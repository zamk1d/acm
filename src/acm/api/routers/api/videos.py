import mimetypes
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import ValidationError

from acm.api.deps import CurrentUserId, StudioDep
from acm.api.uploads import iter_upload
from acm.core.exceptions import InvalidInputError, VideoNotFoundError
from acm.schemas.video import (
    FragmentsOptions,
    ImportProgress,
    VideoProbeRead,
    VideoRead,
    VideoRequest,
    VideoUpdateRequest,
    VideoUrlProbeRequest,
    VideoUrlRequest,
)

router = APIRouter(prefix="/accounts/{account_id}/videos", tags=["Videos"])


@router.get(
    "",
    response_model=list[VideoRead],
    summary="List workspace videos",
    description="Returns all videos currently in the workspace (drafts, queued, publishing, failed)."
)
async def list_workspace(
    account_id: int, user_id: CurrentUserId, service: StudioDep
) -> list[VideoRead]:
    return await service.list_workspace(user_id, account_id)


@router.get(
    "/history",
    response_model=list[VideoRead],
    summary="List recently delivered videos",
    description="Returns videos that have been successfully published or sent to TikTok drafts."
)
async def list_history(
    account_id: int, user_id: CurrentUserId, service: StudioDep
) -> list[VideoRead]:
    return await service.list_history(user_id, account_id)


@router.post(
    "",
    response_model=VideoRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new video",
    description="Upload a raw video file. The server saves it locally and creates a `draft` record.",
    responses={
        413: {"description": "Payload Too Large (exceeds max_upload_bytes)"},
        415: {"description": "Unsupported Media Type (not mp4/mov/webm or not a video)"}
    }
)
async def upload(
    account_id: int,
    user_id: CurrentUserId,
    service: StudioDep,
    metadata: Annotated[VideoRequest, Form()],
    file: Annotated[UploadFile, File(description="The video file to upload")],
) -> VideoRead:
    return await service.upload_video(
        user_id,
        account_id,
        filename=file.filename,
        content_type=file.content_type,
        chunks=iter_upload(file),
        title=metadata.title,
        description=metadata.description,
    )


@router.post(
    "/probe-url",
    response_model=VideoProbeRead,
    summary="Inspect a YouTube URL",
    description="Returns metadata (title, duration) and a list of available audio tracks for a YouTube URL. Does not download the video.",
)
async def probe_url(
    account_id: int,
    user_id: CurrentUserId,
    service: StudioDep,
    body: VideoUrlProbeRequest,
) -> VideoProbeRead:
    probe = await service.probe_url(user_id, account_id, url=body.url)
    return VideoProbeRead.model_validate(probe)


@router.post(
    "/from-url",
    response_model=VideoRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start downloading a YouTube video",
    description="Initiates a background download of a YouTube video. Returns immediately with a `downloading` status. Poll the `/import` endpoint to track progress.",
)
async def from_url(
    account_id: int, user_id: CurrentUserId, service: StudioDep, body: VideoUrlRequest
) -> VideoRead:
    return await service.start_import(
        user_id,
        account_id,
        url=body.url,
        audio_language=body.audio_language,
        metadata_language=body.metadata_language,
    )


@router.get(
    "/{video_id}/import",
    response_model=ImportProgress,
    summary="Progress of a YouTube import",
    description="Poll this endpoint after calling `/from-url` to get the current download percentage.",
)
async def import_progress(
    account_id: int, video_id: int, user_id: CurrentUserId, service: StudioDep
) -> ImportProgress:
    return await service.import_progress(user_id, account_id, video_id)


