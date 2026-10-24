from typing import Annotated
import asyncio
import tempfile
from pathlib import Path


from fastapi import APIRouter, File, Form, UploadFile, status
from fastapi.responses import FileResponse
import mimetypes

from acm.api.deps import CurrentUserId, StudioDep
from acm.api.uploads import iter_upload
from acm.schemas.video import VideoRead, VideoRequest, VideoUpdateRequest

router = APIRouter(prefix="/accounts/{account_id}/videos", tags=["Videos"])


@router.get("", response_model=list[VideoRead], summary="List workspace videos")
async def list_workspace(
    account_id: int, user_id: CurrentUserId, service: StudioDep
) -> list[VideoRead]:
    return await service.list_workspace(user_id, account_id)


@router.get("/history", response_model=list[VideoRead], summary="List recently delivered videos")
async def list_history(
    account_id: int, user_id: CurrentUserId, service: StudioDep
) -> list[VideoRead]:
    return await service.list_history(user_id, account_id)


@router.post(
    "",
    response_model=VideoRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new video",
)
async def upload(
    account_id: int,
    user_id: CurrentUserId,
    service: StudioDep,
    metadata: Annotated[VideoRequest, Form()],
    file: Annotated[UploadFile, File()],
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
        user_id, account_id, video_id,
        title=payload.title, description=payload.description,
    )


@router.delete(
    "/{video_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a video",
)
async def delete_video(
    account_id: int, video_id: int, user_id: CurrentUserId, service: StudioDep
):
    await service.delete_video(user_id, account_id, video_id)


@router.get(
    "/{video_id}/file",
    summary="Download the video file",
    response_class=FileResponse,
)
async def download_file(
    account_id: int, video_id: int, user_id: CurrentUserId, service: StudioDep
):
    video = await service.get_video(user_id, account_id, video_id)
    if not video.file_name:
        from acm.core.exceptions import VideoNotFoundError

        raise VideoNotFoundError("No file for this video")
    path = await service.get_file(user_id, account_id, video.file_name)
    media_type, _ = mimetypes.guess_type(path.name)
    return FileResponse(path, media_type=media_type or "application/octet-stream")


@router.post(
    "/processed",
    response_model=VideoRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a video, trim and change speed with ffmpeg",
)
async def upload_processed(
    account_id: int,
    user_id: CurrentUserId,
    service: StudioDep,
    title: str = Form(...),
    description: str = Form(""),
    start: float = Form(0, ge=0),
    end: float | None = Form(None, ge=0),
    speed: float = Form(1.0, ge=0.25, le=4.0),
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