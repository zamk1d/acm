from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from acm.api.deps import CurrentUser, TikTokServiceDep
from acm.api.session import USER_ID_KEY
from acm.api.templating import templates

router = APIRouter(include_in_schema=False)


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> Response:
    if request.session.get(USER_ID_KEY):
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(request, "index.html", {})


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request, user: CurrentUser, tiktok: TikTokServiceDep
) -> Response:
    accounts = await tiktok.list_accounts(user.id)
    return templates.TemplateResponse(
        request, "dashboard.html", {"user": user, "accounts": accounts}
    )