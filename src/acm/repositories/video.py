from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, func, or_, select, update

from acm.models.video import ACTIVE_STATUSES, DONE_STATUSES, Video, VideoStatus
from acm.repositories.base import BaseRepository


def _values(statuses: Iterable[VideoStatus]) -> list[str]:
    return [s.value for s in statuses]


class VideoRepository(BaseRepository[Video]):
    """Queries only. Who may see which account is decided by the service, not here."""

    model = Video

    async def get_in_account(self, account_id: int, video_id: int) -> Video | None:
        result = await self._session.execute(
            select(Video).where(Video.account_id == account_id, Video.id == video_id)
        )
        return result.scalar_one_or_none()

    async def get_by_file_name(self, account_id: int, file_name: str) -> Video | None:
        result = await self._session.execute(
            select(Video).where(Video.account_id == account_id, Video.file_name == file_name)
        )
        return result.scalar_one_or_none()

    async def list_active(self, account_id: int) -> Sequence[Video]:
        """Everything not yet delivered to TikTok, newest first."""
        result = await self._session.execute(
            select(Video)
            .where(Video.account_id == account_id, Video.status.in_(_values(ACTIVE_STATUSES)))
            .order_by(Video.created_at.desc(), Video.id.desc())
        )
        return result.scalars().all()

    async def list_done(self, account_id: int, limit: int = 10) -> Sequence[Video]:
        result = await self._session.execute(
            select(Video)
            .where(Video.account_id == account_id, Video.status.in_(_values(DONE_STATUSES)))
            .order_by(Video.published_at.desc(), Video.id.desc())
            .limit(limit)
        )
        return result.scalars().all()

    # --- queue (scheduler) -----------------------------------------------------------------

    async def list_queue(self, account_id: int) -> Sequence[Video]:
        result = await self._session.execute(
            select(Video)
            .where(Video.account_id == account_id, Video.status == VideoStatus.QUEUED.value)
            .order_by(Video.queue_position, Video.id)
        )
        return result.scalars().all()

    async def queue_head(self, account_id: int) -> Video | None:
        queue = await self.list_queue(account_id)
        return queue[0] if queue else None

    async def next_queue_position(self, account_id: int) -> int:
        result = await self._session.execute(
            select(func.max(Video.queue_position)).where(
                Video.account_id == account_id, Video.status == VideoStatus.QUEUED.value
            )
        )
        return (result.scalar_one_or_none() or 0) + 1

    # --- atomic state transitions ------------------------------------------------------------
    # Plain UPDATE ... WHERE status IN (...) so that two concurrent requests can't both win.

    async def claim(
        self,
        account_id: int,
        video_id: int,
        *,
        from_statuses: Iterable[VideoStatus],
        values: dict[str, Any],
    ) -> bool:
        result = await self._session.execute(
            update(Video)
            .where(
                Video.account_id == account_id,
                Video.id == video_id,
                Video.status.in_(_values(from_statuses)),
            )
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        return cast("CursorResult[Any]", result).rowcount == 1

    async def claim_due_publishing(self, now: datetime, lock_until: datetime, limit: int) -> list[int]:
        """Videos whose publishing job needs a step now. Locks them so nobody else takes them."""
        result = await self._session.execute(
            select(Video.id)
            .where(
                Video.status == VideoStatus.PUBLISHING.value,
                or_(Video.locked_until.is_(None), Video.locked_until <= now),
            )
            .order_by(Video.id)
            .limit(limit)
        )
        claimed: list[int] = []
        for video_id in result.scalars().all():
            locked = await self._session.execute(
                update(Video)
                .where(
                    Video.id == video_id,
                    Video.status == VideoStatus.PUBLISHING.value,
                    or_(Video.locked_until.is_(None), Video.locked_until <= now),
                )
                .values(locked_until=lock_until)
                .execution_options(synchronize_session=False)
            )
            if cast("CursorResult[Any]", locked).rowcount == 1:
                claimed.append(video_id)
        return claimed
