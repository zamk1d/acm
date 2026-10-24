from fastapi import APIRouter, status

from acm.api.deps import CurrentUserId, SchedulerDep
from acm.schemas.schedule import PlanRead, PlanRequest, QueueOrder, SchedulePreview
from acm.schemas.video import VideoRead

router = APIRouter(prefix="/accounts/{account_id}/schedule", tags=["Scheduler"])


@router.get("", response_model=PlanRead, summary="Get the auto-publish plan")
async def get_plan(
    account_id: int, user_id: CurrentUserId, scheduler: SchedulerDep
) -> PlanRead:
    return await scheduler.get_plan(user_id, account_id)


@router.put("", response_model=PlanRead, summary="Save the auto-publish plan")
async def save_plan(
    account_id: int, user_id: CurrentUserId, scheduler: SchedulerDep, body: PlanRequest
) -> PlanRead:
    return await scheduler.save_plan(user_id, account_id, body)


@router.post("/preview", response_model=SchedulePreview, summary="Preview upcoming slots")
async def preview(
    account_id: int, user_id: CurrentUserId, scheduler: SchedulerDep, body: PlanRequest
) -> SchedulePreview:
    return await scheduler.preview(user_id, account_id, body)


@router.get("/queue", response_model=list[VideoRead], summary="List queued videos")
async def list_queue(
    account_id: int, user_id: CurrentUserId, scheduler: SchedulerDep
) -> list[VideoRead]:
    return await scheduler.list_queue(user_id, account_id)


@router.post(
    "/queue/{video_id}",
    response_model=VideoRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add a video to the queue",
)
async def enqueue(
    account_id: int, video_id: int, user_id: CurrentUserId, scheduler: SchedulerDep
) -> VideoRead:
    return await scheduler.enqueue(user_id, account_id, video_id)


@router.delete(
    "/queue/{video_id}",
    response_model=VideoRead,
    summary="Remove a video from the queue",
)
async def dequeue(
    account_id: int, video_id: int, user_id: CurrentUserId, scheduler: SchedulerDep
) -> VideoRead:
    return await scheduler.dequeue(user_id, account_id, video_id)


@router.put("/queue", response_model=list[VideoRead], summary="Reorder the queue")
async def reorder(
    account_id: int,
    user_id: CurrentUserId,
    scheduler: SchedulerDep,
    body: QueueOrder,
) -> list[VideoRead]:
    return await scheduler.reorder_queue(user_id, account_id, body.ids)