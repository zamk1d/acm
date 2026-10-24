from fastapi import APIRouter

from acm.api.deps import AnalyticsDep, CurrentUser, CurrentUserId, TikTokServiceDep
from acm.schemas.analytics import ChannelTotals, VideoAnalytics
from acm.integrations.tiktok import TikTokVideoPage

router = APIRouter(prefix="/accounts/{account_id}/analytics", tags=["Analytics"])


@router.get("/channel", response_model=ChannelTotals, summary="Channel totals")
async def channel_totals(
    account_id: int, user_id: CurrentUserId, tiktok: TikTokServiceDep, analytics: AnalyticsDep
) -> ChannelTotals:
    page = await tiktok.list_videos(user_id, account_id)
    return analytics.summarize(page.videos)


@router.get("/videos", response_model=TikTokVideoPage, summary="List TikTok videos with metrics")
async def list_tiktok_videos(
    account_id: int,
    user_id: CurrentUserId,
    tiktok: TikTokServiceDep,
    cursor: int | None = None,
) -> TikTokVideoPage:
    return await tiktok.list_videos(user_id, account_id, cursor)


@router.get(
    "/videos/{tiktok_video_id}",
    response_model=VideoAnalytics,
    summary="Analytics for one TikTok video",
)
async def video_analytics(
    account_id: int, tiktok_video_id: str, user: CurrentUser, analytics: AnalyticsDep
) -> VideoAnalytics:
    return await analytics.video_analytics(user.id, account_id, tiktok_video_id)