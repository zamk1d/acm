import uuid
from collections.abc import Sequence

from sqlalchemy import select

from acm.models import TikTokAccount
from acm.repositories.base import BaseRepository


class TikTokAccountRepository(BaseRepository[TikTokAccount]):
    model = TikTokAccount

    async def get_by_open_id(self, open_id: str) -> TikTokAccount | None:
        result = await self._session.execute(
            select(TikTokAccount).where(TikTokAccount.open_id == open_id)
        )
        return result.scalar_one_or_none()

    async def get_for_user(self, user_id: uuid.UUID, account_id: int) -> TikTokAccount:
        """Ownership-checked lookup: returns None for someone else's account."""
        result = await self._session.execute(
            select(TikTokAccount).where(
                TikTokAccount.id == account_id,
                TikTokAccount.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: uuid.UUID) -> Sequence[TikTokAccount]:
        result = await self._session.execute(
            select(TikTokAccount)
            .where(TikTokAccount.user_id == user_id)
            .order_by(TikTokAccount.created_at)
        )
        return result.scalars().all()