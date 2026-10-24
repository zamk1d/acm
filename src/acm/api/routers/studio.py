import logging
import mimetypes
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response

from acm.api.deps import CurrentUser, CurrentUserId, StudioDep, TikTokServiceDep, SettingsDep
from acm.api.templating import templates
from acm.api.uploads import iter_upload
from acm.core.exceptions import AppError
from acm.integrations.tiktok import TikTokVideoPage
from acm.schemas.tiktok import TikTokVideoPostRequest
from acm.schemas.video import VideoDetailRead, VideoRead, VideoRequest, VideoUpdateRequest

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
    # also verifies that the account belongs to this user (404 otherwise)
    drafts = await studio.list_drafts(user.id, account_id)

    # TikTok being down / missing video.list scope must not break the whole page
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
            "drafts": drafts,
            "videos": videos,
            "videos_error": videos_error,
            "error": None,
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
        {"user": user, "account_id": account_id, "video": video, "error": None},
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
        user_id,
        account_id,
        video_id,
        title=payload.title,
        description=payload.description,
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



@router.get("/videos/{video_id}", response_class=HTMLResponse)
async def video_analytics(
    request: Request,
    account_id: int,
    video_id: int,
    user: CurrentUser,
    service: StudioDep,
) -> Response:
    video = await service.get_video(user.id, account_id, video_id)
    return templates.TemplateResponse(
        request,
        "video_analytics.html",
        {"user": user, "account_id": account_id, "video": video, "tiktok_video_id": None},
    )


@router.get("/tiktok/{tiktok_video_id}", response_class=HTMLResponse)
async def tiktok_video_analytics(
    request: Request,
    account_id: int,
    tiktok_video_id: str,
    user: CurrentUser,
    tiktok: TikTokServiceDep,
) -> Response:
    await tiktok.get_account(user.id, account_id)  # ownership check
    # TODO: fetch full metadata + insights from TikTok API when the scope is granted.
    return templates.TemplateResponse(
        request,
        "video_analytics.html",
        {
            "user": user,
            "account_id": account_id,
            "video": None,
            "tiktok_video_id": tiktok_video_id,
        },
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

@router.get("/files/{file_name}")
async def draft_file(
    account_id: int,
    file_name: str,
    user_id: CurrentUserId,
    service: StudioDep,
) -> FileResponse:
    path = await service.get_draft_file(user_id, account_id, file_name)
    media_type, _ = mimetypes.guess_type(path.name)
    # No `filename=`: that would add "Content-Disposition: attachment" and force a download.
    # Without it the browser plays the video inline; Range requests (seeking) work out of the box.
    return FileResponse(path, media_type=media_type or "application/octet-stream")

@router.post("/videos/{video_id}/post")
async def post_video_to_drafts(
    account_id: int,
    user_id: CurrentUserId,
    service: TikTokServiceDep,
    video_id: int,
) -> VideoRead:
    return await service.post_video_draft(
        user_id=user_id, account_id=account_id, video_id=video_id
    )

@router.post("/videos/{video_id}/publish")
async def publish_video(
        account_id: int,
        user_id: CurrentUserId,
        service: TikTokServiceDep,
        video_id: int,
        video_data: TikTokVideoPostRequest
):
    return await service.publish_video(user_id=user_id, account_id=account_id, video_id=video_id, video_data=video_data)