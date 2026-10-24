import re
from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, Response

from acm.api.deps import CurrentUser, SchedulerDep, StudioDep
from acm.api.templating import templates

router = APIRouter(include_in_schema=False, prefix="/studio/{account_id}/schedule")

# Only same-site creative-studio URLs are accepted as a "go back here" target (no open redirect).
_RETURN_RE = re.compile(r"^/studio/\d+/creative(\?[A-Za-z0-9=&._%-]*)?$")


@router.get("", response_class=HTMLResponse)
async def schedule_page(
    request: Request,
    account_id: int,
    user: CurrentUser,
    scheduler: SchedulerDep,
    studio: StudioDep,
    return_to: Annotated[str | None, Query(alias="return")] = None,
) -> Response:
    plan = await scheduler.get_plan(user.id, account_id)
    queue = await scheduler.list_queue(user.id, account_id)
    workspace = await studio.list_workspace(user.id, account_id)
    return_url = (
        return_to
        if return_to
        and _RETURN_RE.fullmatch(return_to)
        and return_to.startswith(f"/studio/{account_id}/creative")
        else None
    )
    return templates.TemplateResponse(
        request,
        "scheduler.html",
        {
            "user": user,
            "account_id": account_id,
            "plan": plan,
            "queue": queue,
            "workspace": workspace,
            "return_url": return_url,
        },
    )