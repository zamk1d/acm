import logging
import os
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta

from acm.core.config import Settings
from acm.core.exceptions import (
    AccountAlreadyLinkedError,
    ReauthorizationRequiredError,
    UpstreamError, VideoNotFoundError, PublishNotImplementedError,
)
from acm.core.time import utcnow
from acm.db.uow import UnitOfWork
from acm.integrations.tiktok import TikTokClient, TikTokUser, TikTokVideoPage, TokenResponse
from acm.integrations.tiktok.schemas import TikTokPostStatus
from acm.integrations.tiktok.scopes import fields_for_scopes
from acm.models import TikTokAccount
from acm.schemas.account import AccountRead
from acm.schemas.tiktok import TikTokVideoPostRequest
from acm.schemas.video import VideoRead
from acm.storage import LocalFileStorage, FileStorage
from acm.core.config import get_settings

logger = logging.getLogger(__name__)

# Refresh slightly before the real expiry so a token never dies mid-request.
TOKEN_EXPIRY_LEEWAY = timedelta(minutes=2)
VIDEO_LIST_FIELDS = ("id", "title", "cover_image_url", "embed_link")

# Константы должны быть заданы в байтах
MIN_CHUNK_SIZE = 5 * 1024 * 1024          # 5 MB
MAX_CHUNK_SIZE = 64 * 1024 * 1024         # 64 MB
DEFAULT_CHUNK_SIZE = 10 * 1024 * 1024     # 10 MB (рекомендуемый)
MAX_WHOLE_SIZE = 64 * 1024 * 1024         # 64 MB — можно грузить целиком


def calculate_chunks(video_size: int) -> tuple[int, int]:
    """
    Возвращает (chunk_size, total_chunk_count) по правилам TikTok Media Transfer Guide:
    - видео ≤ 64 MB грузится одним чанком;
    - total_chunk_count = video_size // chunk_size (floor);
    - каждый чанк ≥ 5 MB и ≤ 64 MB (кроме последнего — до 128 MB).
    """
    # 1. Небольшие видео (≤ 64 MB) — всегда целиком
    if video_size <= MAX_WHOLE_SIZE:
        return video_size, 1

    # 2. Выбираем размер чанка
    chunk_size = min(DEFAULT_CHUNK_SIZE, MAX_CHUNK_SIZE)

    # 3. КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: floor, а не ceil
    total_chunk_count = video_size // chunk_size

    # 4. Защита от нуля (не должно случиться при video_size > 64 MB,
    #    но пусть будет)
    if total_chunk_count == 0:
        total_chunk_count = 1

    return chunk_size, total_chunk_count

