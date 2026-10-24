import logging
import mimetypes
from typing import Annotated

from fastapi import APIRouter, Body, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response

from acm.api.deps import (
    AnalyticsDep,
    CurrentUser,
    CurrentUserId,
    PublishingDep,
    StudioDep,
    TikTokServiceDep,
)
from acm.api.templating import templates
from acm.api.uploads import iter_upload
from acm.core.exceptions import AppError
from acm.integrations.tiktok import TikTokVideoPage
from acm.schemas.publishing import PublishMethod, PublishOptions
from acm.schemas.video import VideoRead, VideoRequest, VideoUpdateRequest

router = APIRouter(include_in_schema=False, prefix="/studio/{account_id}")
logger = logging.getLogger(__name__)


@router.get("", response_class=HTMLResponse)
async def studio_page(
    request: Request,
    account_id: int,
    user: CurrentUser,
    studio: StudioDep,
    tiktok: TikTokServiceDep,
) -> Response:
    # also verifies the account belongs to this user (404 otherwise)
    workspace = await studio.list_workspace(user.id, account_id)
    history = await studio.list_history(user.id, account_id, limit=6)

    videos, videos_error = TikTokVideoPage(), None
    try:
        videos = await tiktok.list_videos(user.id, account_id)
    except AppError as exc:
        logger.warning("Could not load TikTok videos: %s", exc.message)
        videos_error = exc.message

    return templates.TemplateResponse(
        request,
        "studio.html",
        {
            "user": user,
            "account_id": account_id,
            "workspace": workspace,
            "history": history,
            "videos": videos,
            "videos_error": videos_error,
        },
    )


@router.get("/videos/list")
async def list_videos(
    account_id: int,
    user_id: CurrentUserId,
    tiktok: TikTokServiceDep,
    cursor: int | None = None,
) -> TikTokVideoPage:
    return await tiktok.list_videos(user_id, account_id, cursor)


@router.get("/creative", response_class=HTMLResponse)
async def creative_studio(
    request: Request,
    account_id: int,
    user: CurrentUser,
    tiktok: TikTokServiceDep,
    studio: StudioDep,
    id: int | None = None,
) -> Response:
    await tiktok.get_account(user.id, account_id)  # ownership check
    video = await studio.get_video(user.id, account_id, id) if id is not None else None
    return templates.TemplateResponse(
        request,
        "creative_studio.html",
        {"user": user, "account_id": account_id, "video": video},
    )


@router.post("/creative/upload", status_code=201)
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


@router.post("/videos/{video_id}/update")
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


@router.post("/videos/{video_id}/delete", status_code=204)
async def delete_video(
    account_id: int,
    video_id: int,
    user_id: CurrentUserId,
    service: StudioDep,
) -> Response:
    await service.delete_video(user_id, account_id, video_id)
    return Response(status_code=204)


@router.get("/files/{file_name}")
async def draft_file(
    account_id: int,
    file_name: str,
    user_id: CurrentUserId,
    service: StudioDep,
) -> FileResponse:
    path = await service.get_file(user_id, account_id, file_name)
    media_type, _ = mimetypes.guess_type(path.name)
    return FileResponse(path, media_type=media_type or "application/octet-stream")


@router.post("/videos/{video_id}/post")
async def post_to_drafts(
    account_id: int,
    video_id: int,
    user_id: CurrentUserId,
    service: PublishingDep,
) -> VideoRead:
    return await service.start(
        user_id, account_id, video_id, PublishOptions(method=PublishMethod.DRAFT)
    )


@router.post("/videos/{video_id}/publish")
async def direct_post(
    account_id: int,
    video_id: int,
    user_id: CurrentUserId,
    service: PublishingDep,
    options: PublishOptions | None = Body(default=None),
) -> VideoRead:
    if options is None:
        options = PublishOptions(method=PublishMethod.DIRECT, privacy_level="SELF_ONLY")
    return await service.start(user_id, account_id, video_id, options)


@router.get("/videos/{video_id}/state")
async def video_state(
    account_id: int,
    video_id: int,
    user_id: CurrentUserId,
    service: StudioDep,
) -> VideoRead:
    return await service.get_video(user_id, account_id, video_id)


@router.get("/videos/{video_id}", response_class=HTMLResponse)
async def draft_analytics(
    request: Request,
    account_id: int,
    video_id: int,
    user: CurrentUser,
    studio: StudioDep,
) -> Response:
    video = await studio.get_video(user.id, account_id, video_id)
    return templates.TemplateResponse(
        request,
        "video_analytics.html",
        {
            "user": user,
            "account_id": account_id,
            "video": video,
            "tiktok_video_id": None,
            "analytics": None,
        },
    )


@router.get("/tiktok/{tiktok_video_id}", response_class=HTMLResponse)
async def tiktok_video_analytics(
    request: Request,
    account_id: int,
    tiktok_video_id: str,
    user: CurrentUser,
    analytics: AnalyticsDep,
) -> Response:
    data = await analytics.video_analytics(user.id, account_id, tiktok_video_id)
    return templates.TemplateResponse(
        request,
        "video_analytics.html",
        {
            "user": user,
            "account_id": account_id,
            "video": None,
            "tiktok_video_id": tiktok_video_id,
            "analytics": data,
        },
    )