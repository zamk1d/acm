import datetime as dt

from pydantic import BaseModel

from acm.integrations.tiktok import TikTokVideo


class SnapshotPoint(BaseModel):
    at: dt.datetime
    views: int
    likes: int
    comments: int
    shares: int


class VideoAnalytics(BaseModel):
    video: TikTokVideo
    # shares of views, in percent
    engagement_rate: float | None = None
    like_rate: float | None = None
    comment_rate: float | None = None
    share_rate: float | None = None
    age_days: float | None = None
    views_per_day: float | None = None  # lifetime average
    # growth over the last 24h; None until we have a snapshot that old
    views_24h: int | None = None
    likes_24h: int | None = None
    comments_24h: int | None = None
    shares_24h: int | None = None
    history: list[SnapshotPoint] = []


class ChannelTotals(BaseModel):
    """Aggregate over a set of videos (the ones currently loaded in the library)."""

    videos: int = 0
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    engagement_rate: float | None = None
    best_video_id: str | None = None
    best_video_title: str | None = None
    best_video_views: int | None = None
