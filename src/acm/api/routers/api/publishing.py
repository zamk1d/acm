from fastapi import APIRouter, Body

from acm.api.deps import CurrentUserId, PublishingDep
from acm.schemas.publishing import PublishMethod, PublishOptions
from acm.schemas.video import VideoRead

router = APIRouter(prefix="/accounts/{account_id}/videos/{video_id}", tags=["Publishing"])


@router.post("/drafts", response_model=VideoRead, summary="Send video to TikTok drafts")
async def post_to_drafts(
    account_id: int,
    video_id: int,
    user_id: CurrentUserId,
    service: PublishingDep,
) -> VideoRead:
    return await service.start(
        user_id, account_id, video_id, PublishOptions(method=PublishMethod.DRAFT)
    )


@router.post("/publish", response_model=VideoRead, summary="Direct post to TikTok")
async def publish_direct(
    account_id: int,
    video_id: int,
    user_id: CurrentUserId,
    service: PublishingDep,
    options: PublishOptions | None = Body(default=None),
) -> VideoRead:
    if options is None:
        options = PublishOptions(method=PublishMethod.DIRECT, privacy_level="SELF_ONLY")
    return await service.start(user_id, account_id, video_id, options)