from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, select, update

from acm.models.publish_plan import PublishPlan
from acm.repositories.base import BaseRepository


class PublishPlanRepository(BaseRepository[PublishPlan]):
    model = PublishPlan

    async def get_by_account(self, account_id: int) -> PublishPlan | None:
        result = await self._session.execute(
            select(PublishPlan).where(PublishPlan.account_id == account_id)
        )
        return result.scalar_one_or_none()

    async def list_due(self, now: datetime) -> list[PublishPlan]:
        result = await self._session.execute(
            select(PublishPlan).where(
                PublishPlan.enabled.is_(True),
                PublishPlan.next_run_at.is_not(None),
                PublishPlan.next_run_at <= now,
            )
        )
        return list(result.scalars().all())

    async def claim_run(
        self, plan_id: int, expected_next_run_at: datetime, new_next_run_at: datetime | None, now: datetime
    ) -> bool:
        """Moves `next_run_at` forward iff nobody else did it first (optimistic lock)."""
        result = await self._session.execute(
            update(PublishPlan)
            .where(PublishPlan.id == plan_id, PublishPlan.next_run_at == expected_next_run_at)
            .values(next_run_at=new_next_run_at, last_run_at=now)
            .execution_options(synchronize_session=False)
        )
        return cast("CursorResult[Any]", result).rowcount == 1
