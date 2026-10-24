from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from acm.api.deps import CurrentUser, SchedulerDep, StudioDep
from acm.api.templating import templates

router = APIRouter(include_in_schema=False, prefix="/studio/{account_id}/schedule")


@router.get("", response_class=HTMLResponse)
async def schedule_page(
    request: Request,
    account_id: int,
    user: CurrentUser,
    scheduler: SchedulerDep,
    studio: StudioDep,
) -> Response:
    plan = await scheduler.get_plan(user.id, account_id)
    queue = await scheduler.list_queue(user.id, account_id)
    workspace = await studio.list_workspace(user.id, account_id)
    return templates.TemplateResponse(
        request,
        "scheduler.html",
        {
            "user": user,
            "account_id": account_id,
            "plan": plan,
            "queue": queue,
            "workspace": workspace,
        },
    )