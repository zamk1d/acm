import logging
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
import mimetypes
from fastapi.responses import FileResponse
from acm.api.deps import CurrentUser, StudioDep, CurrentUserId
from acm.api.templating import templates
from acm.schemas.video import VideoRequest, VideoRead

router = APIRouter(include_in_schema=False, prefix="/studio/{account_id}")

logger = logging.getLogger(__name__)

@router.get("", response_class=HTMLResponse)
async def studio_page(
    request: Request,
    account_id: int,
    user: CurrentUser,
    service: StudioDep,
) -> Response:

    videos = await service.get_tiktok_videos_list(account_id=account_id, user_id=user.id)

    drafts = await service.get_videos_list(account_id=account_id, user_id=user.id)

    return templates.TemplateResponse(
        request=request,
        name="studio.html",
        context={
            "user": user,
            "account_id": account_id,
            "drafts": drafts,
            "videos": videos,
            "error": None,
        },
    )

@router.get("/videos/list")
async def list_videos(
        account_id: int,
        user_id: CurrentUserId,
        service: StudioDep
):
    data = await service.get_tiktok_videos_list(account_id=account_id, user_id=user_id)
    logger.info("data: %s", data)
    return data


@router.post("/creative/upload")
async def upload(
    account_id: int,
    user: CurrentUser,
    service: StudioDep,
    metadata: Annotated[VideoRequest, Form()],
    file: UploadFile = File(...),
) -> VideoRead:
    return await service.upload_video(
        account_id=account_id,
        title=metadata.title,
        desc=metadata.description,
        file=file,
    )

@router.get("/creative", response_class=HTMLResponse)
async def creative_studio(
        request: Request,
        account_id: int,
        user: CurrentUser,
        service: StudioDep,
):
    return templates.TemplateResponse(
        request=request,
        name="creative_studio.html",
        context={
            "user": user,
            "account_id": account_id,
            "error": None,
        },
    )

@router.get("/files/{file_name}")
async def draft_file(
    account_id: int,
    file_name: str,
    user: CurrentUser,
    service: StudioDep,
):
    path = await service.get_draft_file(account_id, user.id, file_name)
    media_type, _ = mimetypes.guess_type(path.name)
    return FileResponse(
        path,
        media_type=media_type or "application/octet-stream",
        filename=path.name,
    )