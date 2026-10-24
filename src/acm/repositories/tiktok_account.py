import uuid

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

    async def list_by_user(self, user_id: uuid.UUID) -> list[TikTokAccount]:
        result = await self._session.execute(
            select(TikTokAccount).where(TikTokAccount.user_id == user_id)
        )
        return list(result.scalars().all())