"""Metrics of videos on TikTok.

TikTok's Display API only returns CURRENT counters (views, likes, comments, shares). Everything
that looks like a trend is built by us from snapshots we take regularly (see snapshot_all()).
"""

import logging
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta

from acm.core.exceptions import AppError
from acm.core.time import ensure_utc, utcnow
from acm.db.uow import UnitOfWork
from acm.integrations.tiktok import TikTokVideo
from acm.integrations.tiktok.scopes import SCOPE_VIDEO_LIST
from acm.models import VideoMetricSnapshot
from acm.schemas.analytics import ChannelTotals, SnapshotPoint, VideoAnalytics
from acm.services.tiktok import TikTokService

logger = logging.getLogger(__name__)

# opening a page may add a snapshot, but not more often than this
PAGE_VIEW_SNAPSHOT_EVERY = timedelta(minutes=15)
# the background job runs hourly; slightly less so that it never skips a round
BACKGROUND_SNAPSHOT_EVERY = timedelta(minutes=50)
SNAPSHOT_PAGES = 3  # 3 * 20 = the newest 60 videos of each channel


def _percent(part: int | None, whole: int | None) -> float | None:
    return None if not whole else (part or 0) / whole * 100


class AnalyticsService:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        accounts: TikTokService,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._uow_factory = uow_factory
        self._accounts = accounts
        self._clock = clock

    # --- one video -------------------------------------------------------------------------

    async def video_analytics(
        self, user_id: uuid.UUID, account_id: int, tiktok_video_id: str
    ) -> VideoAnalytics:
        video = await self._accounts.get_video(user_id, account_id, tiktok_video_id)
        now = self._clock()

        async with self._uow_factory() as uow:
            await self._record(uow, account_id, [video], now, PAGE_VIEW_SNAPSHOT_EVERY)
            await uow.commit()
            history = await uow.snapshots.history(account_id, tiktok_video_id)
            baseline = await uow.snapshots.at_or_before(
                account_id, tiktok_video_id, now - timedelta(hours=24)
            )

        def grew(current: int | None, before: int | None) -> int | None:
            return None if baseline is None else max((current or 0) - (before or 0), 0)

        age_days = None
        if video.created_at is not None:
            age_days = max((now - video.created_at).total_seconds() / 86400, 0)
        views = video.view_count
        return VideoAnalytics(
            video=video,
            engagement_rate=video.engagement_rate,
            like_rate=_percent(video.like_count, views),
            comment_rate=_percent(video.comment_count, views),
            share_rate=_percent(video.share_count, views),
            age_days=age_days,
            views_per_day=(views / max(age_days, 1)) if views is not None and age_days is not None else None,
            views_24h=grew(views, baseline.view_count if baseline else None),
            likes_24h=grew(video.like_count, baseline.like_count if baseline else None),
            comments_24h=grew(video.comment_count, baseline.comment_count if baseline else None),
            shares_24h=grew(video.share_count, baseline.share_count if baseline else None),
            history=[
                SnapshotPoint(
                    at=ensure_utc(s.captured_at),
                    views=s.view_count,
                    likes=s.like_count,
                    comments=s.comment_count,
                    shares=s.share_count,
                )
                for s in history
            ],
        )

    # --- the whole channel -----------------------------------------------------------------

    @staticmethod
    def summarize(videos: Sequence[TikTokVideo]) -> ChannelTotals:
        """Totals over the given videos (pure function: no I/O)."""
        views = sum(v.view_count or 0 for v in videos)
        likes = sum(v.like_count or 0 for v in videos)
        comments = sum(v.comment_count or 0 for v in videos)
        shares = sum(v.share_count or 0 for v in videos)
        best = max(videos, key=lambda v: v.view_count or 0, default=None)
        return ChannelTotals(
            videos=len(videos),
            views=views,
            likes=likes,
            comments=comments,
            shares=shares,
            engagement_rate=_percent(likes + comments + shares, views),
            best_video_id=best.id if best else None,
            best_video_title=(best.title or best.video_description) if best else None,
            best_video_views=best.view_count if best else None,
        )

    # --- background snapshots --------------------------------------------------------------

    async def snapshot_all(self) -> int:
        """Called hourly by the worker: stores the counters of every channel's recent videos."""
        async with self._uow_factory() as uow:
            accounts = [
                (a.id, a.user_id, SCOPE_VIDEO_LIST in a.scopes.split(","))
                for a in await uow.tiktok_accounts.list_all()
            ]
        total = 0
        for account_id, user_id, has_scope in accounts:
            if not has_scope:
                continue
            try:
                total += await self._snapshot_account(user_id, account_id)
            except AppError as exc:  # one broken account must not stop the others
                logger.warning("Snapshot failed account_id=%s: %s", account_id, exc.message)
        return total

    async def _snapshot_account(self, user_id: uuid.UUID, account_id: int) -> int:
        videos: list[TikTokVideo] = []
        cursor: int | None = None
        for _ in range(SNAPSHOT_PAGES):
            page = await self._accounts.list_videos(user_id, account_id, cursor)
            videos += page.videos
            if not page.has_more or page.cursor is None:
                break
            cursor = page.cursor
        async with self._uow_factory() as uow:
            added = await self._record(
                uow, account_id, videos, self._clock(), BACKGROUND_SNAPSHOT_EVERY
            )
            await uow.commit()
        return added

    @staticmethod
    async def _record(
        uow: UnitOfWork,
        account_id: int,
        videos: Sequence[TikTokVideo],
        now: datetime,
        min_age: timedelta,
    ) -> int:
        added = 0
        for video in videos:
            latest = await uow.snapshots.latest(account_id, video.id)
            if latest is not None and now - ensure_utc(latest.captured_at) < min_age:
                continue
            uow.snapshots.add(
                VideoMetricSnapshot(
                    account_id=account_id,
                    tiktok_video_id=video.id,
                    captured_at=now.astimezone(UTC),
                    view_count=video.view_count or 0,
                    like_count=video.like_count or 0,
                    comment_count=video.comment_count or 0,
                    share_count=video.share_count or 0,
                )
            )
            added += 1
        return added
