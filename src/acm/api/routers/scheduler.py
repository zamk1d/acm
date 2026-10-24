from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from acm.api.deps import CurrentUser, CurrentUserId, SchedulerDep, StudioDep
from acm.api.templating import templates
from acm.schemas.schedule import PlanRead, PlanRequest, QueueOrder, SchedulePreview
from acm.schemas.video import VideoRead

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


@router.get("/plan")
async def get_plan(
    account_id: int, user_id: CurrentUserId, scheduler: SchedulerDep
) -> PlanRead:
    return await scheduler.get_plan(user_id, account_id)


@router.post("/plan")
async def save_plan(
    account_id: int,
    user_id: CurrentUserId,
    scheduler: SchedulerDep,
    payload: PlanRequest,
) -> PlanRead:
    return await scheduler.save_plan(user_id, account_id, payload)


@router.post("/preview")
async def preview(
    account_id: int,
    user_id: CurrentUserId,
    scheduler: SchedulerDep,
    payload: PlanRequest,
) -> SchedulePreview:
    return await scheduler.preview(user_id, account_id, payload)


@router.post("/queue/{video_id}/enqueue")
async def enqueue(
    account_id: int, video_id: int, user_id: CurrentUserId, scheduler: SchedulerDep
) -> VideoRead:
    return await scheduler.enqueue(user_id, account_id, video_id)


@router.post("/queue/{video_id}/dequeue")
async def dequeue(
    account_id: int, video_id: int, user_id: CurrentUserId, scheduler: SchedulerDep
) -> VideoRead:
    return await scheduler.dequeue(user_id, account_id, video_id)


@router.post("/queue/order")
async def reorder(
    account_id: int,
    user_id: CurrentUserId,
    scheduler: SchedulerDep,
    payload: QueueOrder,
) -> list[VideoRead]:
    return await scheduler.reorder_queue(user_id, account_id, payload.ids)