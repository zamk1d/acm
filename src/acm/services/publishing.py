"""Sending videos to TikTok.

A publish is a JOB, not a request: uploading a few hundred MB and waiting for TikTok to process it
takes minutes, far longer than an HTTP request should live. So:

    start()            validates, flips the video to PUBLISHING and returns immediately;
    process_pending()  is called by the background worker every few seconds and advances each
                       PUBLISHING video by ONE step:
                         step 1  init + upload the file          (stores `publish_id`)
                         step N  ask TikTok for the status       (until it is final)

All state lives in the `videos` row, so a restart of the server loses nothing.
"""

import asyncio
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from acm.core.exceptions import (
    AppError,
    InvalidInputError,
    MissingScopeError,
    VideoNotEditableError,
    VideoNotFoundError,
)
from acm.core.time import utcnow
from acm.db.uow import UnitOfWork
from acm.integrations.tiktok import (
    DirectPostInfo,
    TikTokAPIError,
    TikTokClient,
    TikTokPostStatus,
    TikTokTransportError,
    mime_for,
    plan_chunks,
)
from acm.integrations.tiktok.scopes import SCOPE_VIDEO_PUBLISH, SCOPE_VIDEO_UPLOAD
from acm.models.video import STARTABLE_STATUSES, VideoStatus
from acm.schemas.publishing import PublishMethod, PublishOptions
from acm.schemas.video import VideoRead
from acm.services.tiktok import TikTokService
from acm.storage import FileStorage

logger = logging.getLogger(__name__)

POLL_INTERVAL = timedelta(seconds=10)  # between status checks
RETRY_DELAY = timedelta(seconds=30)  # after a network hiccup
UPLOAD_LOCK = timedelta(minutes=30)  # nobody else touches a video while its file is being sent
MAX_ATTEMPTS = 90  # ≈ 15 minutes of waiting for TikTok before we give up

_SCOPE_FOR_METHOD = {
    PublishMethod.DIRECT: SCOPE_VIDEO_PUBLISH,
    PublishMethod.DRAFT: SCOPE_VIDEO_UPLOAD,
}
_STARTABLE = {s.value for s in STARTABLE_STATUSES}


@dataclass(frozen=True, slots=True)
class _Job:
    video_id: int
    account_id: int
    user_id: uuid.UUID
    file_name: str | None
    caption: str
    publish_id: str | None
    options: PublishOptions


