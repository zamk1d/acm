from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from acm.repositories.metric_snapshot import MetricSnapshotRepository
from acm.repositories.publish_plan import PublishPlanRepository
from acm.repositories.tiktok_account import TikTokAccountRepository
from acm.repositories.user import UserRepository
from acm.repositories.video import VideoRepository


class UnitOfWork:
    """One transaction scope. Owns the session and exposes repositories bound to it."""

    users: UserRepository
    tiktok_accounts: TikTokAccountRepository
    videos: VideoRepository
    plans: PublishPlanRepository
    snapshots: MetricSnapshotRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        self.users = UserRepository(self._session)
        self.tiktok_accounts = TikTokAccountRepository(self._session)
        self.videos = VideoRepository(self._session)
        self.plans = PublishPlanRepository(self._session)
        self.snapshots = MetricSnapshotRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if exc_type is not None:
                await self._session.rollback()
        finally:
            await self._session.close()

    async def commit(self) -> None:
        await self._session.commit()
