import logging
import uuid
from collections.abc import AsyncIterator, Callable
from pathlib import Path

from acm.core.exceptions import (
    InvalidInputError,
    UnsupportedMediaTypeError,
    VideoNotFoundError, PublishNotImplementedError,
)
from acm.db.uow import UnitOfWork
from acm.models.video import Video
from acm.schemas.video import VideoListRead, VideoRead, VideoDetailRead
from acm.storage import FileStorage

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = frozenset({"mp4", "mov", "webm"})  # formats TikTok accepts


class StudioService:
    """Local video drafts: upload, list, serve. Everything is scoped to the user's account."""

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        storage: FileStorage,
        *,
        max_upload_bytes: int,
    ) -> None:
        self._uow_factory = uow_factory
        self._storage = storage
        self._max_upload_bytes = max_upload_bytes

    async def list_drafts(self, user_id: uuid.UUID, account_id: int) -> list[VideoListRead]:
        async with self._uow_factory() as uow:
            await uow.tiktok_accounts.require_for_user(user_id, account_id)
            videos = await uow.videos.list_unpublished(account_id)
            return [VideoListRead.model_validate(v) for v in videos]

    async def upload_video(
        self,
        user_id: uuid.UUID,
        account_id: int,
        *,
        filename: str | None,
        content_type: str | None,
        chunks: AsyncIterator[bytes],
        title: str,
        description: str,
    ) -> VideoRead:
        extension = self._validate_media(filename, content_type)

        # 1) authorize BEFORE reading the (possibly huge) upload. Separate short transaction:
        #    we must not hold a DB connection while the file is streaming to disk.
        async with self._uow_factory() as uow:
            await uow.tiktok_accounts.require_for_user(user_id, account_id)

        stored = await self._storage.save(
            chunks, extension=extension, max_bytes=self._max_upload_bytes
        )

        # 2) record it. If this fails, don't leave an orphan file on disk.
        try:
            async with self._uow_factory() as uow:
                video = Video(
                    account_id=account_id,
                    video_name=Path(filename or "").name[:255],
                    file_name=stored.name,
                    title=title,
                    description=description,
                )
                uow.videos.add(video)
                await uow.commit()
                logger.info("Draft uploaded account_id=%s file=%s", account_id, stored.name)
                return VideoRead.model_validate(video)
        except Exception:
            await self._storage.delete(stored.name)
            raise

    async def get_draft_file(self, user_id: uuid.UUID, account_id: int, file_name: str) -> Path:
        async with self._uow_factory() as uow:
            await uow.tiktok_accounts.require_for_user(user_id, account_id)
            video = await uow.videos.get_by_file_name(account_id, file_name)
        if video is None:
            raise VideoNotFoundError()
        path = self._storage.path_for(video.file_name)
        if path is None:  # row exists but the file is gone
            raise VideoNotFoundError()
        return path

    # --- helpers ---------------------------------------------------------------------------

    @staticmethod
    def _validate_media(filename: str | None, content_type: str | None) -> str:
        """Returns a safe extension. NOTE: content_type is client-supplied, not a real check."""
        if not filename:
            raise InvalidInputError("File name is missing")
        extension = Path(filename).suffix.removeprefix(".").lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise UnsupportedMediaTypeError(
                f"Allowed formats: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            )
        if not content_type or not content_type.startswith("video/"):
            raise UnsupportedMediaTypeError("The file is not a video")
        return extension

    async def get_video(
        self, user_id: uuid.UUID, account_id: int, video_id: int
    ) -> VideoDetailRead:
        async with self._uow_factory() as uow:
            await uow.tiktok_accounts.require_for_user(user_id, account_id)
            video = await uow.videos.get_by_id(account_id, video_id)
        if video is None:
            raise VideoNotFoundError()
        return VideoDetailRead.model_validate(video)

    async def update_video(
        self,
        user_id: uuid.UUID,
        account_id: int,
        video_id: int,
        *,
        title: str,
        description: str,
    ) -> VideoRead:
        async with self._uow_factory() as uow:
            await uow.tiktok_accounts.require_for_user(user_id, account_id)
            video = await uow.videos.get_by_id(account_id, video_id)
            if video is None:
                raise VideoNotFoundError()
            video.title = title
            video.description = description
            await uow.commit()
            logger.info("Draft updated account_id=%s video_id=%s", account_id, video_id)
            return VideoRead.model_validate(video)

    async def delete_video(
        self, user_id: uuid.UUID, account_id: int, video_id: int
    ) -> None:
        async with self._uow_factory() as uow:
            await uow.tiktok_accounts.require_for_user(user_id, account_id)
            video = await uow.videos.get_by_id(account_id, video_id)
            if video is None:
                raise VideoNotFoundError()
            file_name = video.file_name
            await uow.videos.delete(video)
            await uow.commit()
        # best-effort disk cleanup AFTER commit: if it fails, DB is still consistent
        if file_name:
            await self._storage.delete(file_name)
        logger.info("Draft deleted account_id=%s video_id=%s", account_id, video_id)

