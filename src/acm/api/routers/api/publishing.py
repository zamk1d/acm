from fastapi import APIRouter, Body
from acm.api.deps import CurrentUserId, PublishingDep
from acm.schemas.publishing import PublishMethod, PublishOptions
from acm.schemas.video import VideoRead

router = APIRouter(prefix="/accounts/{account_id}/videos/{video_id}", tags=["Publishing"])

@router.post(
    "/drafts",
    response_model=VideoRead,
    summary="Send video to TikTok drafts",
    description="Moves the local video to the background worker queue. The worker will upload it to TikTok's inbox (drafts). Requires the `video.upload` scope."
)
async def post_to_drafts(
    account_id: int, video_id: int, user_id: CurrentUserId, service: PublishingDep,
) -> VideoRead:
    return await service.start(user_id, account_id, video_id, PublishOptions(method=PublishMethod.DRAFT))

@router.post(
    "/publish",
    response_model=VideoRead,
    summary="Direct post to TikTok",
    description=(
        "Publishes the video directly to the creator's profile. "
        "Requires the `video.publish` scope. For unaudited apps, TikTok enforces `SELF_ONLY` "
        "and the creator's account must be private."
    ),
    responses={
        400: {"description": "Invalid options (e.g., missing privacy_level, or unauthorized privacy)"},
        403: {"description": "Missing video.publish scope"}
    }
)
async def publish_direct(
    account_id: int, video_id: int, user_id: CurrentUserId, service: PublishingDep,
    options: PublishOptions | None = Body(default=None, description="Options for publishing. Defaults to SELF_ONLY if omitted."),
) -> VideoRead:
    if options is None:
        options = PublishOptions(method=PublishMethod.DIRECT, privacy_level="SELF_ONLY")
    return await service.start(user_id, account_id, video_id, options)