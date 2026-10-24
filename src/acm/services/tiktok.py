import logging
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta

from acm.core.exceptions import (
    AccountAlreadyLinkedError,
    MissingScopeError,
    ReauthorizationRequiredError,
    UpstreamError,
    VideoNotFoundError,
)
from acm.core.time import utcnow
from acm.db.uow import UnitOfWork
from acm.integrations.tiktok import (
    TikTokClient,
    TikTokCreatorInfo,
    TikTokUser,
    TikTokVideo,
    TikTokVideoPage,
    TokenResponse,
)
from acm.integrations.tiktok.scopes import (
    SCOPE_USER_INFO_STATS,
    SCOPE_VIDEO_LIST,
    SCOPE_VIDEO_PUBLISH,
    STATS_FIELDS,
    fields_for_scopes,
)
from acm.models import TikTokAccount
from acm.schemas.account import AccountRead

logger = logging.getLogger(__name__)

# Refresh slightly before the real expiry so a token never dies mid-request.
TOKEN_EXPIRY_LEEWAY = timedelta(minutes=2)

# The library shows these for every video (all come from the same /video/list/ call)
VIDEO_FIELDS = (
    "id",
    "title",
    "video_description",
    "cover_image_url",
    "share_url",
    "embed_link",
    "duration",
    "create_time",
    "view_count",
    "like_count",
    "comment_count",
    "share_count",
)


class TikTokService:
    """Connected TikTok accounts: OAuth, tokens, and everything we READ from TikTok.

    (Sending videos to TikTok lives in PublishingService.)
    """

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        tiktok: TikTokClient,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._uow_factory = uow_factory
        self._tiktok = tiktok
        self._clock = clock

    # --- accounts --------------------------------------------------------------------------

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

    # --- tokens ----------------------------------------------------------------------------

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

    # --- reading from TikTok ---------------------------------------------------------------

    async def list_videos(
        self, user_id: uuid.UUID, account_id: int, cursor: int | None = None
    ) -> TikTokVideoPage:
        """Videos live on the channel, newest first (needs the video.list scope)."""
        token = await self.get_access_token(user_id, account_id)
        return await self._tiktok.get_user_videos(token, VIDEO_FIELDS, cursor=cursor)

    async def get_video(
        self, user_id: uuid.UUID, account_id: int, tiktok_video_id: str
    ) -> TikTokVideo:
        token = await self.get_access_token(user_id, account_id)
        videos = await self._tiktok.query_videos(token, [tiktok_video_id], VIDEO_FIELDS)
        if not videos:  # TikTok drops ids that don't belong to this user
            raise VideoNotFoundError()
        return videos[0]

    async def get_channel_stats(self, user_id: uuid.UUID, account_id: int) -> TikTokUser | None:
        """Followers / likes / video count of the channel; None if that scope wasn't granted."""
        account = await self.get_account(user_id, account_id)
        if SCOPE_USER_INFO_STATS not in account.scopes:
            return None
        token = await self.get_access_token(user_id, account_id)
        return await self._tiktok.get_user_info(token, ["open_id", *STATS_FIELDS])

    async def get_creator_info(self, user_id: uuid.UUID, account_id: int) -> TikTokCreatorInfo:
        """What this creator may post right now (privacy levels, interaction settings)."""
        account = await self.get_account(user_id, account_id)
        if SCOPE_VIDEO_PUBLISH not in account.scopes:
            raise MissingScopeError("Direct posting isn't authorized. Reconnect the account.")
        token = await self.get_access_token(user_id, account_id)
        return await self._tiktok.query_creator_info(token)

    async def can_list_videos(self, user_id: uuid.UUID, account_id: int) -> bool:
        return SCOPE_VIDEO_LIST in (await self.get_account(user_id, account_id)).scopes

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
