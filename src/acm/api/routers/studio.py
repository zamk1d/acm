import logging
import mimetypes

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

from acm.api.deps import (
    AnalyticsDep,
    CurrentUser,
    CurrentUserId,
    StudioDep,
    TikTokServiceDep,
)
from acm.api.templating import templates
from acm.core.exceptions import AppError
from acm.integrations.tiktok import TikTokVideoPage

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


# src/acm/api/routers/studio.py

# ... импорты ...

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
            "history_json": [], # Пустая история для драфтов
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
            # Передаем историю как список словарей для Chart.js
            "history_json": [p.model_dump(mode="json") for p in data.history],
        },
    )


@router.get("/files/{file_name}")
async def draft_file(
    account_id: int,
    file_name: str,
    user_id: CurrentUserId,
    service: StudioDep,
) -> FileResponse:
    path = await service.get_file(user_id, account_id, file_name)
    media_type, _ = mimetypes.guess_type(path.name)
    # No `filename=`: that would add "Content-Disposition: attachment" and force a download.
    # Without it the browser plays the video inline; Range requests (seeking) work out of the box.
    return FileResponse(path, media_type=media_type or "application/octet-stream")