class TikTokService:
    """Connecting / managing TikTok accounts that belong to a service user."""

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        tiktok: TikTokClient,
        storage: FileStorage,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._uow_factory = uow_factory
        self._tiktok = tiktok
        self._clock = clock
        self._storage = storage

    def build_authorization_url(self, state: str) -> str:
        return self._tiktok.build_authorization_url(state)

    async def connect_account(self, user_id: uuid.UUID, code: str) -> AccountRead:
        tokens = await self._tiktok.exchange_code(code)
        profile = await self._tiktok.get_user_info(
            tokens.access_token, fields_for_scopes(tokens.scopes)
        )

        async with self._uow_factory() as uow:
            account = await uow.tiktok_accounts.get_by_open_id(tokens.open_id)
            if account is not None and account.user_id != user_id:
                raise AccountAlreadyLinkedError()
            if account is None:
                account = TikTokAccount(open_id=tokens.open_id, user_id=user_id)
                uow.tiktok_accounts.add(account)
            self._apply_tokens(account, tokens)
            self._apply_profile(account, profile)
            await uow.commit()
            logger.info("TikTok connected user_id=%s open_id=%s", user_id, account.open_id)
            return AccountRead.model_validate(account)

    async def list_accounts(self, user_id: uuid.UUID) -> list[AccountRead]:
        async with self._uow_factory() as uow:
            accounts = await uow.tiktok_accounts.list_by_user(user_id)
            return [AccountRead.model_validate(a) for a in accounts]

    async def get_account(self, user_id: uuid.UUID, account_id: int) -> AccountRead:
        async with self._uow_factory() as uow:
            account = await uow.tiktok_accounts.require_for_user(user_id, account_id)
            return AccountRead.model_validate(account)

    async def get_access_token(self, user_id: uuid.UUID, account_id: int) -> str:
        """A valid access token for the account; refreshes it transparently when it is stale."""
        async with self._uow_factory() as uow:
            account = await uow.tiktok_accounts.require_for_user(user_id, account_id)
            now = self._clock()
            if not account.is_access_token_expired(now, TOKEN_EXPIRY_LEEWAY):
                return account.access_token
            if account.is_refresh_token_expired(now):
                raise ReauthorizationRequiredError()
            tokens = await self._tiktok.refresh_access_token(account.refresh_token)
            self._apply_tokens(account, tokens)
            await uow.commit()
            return account.access_token

    async def list_videos(
        self, user_id: uuid.UUID, account_id: int, cursor: int | None = None
    ) -> TikTokVideoPage:
        """Published videos of the account, straight from TikTok (needs the video.list scope)."""
        token = await self.get_access_token(user_id, account_id)
        return await self._tiktok.get_user_videos(token, VIDEO_LIST_FIELDS, cursor=cursor)

    async def refresh_tokens(self, user_id: uuid.UUID, account_id: int) -> AccountRead:
        async with self._uow_factory() as uow:
            account = await uow.tiktok_accounts.require_for_user(user_id, account_id)
            tokens = await self._tiktok.refresh_access_token(account.refresh_token)
            self._apply_tokens(account, tokens)
            await uow.commit()
            return AccountRead.model_validate(account)

    async def disconnect(self, user_id: uuid.UUID, account_id: int) -> None:
        async with self._uow_factory() as uow:
            account = await uow.tiktok_accounts.require_for_user(user_id, account_id)
            try:
                await self._tiktok.revoke_token(account.access_token)
            except UpstreamError:
                # Token may already be expired/revoked; the user still wants the account gone.
                logger.warning("Token revoke failed open_id=%s", account.open_id, exc_info=True)
            await uow.tiktok_accounts.delete(account)
            await uow.commit()

    # --- helpers ---------------------------------------------------------------------------

    def _apply_tokens(self, account: TikTokAccount, tokens: TokenResponse) -> None:
        now = self._clock()
        account.access_token = tokens.access_token
        account.refresh_token = tokens.refresh_token
        account.scopes = ",".join(tokens.scopes)
        account.access_token_expires_at = now + timedelta(seconds=tokens.expires_in)
        account.refresh_token_expires_at = now + timedelta(seconds=tokens.refresh_expires_in)

    @staticmethod
    def _apply_profile(account: TikTokAccount, profile: TikTokUser) -> None:
        account.union_id = profile.union_id
        account.display_name = profile.display_name
        account.avatar_url = (
            profile.avatar_large_url or profile.avatar_url_100 or profile.avatar_url
        )

    async def publish_video(
        self, user_id: uuid.UUID, account_id: int, video_id: int, video_data: TikTokVideoPostRequest
    ):
        async with self._uow_factory() as uow:
            video = await uow.videos.get_by_id(account_id, video_id)
            if video is None:
                raise VideoNotFoundError()
        access_token = await self.get_access_token(user_id=user_id, account_id=account_id)

        post_info = video_data.post_info
        source_info = video_data.source_info
        filepath = self._storage.path_for(name=video.file_name)

        if filepath is None:
            raise FileNotFoundError(f"Video file not found: {video.video_name}")

        video_size = os.path.getsize(str(filepath))

        chunk_size, total_chunk_count = calculate_chunks(video_size=video_size)

        publish_response = await self._tiktok.publish_video(
            access_token=access_token,
            title=video.title,
            disable_duet=post_info.disable_duet,
            disable_stitch=post_info.disable_stitch,
            disable_comment=post_info.disable_comment,
            cover_ts=post_info.video_cover_timestamp_ms or 0,
            brand_content_toggle=post_info.brand_content_toggle,
            is_aigc=post_info.is_aigc,
            privacy_level=post_info.privacy_level,
            source=source_info.source,
            video_url=source_info.video_url,
            video_size=video_size,
            chunk_size=chunk_size,
            total_chunk_count=total_chunk_count,
        )

        r = await self._upload_video_chunks(upload_url=publish_response.upload_url, file_path=str(filepath), chunk_size=chunk_size)
        logger.info("PUBLISH: %s", r)
        return VideoRead.model_validate(video)

    async def post_video_draft(
        self, user_id: uuid.UUID, account_id: int, video_id: int
    ) -> VideoRead:
        """Upload a local draft to the TikTok inbox (drafts folder).

        The video is not published automatically — the user opens the TikTok
        app, finds it in drafts, adds sounds/effects, picks privacy, and publishes.

        Local draft and its file are kept as-is so the user can retry if needed.
        (When you decide how to mark "sent to drafts" — add a `Video` field
        like `drafts_uploaded_at` or set status="in_drafts" — do it here.)
        """
        async with self._uow_factory() as uow:
            await uow.tiktok_accounts.require_for_user(user_id, account_id)
            video = await uow.videos.get_by_id(account_id, video_id)
            if video is None:
                raise VideoNotFoundError()

        access_token = await self.get_access_token(user_id=user_id, account_id=account_id)

        filepath = self._storage.path_for(name=video.file_name)
        if filepath is None:
            raise VideoNotFoundError()

        video_size = os.path.getsize(str(filepath))
        chunk_size, total_chunk_count = calculate_chunks(video_size=video_size)

        init_response = await self._tiktok.init_inbox_upload(
            access_token=access_token,
            video_size=video_size,
            chunk_size=chunk_size,
            total_chunk_count=total_chunk_count,
        )

        await self._upload_video_chunks(
            upload_url=init_response.upload_url,
            file_path=str(filepath),
            chunk_size=chunk_size,
        )

        logger.info(
            "Draft sent to TikTok inbox account_id=%s video_id=%s publish_id=%s",
            account_id,
            video_id,
            init_response.publish_id,
        )
        return VideoRead.model_validate(video)

    async def check_posting_status(
            self, user_id: uuid.UUID, account_id: int, publish_id: str
    ) -> TikTokPostStatus:
        access_token = await self.get_access_token(user_id=user_id, account_id=account_id)
        return await self._tiktok.check_posting_status(
            access_token=access_token, publish_id=publish_id
        )

    async def _upload_video_chunks(
        self,
        upload_url: str,
        file_path: str,
        chunk_size: int,
    ):
        video_size = os.path.getsize(file_path)

        with open(file_path, "rb") as file:
            start = 0

            while start < video_size:
                chunk = file.read(chunk_size)
                if not chunk:
                    break

                end = start + len(chunk) - 1

                r = await self._tiktok.send_video_chunk(
                    url=upload_url,
                    chunk=chunk,
                    content_range=f"bytes {start}-{end}/{video_size}",
                )

                start = end + 1
        return r

