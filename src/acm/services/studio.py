import asyncio
import logging
import subprocess
import uuid
from collections.abc import AsyncIterator, Callable
from pathlib import Path

from acm.core.exceptions import (
    AppError,
    InvalidInputError,
    UnsupportedMediaTypeError,
    VideoNotEditableError,
    VideoNotFoundError,
)
from acm.db.uow import UnitOfWork
from acm.integrations.youtube import (
    VideoProbe,
    download_youtube,
    probe_youtube,
    validate_youtube_url,
)
from acm.models.video import STARTABLE_STATUSES, Video, VideoStatus
from acm.schemas.video import FragmentsOptions, ImportProgress, VideoRead
from acm.storage import FileStorage

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = frozenset({"mp4", "mov", "webm"})  # formats TikTok accepts
OUTPUT_EXTENSION = "mp4"  # ffmpeg output is always h264/aac, which webm can't hold

# Background YouTube imports. Module-level on purpose: StudioService is rebuilt per request.
_JOBS: dict[int, "asyncio.Task[None]"] = {}
_PROGRESS: dict[int, float] = {}
_IMPORT_SLOTS = asyncio.Semaphore(2)


class StudioService:
    """The local video library: upload, edit, delete, serve. Scoped to the user's account."""

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

    # --- reading ---------------------------------------------------------------------------

    async def list_workspace(self, user_id: uuid.UUID, account_id: int) -> list[VideoRead]:
        """Drafts, queued, in-flight and failed videos."""
        async with self._uow_factory() as uow:
            await uow.tiktok_accounts.require_for_user(user_id, account_id)
            videos = await uow.videos.list_active(account_id)
            for v in videos:  # a placeholder whose task died with the server
                if v.status == VideoStatus.DOWNLOADING.value and v.id not in _JOBS:
                    v.status = VideoStatus.FAILED.value
                    v.error = "The download was interrupted. Try again."
            await uow.commit()
            return [VideoRead.model_validate(v) for v in videos]

    async def list_history(
        self, user_id: uuid.UUID, account_id: int, limit: int = 10
    ) -> list[VideoRead]:
        """Recently delivered videos (published / sent to TikTok drafts)."""
        async with self._uow_factory() as uow:
            await uow.tiktok_accounts.require_for_user(user_id, account_id)
            videos = await uow.videos.list_done(account_id, limit)
            return [VideoRead.model_validate(v) for v in videos]

    async def get_video(self, user_id: uuid.UUID, account_id: int, video_id: int) -> VideoRead:
        async with self._uow_factory() as uow:
            await uow.tiktok_accounts.require_for_user(user_id, account_id)
            video = await uow.videos.get_in_account(account_id, video_id)
            if video is None:
                raise VideoNotFoundError()
            return VideoRead.model_validate(video)

    async def get_file(self, user_id: uuid.UUID, account_id: int, file_name: str) -> Path:
        async with self._uow_factory() as uow:
            await uow.tiktok_accounts.require_for_user(user_id, account_id)
            video = await uow.videos.get_by_file_name(account_id, file_name)
        path = self._storage.path_for(video.file_name) if video and video.file_name else None
        if path is None:
            raise VideoNotFoundError()
        return path

    # --- writing ---------------------------------------------------------------------------

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

        # authorize BEFORE reading the (possibly huge) upload, in a short transaction:
        # we must not hold a DB connection while the file is streaming to disk.
        async with self._uow_factory() as uow:
            await uow.tiktok_accounts.require_for_user(user_id, account_id)

        stored = await self._storage.save(
            chunks, extension=extension, max_bytes=self._max_upload_bytes
        )
        try:
            return await self._add_video(
                account_id,
                video_name=Path(filename or "").name[:255],
                file_name=stored.name,
                title=title,
                description=description,
            )
        except Exception:
            await self._storage.delete(stored.name)
            raise

    async def probe_url(
        self, user_id: uuid.UUID, account_id: int, *, url: str
    ) -> VideoProbe:
        """Metadata only: title, duration, list of audio tracks. No download."""
        async with self._uow_factory() as uow:
            await uow.tiktok_accounts.require_for_user(user_id, account_id)
        return await asyncio.to_thread(probe_youtube, url)

    async def start_import(
        self,
        user_id: uuid.UUID,
        account_id: int,
        *,
        url: str,
        audio_language: str | None = None,
        metadata_language: str | None = None,
    ) -> VideoRead:
        """Begin a YouTube import in the background and return at once.

        A placeholder row (status "downloading") is created; a task fills it in when the file
        arrives. The UI polls `import_progress()`.

        `audio_language` — BCP-47 code ("ru", "en-US"); selects the matching audio track.
        `metadata_language` — same code; yt-dlp returns title/description in that language.
        """
        url = validate_youtube_url(url)
        async with self._uow_factory() as uow:
            await uow.tiktok_accounts.require_for_user(user_id, account_id)
        video = await self._add_video(
            account_id,
            video_name=url[:255],
            file_name=None,
            title="Downloading…",
            description="",
            status=VideoStatus.DOWNLOADING,
        )
        task = asyncio.create_task(
            self._run_import(
                video.id,
                url,
                audio_language=audio_language,
                metadata_language=metadata_language,
            )
        )
        _JOBS[video.id] = task  # module-level: this service object lives for one request only
        task.add_done_callback(lambda _t, vid=video.id: (_JOBS.pop(vid, None), _PROGRESS.pop(vid, None)))
        return video

    async def import_progress(
        self, user_id: uuid.UUID, account_id: int, video_id: int
    ) -> ImportProgress:
        async with self._uow_factory() as uow:
            await uow.tiktok_accounts.require_for_user(user_id, account_id)
            video = await uow.videos.get_in_account(account_id, video_id)
            if video is None:
                raise VideoNotFoundError()
            if video.status == VideoStatus.DOWNLOADING.value and video_id not in _JOBS:
                video.status = VideoStatus.FAILED.value  # the server restarted mid-download
                video.error = "The download was interrupted. Try again."
                await uow.commit()
            percent = int(_PROGRESS.get(video_id, 0) * 100)
            if video.status != VideoStatus.DOWNLOADING.value:
                percent = 100 if video.status == VideoStatus.DRAFT.value else 0
            return ImportProgress(status=video.status, percent=percent, error=video.error)

    async def _run_import(
        self,
        video_id: int,
        url: str,
        *,
        audio_language: str | None = None,
        metadata_language: str | None = None,
    ) -> None:
        stem = self._storage.new_path("tmp").with_suffix("")
        name: str | None = None
        try:
            async with _IMPORT_SLOTS:  # at most a couple of downloads at once
                result = await asyncio.to_thread(
                    download_youtube,
                    url,
                    stem,
                    self._max_upload_bytes,
                    lambda fraction: _PROGRESS.__setitem__(video_id, fraction),
                    audio_language=audio_language,
                    metadata_language=metadata_language,
                )
            name = result.path.name
            if result.path.suffix.removeprefix(".").lower() not in ALLOWED_EXTENSIONS:
                raise UnsupportedMediaTypeError("YouTube returned an unsupported video format")
            async with self._uow_factory() as uow:
                video = await uow.videos.get(video_id)
                if video is None:
                    await self._storage.delete(name)
                    return
                video.file_name = name
                video.video_name = f"{result.title}.mp4"[:255]
                video.title = result.title[:255]
                video.status = VideoStatus.DRAFT.value
                video.error = None
                await uow.commit()
            logger.info("YouTube video imported video_id=%s lang=%s", video_id, audio_language)
        except AppError as exc:
            if name:
                await self._storage.delete(name)
            await self._fail_import(video_id, exc.message)
        except Exception:
            logger.exception("YouTube import crashed video_id=%s", video_id)
            if name:
                await self._storage.delete(name)
            await self._fail_import(video_id, "Unexpected error while downloading")

    async def _fail_import(self, video_id: int, message: str) -> None:
        async with self._uow_factory() as uow:
            video = await uow.videos.get(video_id)
            if video is not None:
                video.status = VideoStatus.FAILED.value
                video.error = message[:1000]
                await uow.commit()

    async def update_video(
        self, user_id: uuid.UUID, account_id: int, video_id: int, *, title: str, description: str
    ) -> VideoRead:
        async with self._uow_factory() as uow:
            video = await self._require_startable(uow, user_id, account_id, video_id)
            video.title = title
            video.description = description
            await uow.commit()
            return VideoRead.model_validate(video)

    async def delete_video(self, user_id: uuid.UUID, account_id: int, video_id: int) -> None:
        async with self._uow_factory() as uow:
            video = await self._require_startable(uow, user_id, account_id, video_id)
            file_name = video.file_name
            await uow.videos.delete(video)
            await uow.commit()
        # best-effort disk cleanup AFTER commit: if it fails, the DB is still consistent
        if file_name:
            await self._storage.delete(file_name)
        logger.info("Video deleted account_id=%s video_id=%s", account_id, video_id)

    # --- processing ------------------------------------------------------------------------

    async def upload_video_processed(
        self,
        user_id: uuid.UUID,
        account_id: int,
        *,
        filename: str | None,
        content_type: str | None,
        chunks: AsyncIterator[bytes],
        title: str,
        description: str,
        start: float = 0,
        end: float | None = None,
        speed: float = 1.0,
    ) -> VideoRead:
        extension = self._validate_media(filename, content_type)
        async with self._uow_factory() as uow:
            await uow.tiktok_accounts.require_for_user(user_id, account_id)

        stored_raw = await self._storage.save(
            chunks, extension=extension, max_bytes=self._max_upload_bytes
        )
        raw_path = self._storage.path_for(stored_raw.name)
        if raw_path is None:
            raise InvalidInputError("Failed to store upload")

        out_path = self._storage.new_path(OUTPUT_EXTENSION)
        try:
            await self._ffmpeg_trim_speed(raw_path, out_path, start, end, speed)
            return await self._add_video(
                account_id,
                video_name=Path(filename or "").name[:255],
                file_name=out_path.name,
                title=title,
                description=description,
            )
        except BaseException:
            await self._storage.delete(out_path.name)
            raise
        finally:
            await self._storage.delete(stored_raw.name)

    async def upload_fragments(
        self,
        user_id: uuid.UUID,
        account_id: int,
        *,
        filename: str | None,
        content_type: str | None,
        chunks: AsyncIterator[bytes],
        options: FragmentsOptions,
    ) -> list[VideoRead]:
        """Upload a source file and cut it into one video per enabled fragment."""
        extension = self._validate_media(filename, content_type)
        async with self._uow_factory() as uow:
            await uow.tiktok_accounts.require_for_user(user_id, account_id)

        stored = await self._storage.save(
            chunks, extension=extension, max_bytes=self._max_upload_bytes
        )
        try:
            return await self._cut(
                user_id,
                account_id,
                source_name=stored.name,
                video_name=Path(filename or "").name[:255],
                options=options,
                replace_video_id=None,
            )
        finally:
            await self._storage.delete(stored.name)  # the raw upload is never kept

    async def split_video(
        self, user_id: uuid.UUID, account_id: int, video_id: int, options: FragmentsOptions
    ) -> list[VideoRead]:
        """Cut an existing draft (e.g. a YouTube import) into fragments, replacing the draft."""
        async with self._uow_factory() as uow:
            source = await self._require_startable(uow, user_id, account_id, video_id)
            source_name, video_name = source.file_name, source.video_name
        if not source_name:
            raise VideoNotFoundError("The video file is missing")
        return await self._cut(
            user_id,
            account_id,
            source_name=source_name,
            video_name=video_name,
            options=options,
            replace_video_id=video_id,
        )

    async def _cut(
        self,
        user_id: uuid.UUID,
        account_id: int,
        *,
        source_name: str,
        video_name: str,
        options: FragmentsOptions,
        replace_video_id: int | None,
    ) -> list[VideoRead]:
        source = self._storage.path_for(source_name)
        if source is None:
            raise VideoNotFoundError("The video file is missing")
        enabled = [f for f in options.fragments if f.enabled]

        produced: list[str] = []
        old_file: str | None = None
        try:
            for fragment in enabled:  # sequential on purpose: ffmpeg already uses all cores
                out = self._storage.new_path(OUTPUT_EXTENSION)
                produced.append(out.name)  # registered first so a half-written file is cleaned
                await self._ffmpeg_trim_speed(
                    source, out, fragment.start, fragment.end, options.speed,
                    options.aspect, options.zoom,
                )

            async with self._uow_factory() as uow:
                if replace_video_id is not None:  # re-check: it may have been queued meanwhile
                    old = await self._require_startable(uow, user_id, account_id, replace_video_id)
                    old_file = old.file_name
                    await uow.videos.delete(old)
                else:
                    await uow.tiktok_accounts.require_for_user(user_id, account_id)
                first_position = (
                    await uow.videos.next_queue_position(account_id) if options.queue else None
                )
                videos: list[Video] = []
                for i, (fragment, file_name) in enumerate(zip(enabled, produced, strict=True)):
                    video = Video(
                        account_id=account_id,
                        video_name=video_name,
                        file_name=file_name,
                        title=fragment.title,
                        description=options.description,
                    )
                    if first_position is not None:
                        video.status = VideoStatus.QUEUED.value
                        video.queue_position = first_position + i
                    uow.videos.add(video)
                    videos.append(video)
                await uow.commit()
                result = [VideoRead.model_validate(v) for v in videos]
        except BaseException:
            for name in produced:
                await self._storage.delete(name)
            raise

        if old_file:
            await self._storage.delete(old_file)
        logger.info(
            "Fragments created account_id=%s count=%s queued=%s", account_id, len(result), options.queue
        )
        return result

    async def _ffmpeg_trim_speed(
        self,
        input_path: Path,
        output_path: Path,
        start: float,
        end: float | None,
        speed: float,
        aspect: str = "original",
        zoom: float = 0.0,
    ) -> None:
        """Trim with -ss/-to, change speed with setpts/atempo, optionally reframe to 9:16."""
        vf = f"setpts=PTS/{speed}"
        if aspect == "9:16":
            vf += "," + _vertical_filter(zoom)
        atempo = speed  # atempo only accepts 0.5–2.0 per instance, so chain them
        af_parts: list[str] = []
        while atempo > 2.0:
            af_parts.append("atempo=2.0")
            atempo /= 2.0
        while atempo < 0.5:
            af_parts.append("atempo=0.5")
            atempo *= 2.0
        af_parts.append(f"atempo={atempo:.6f}")

        cmd = ["ffmpeg", "-y", "-ss", str(start)]
        if end is not None and end > start:
            cmd += ["-to", str(end)]
        cmd += [
            "-i", str(input_path),
            "-vf", vf,
            "-af", ",".join(af_parts),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            str(output_path),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise InvalidInputError(f"ffmpeg failed: {stderr.decode(errors='replace')[-300:]}")

    # --- helpers ---------------------------------------------------------------------------

    async def _add_video(
        self,
        account_id: int,
        *,
        video_name: str,
        file_name: str | None,
        title: str,
        description: str,
        status: VideoStatus = VideoStatus.DRAFT,
    ) -> VideoRead:
        async with self._uow_factory() as uow:
            video = Video(
                account_id=account_id,
                video_name=video_name,
                file_name=file_name,
                title=title,
                description=description,
                status=status.value,
            )
            uow.videos.add(video)
            await uow.commit()
            return VideoRead.model_validate(video)

    @staticmethod
    async def _require_startable(
        uow: UnitOfWork, user_id: uuid.UUID, account_id: int, video_id: int
    ) -> Video:
        """A video that may still be changed (not in flight, not delivered)."""
        await uow.tiktok_accounts.require_for_user(user_id, account_id)
        video = await uow.videos.get_in_account(account_id, video_id)
        if video is None:
            raise VideoNotFoundError()
        if video.status not in {s.value for s in STARTABLE_STATUSES}:
            if video.status == VideoStatus.PUBLISHING.value:
                raise VideoNotEditableError("This video is being published right now")
            raise VideoNotEditableError("This video has already been sent to TikTok")
        return video

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


def _vertical_filter(zoom: float) -> str:
    """ffmpeg filter that puts any frame onto a 1080x1920 canvas.

    The picture is scaled to height h, then centre-cropped to the canvas width (if wider) and
    padded with black to the canvas height (if shorter):
        h = hfit * (1 - zoom) + 1920 * zoom,   hfit = height at which the whole frame fits the width
    zoom=0 -> whole frame, big bars; zoom=1 -> fills the screen, sides cropped; in between ->
    a bigger picture with thinner bars and only part of the sides cut off.
    """
    z = max(0.0, min(1.0, zoom))
    hfit = "min(1080*ih/iw,1920)"
    height = f"trunc(({hfit}*(1-{z:.4f})+1920*{z:.4f})/2)*2"
    return (
        f"scale=-2:'{height}',"
        "crop='min(iw,1080)':ih,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
    )