@router.post(
    "/processed",
    response_model=VideoRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload, trim, and change speed",
    description="Uploads a video, runs `ffmpeg` to cut it (`start`/`end`) and change its speed, then saves the result as a draft.",
)
async def upload_processed(
    account_id: int,
    user_id: CurrentUserId,
    service: StudioDep,
    title: str = Form(..., description="Title for the new video"),
    description: str = Form("", description="Description"),
    start: float = Form(0, ge=0, description="Start time in seconds"),
    end: float | None = Form(None, ge=0, description="End time in seconds"),
    speed: float = Form(1.0, ge=0.25, le=4.0, description="Playback speed multiplier"),
    file: UploadFile = File(...),
) -> VideoRead:
    return await service.upload_video_processed(
        user_id,
        account_id,
        filename=file.filename,
        content_type=file.content_type,
        chunks=iter_upload(file),
        title=title,
        description=description,
        start=start,
        end=end,
        speed=speed,
    )


@router.post(
    "/fragments",
    response_model=list[VideoRead],
    status_code=status.HTTP_201_CREATED,
    summary="Upload and cut into fragments",
    description=(
        "Uploads a single video and cuts it into multiple fragments based on the JSON `options`. "
        "Returns a list of created video records (one per enabled fragment)."
    ),
    openapi_extra={
        "requestBody": {
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "options": {
                                "type": "string",
                                "description": "JSON string representing `FragmentsOptions`.",
                                "example": '{"fragments": [{"start": 0, "end": 15, "title": "Part 1", "enabled": true}], "description": "Epic split", "speed": 1.0, "queue": false, "aspect": "original", "zoom": 0.0}'
                            },
                            "file": {"type": "string", "format": "binary"}
                        }
                    }
                }
            }
        }
    }
)
async def upload_fragments(
    account_id: int,
    user_id: CurrentUserId,
    service: StudioDep,
    options: Annotated[str, Form(description="JSON string of FragmentsOptions")],
    file: Annotated[UploadFile, File()],
) -> list[VideoRead]:
    try:
        parsed = FragmentsOptions.model_validate_json(options)
    except ValidationError as exc:
        raise InvalidInputError(exc.errors()[0]["msg"]) from exc
    return await service.upload_fragments(
        user_id,
        account_id,
        filename=file.filename,
        content_type=file.content_type,
        chunks=iter_upload(file),
        options=parsed,
    )


@router.get("/{video_id}", response_model=VideoRead, summary="Get one video")
async def get_video(
    account_id: int, video_id: int, user_id: CurrentUserId, service: StudioDep
) -> VideoRead:
    return await service.get_video(user_id, account_id, video_id)


@router.patch("/{video_id}", response_model=VideoRead, summary="Edit title/description")
async def update_video(
    account_id: int,
    video_id: int,
    user_id: CurrentUserId,
    service: StudioDep,
    payload: VideoUpdateRequest,
) -> VideoRead:
    return await service.update_video(
        user_id, account_id, video_id, title=payload.title, description=payload.description
    )


@router.post(
    "/{video_id}/fragments",
    response_model=list[VideoRead],
    status_code=status.HTTP_201_CREATED,
    summary="Cut an existing draft into fragments",
    description="Cuts an existing local video (e.g., a downloaded YouTube video) into fragments. The original draft is replaced by the new fragments.",
)
async def split_video(
    account_id: int,
    video_id: int,
    user_id: CurrentUserId,
    service: StudioDep,
    body: FragmentsOptions,
) -> list[VideoRead]:
    return await service.split_video(user_id, account_id, video_id, body)


@router.delete(
    "/{video_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a video"
)
async def delete_video(
    account_id: int, video_id: int, user_id: CurrentUserId, service: StudioDep
) -> None:
    await service.delete_video(user_id, account_id, video_id)


@router.get(
    "/{video_id}/file",
    summary="Download the video file",
    response_class=FileResponse,
    description="Streams the raw video file. Supports HTTP Range requests for seeking in the browser."
)
async def download_file(
    account_id: int, video_id: int, user_id: CurrentUserId, service: StudioDep
) -> FileResponse:
    video = await service.get_video(user_id, account_id, video_id)
    if not video.file_name:
        raise VideoNotFoundError("No file for this video")
    path = await service.get_file(user_id, account_id, video.file_name)
    media_type, _ = mimetypes.guess_type(path.name)
    return FileResponse(path, media_type=media_type or "application/octet-stream")