class PublishingService:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        tiktok: TikTokClient,
        accounts: TikTokService,
        storage: FileStorage,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._uow_factory = uow_factory
        self._tiktok = tiktok
        self._accounts = accounts
        self._storage = storage
        self._clock = clock
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def running(self) -> int:
        """How many jobs this instance is working on right now."""
        return len(self._tasks)

    # --- starting a publish ----------------------------------------------------------------

    async def start(
        self, user_id: uuid.UUID, account_id: int, video_id: int, options: PublishOptions
    ) -> VideoRead:
        """Queue a video for publishing. Returns at once; the worker does the actual work."""
        async with self._uow_factory() as uow:
            account = await uow.tiktok_accounts.require_for_user(user_id, account_id)
            video = await uow.videos.get_in_account(account_id, video_id)
            if video is None:
                raise VideoNotFoundError()
            if video.status not in _STARTABLE:
                raise VideoNotEditableError("This video is already being sent or was sent to TikTok")
            if not video.file_name or self._storage.path_for(video.file_name) is None:
                raise VideoNotFoundError("The video file is missing, upload it again")
            if _SCOPE_FOR_METHOD[options.method] not in account.scopes.split(","):
                raise MissingScopeError()

        if options.method is PublishMethod.DIRECT:
            options = await self._apply_creator_limits(user_id, account_id, options)

        async with self._uow_factory() as uow:
            claimed = await uow.videos.claim(  # atomic: of two simultaneous clicks only one wins
                account_id,
                video_id,
                from_statuses=STARTABLE_STATUSES,
                values={
                    "status": VideoStatus.PUBLISHING.value,
                    "publish_options": options.model_dump(mode="json"),
                    "publish_id": None,
                    "attempts": 0,
                    "locked_until": None,
                    "error": None,
                    "queue_position": None,
                },
            )
            if not claimed:
                raise VideoNotEditableError("This video is already being published")
            await uow.commit()
        logger.info("Publish started account_id=%s video_id=%s method=%s", account_id, video_id, options.method)
        return await self._read(account_id, video_id)

    async def _apply_creator_limits(
        self, user_id: uuid.UUID, account_id: int, options: PublishOptions
    ) -> PublishOptions:
        """TikTok requires posts to respect the creator's current settings."""
        info = await self._accounts.get_creator_info(user_id, account_id)
        if options.privacy_level not in info.privacy_level_options:
            raise InvalidInputError("This visibility isn't available for the account right now")
        return options.model_copy(
            update={
                "disable_comment": options.disable_comment or info.comment_disabled,
                "disable_duet": options.disable_duet or info.duet_disabled,
                "disable_stitch": options.disable_stitch or info.stitch_disabled,
            }
        )

    # --- the worker side -------------------------------------------------------------------

    async def process_pending(self, *, limit: int = 3, wait: bool = False) -> int:
        """Advance up to `limit` due jobs by one step. With wait=True, returns when they're done."""
        if limit <= 0:
            return 0
        now = self._clock()
        async with self._uow_factory() as uow:
            ids = await uow.videos.claim_due_publishing(now, now + UPLOAD_LOCK, limit)
            await uow.commit()
        tasks = [asyncio.create_task(self._run_step(video_id)) for video_id in ids]
        if wait:
            await asyncio.gather(*tasks)
        else:
            for task in tasks:
                self._tasks.add(task)  # keep a reference, or the task may be garbage collected
                task.add_done_callback(self._tasks.discard)
        return len(ids)

    async def _run_step(self, video_id: int) -> None:
        try:
            await self._advance(video_id)
        except TikTokTransportError:
            logger.warning("Network problem while publishing video_id=%s, will retry", video_id)
            await self._release(video_id)
        except AppError as exc:
            logger.warning("Publishing failed video_id=%s: %s", video_id, exc.message)
            await self.fail_video(video_id, exc.message)
        except Exception:
            logger.exception("Unexpected error while publishing video_id=%s", video_id)
            await self.fail_video(video_id, "Unexpected error while publishing")

    async def _advance(self, video_id: int) -> None:
        async with self._uow_factory() as uow:
            video = await uow.videos.get(video_id)
            if video is None or video.status != VideoStatus.PUBLISHING.value:
                return
            account = await uow.tiktok_accounts.get(video.account_id)
            if account is None:
                return
            job = _Job(
                video_id=video.id,
                account_id=account.id,
                user_id=account.user_id,
                file_name=video.file_name,
                caption=(video.description or video.title)[:2200],
                publish_id=video.publish_id,
                options=PublishOptions.model_validate(video.publish_options or {}),
            )
        token = await self._accounts.get_access_token(job.user_id, job.account_id)
        if job.publish_id is None:
            await self._send_file(job, token)
        else:
            await self._check_status(job, token)

    async def _send_file(self, job: _Job, token: str) -> None:
        path = self._storage.path_for(job.file_name) if job.file_name else None
        if path is None:
            raise VideoNotFoundError("The video file is missing")
        plan = plan_chunks(path.stat().st_size)
        options = job.options

        if options.method is PublishMethod.DIRECT:
            init = await self._tiktok.init_direct_post(
                token,
                DirectPostInfo(
                    caption=job.caption,
                    privacy_level=options.privacy_level or "SELF_ONLY",
                    disable_comment=options.disable_comment,
                    disable_duet=options.disable_duet,
                    disable_stitch=options.disable_stitch,
                    is_aigc=options.is_aigc,
                    brand_content_toggle=options.brand_content_toggle,
                    brand_organic_toggle=options.brand_organic_toggle,
                    cover_timestamp_ms=options.cover_timestamp_ms,
                ),
                plan,
            )
        else:
            init = await self._tiktok.init_inbox_upload(token, plan)

        if not init.upload_url:
            raise TikTokAPIError("invalid_response", "TikTok did not return an upload URL")
        await self._tiktok.upload_video_file(init.upload_url, path, plan, mime_for(path))
        await self._update(
            job.video_id, publish_id=init.publish_id, locked_until=self._clock() + POLL_INTERVAL
        )
        logger.info("File sent to TikTok video_id=%s publish_id=%s", job.video_id, init.publish_id)

    async def _check_status(self, job: _Job, token: str) -> None:
        assert job.publish_id is not None
        status = await self._tiktok.check_posting_status(token, job.publish_id)
        if status.status == "FAILED":
            await self.fail_video(job.video_id, status.fail_reason or "TikTok rejected the video")
        elif status.status == "PUBLISH_COMPLETE":
            await self._complete(job.video_id, VideoStatus.PUBLISHED, status)
        elif status.status == "SEND_TO_USER_INBOX" and job.options.method is PublishMethod.DRAFT:
            await self._complete(job.video_id, VideoStatus.INBOX, status)
        else:  # PROCESSING_UPLOAD / PROCESSING_DOWNLOAD / ...: ask again later
            await self._release(job.video_id, delay=POLL_INTERVAL)

    # --- state transitions -----------------------------------------------------------------

    async def _complete(self, video_id: int, status: VideoStatus, tiktok: TikTokPostStatus) -> None:
        """TikTok has the video: record the result and delete our copy of the file."""
        async with self._uow_factory() as uow:
            video = await uow.videos.get(video_id)
            if video is None:
                return
            file_name = video.file_name
            video.status = status.value
            video.file_name = None
            video.locked_until = None
            video.error = None
            video.published_at = self._clock()
            if tiktok.publicaly_available_post_id:
                video.tiktok_video_id = str(tiktok.publicaly_available_post_id[0])
            await uow.commit()
        if file_name:
            await self._storage.delete(file_name)
        logger.info("Video delivered video_id=%s status=%s", video_id, status.value)

    async def fail_video(self, video_id: int, message: str) -> None:
        """Mark a queued / publishing video as failed. The file is kept so it can be retried."""
        async with self._uow_factory() as uow:
            video = await uow.videos.get(video_id)
            if video is None or video.status not in {
                VideoStatus.PUBLISHING.value,
                VideoStatus.QUEUED.value,
            }:
                return
            video.status = VideoStatus.FAILED.value
            video.error = message[:1000]
            video.locked_until = None
            await uow.commit()

    async def _release(self, video_id: int, *, delay: timedelta = RETRY_DELAY) -> None:
        """Count an attempt and make the job due again after `delay` (or give up)."""
        async with self._uow_factory() as uow:
            video = await uow.videos.get(video_id)
            if video is None or video.status != VideoStatus.PUBLISHING.value:
                return
            video.attempts += 1
            if video.attempts >= MAX_ATTEMPTS:
                video.status = VideoStatus.FAILED.value
                video.error = "TikTok is taking too long to process the video"
                video.locked_until = None
            else:
                video.locked_until = self._clock() + delay
            await uow.commit()

    async def _update(self, video_id: int, **values: object) -> None:
        async with self._uow_factory() as uow:
            video = await uow.videos.get(video_id)
            if video is not None:
                for key, value in values.items():
                    setattr(video, key, value)
                await uow.commit()

    async def _read(self, account_id: int, video_id: int) -> VideoRead:
        async with self._uow_factory() as uow:
            video = await uow.videos.get_in_account(account_id, video_id)
            if video is None:
                raise VideoNotFoundError()
            return VideoRead.model_validate(video)
