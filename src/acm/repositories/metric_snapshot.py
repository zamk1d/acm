from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select

from acm.models.metric_snapshot import VideoMetricSnapshot
from acm.repositories.base import BaseRepository


class MetricSnapshotRepository(BaseRepository[VideoMetricSnapshot]):
    model = VideoMetricSnapshot

    async def latest(self, account_id: int, tiktok_video_id: str) -> VideoMetricSnapshot | None:
        result = await self._session.execute(
            select(VideoMetricSnapshot)
            .where(
                VideoMetricSnapshot.account_id == account_id,
                VideoMetricSnapshot.tiktok_video_id == tiktok_video_id,
            )
            .order_by(VideoMetricSnapshot.captured_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def at_or_before(
        self, account_id: int, tiktok_video_id: str, moment: datetime
    ) -> VideoMetricSnapshot | None:
        """The newest snapshot taken no later than `moment` (baseline for "last 24h" growth)."""
        result = await self._session.execute(
            select(VideoMetricSnapshot)
            .where(
                VideoMetricSnapshot.account_id == account_id,
                VideoMetricSnapshot.tiktok_video_id == tiktok_video_id,
                VideoMetricSnapshot.captured_at <= moment,
            )
            .order_by(VideoMetricSnapshot.captured_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def history(
        self, account_id: int, tiktok_video_id: str, limit: int = 500
    ) -> Sequence[VideoMetricSnapshot]:
        result = await self._session.execute(
            select(VideoMetricSnapshot)
            .where(
                VideoMetricSnapshot.account_id == account_id,
                VideoMetricSnapshot.tiktok_video_id == tiktok_video_id,
            )
            .order_by(VideoMetricSnapshot.captured_at.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))  # oldest first, for charts
