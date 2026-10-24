import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from acm.db.base import Base


class BaseRepository[ModelT: Base]:
    """Generic persistence operations. Subclasses set `model`."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, entity_id: uuid.UUID) -> ModelT | None:
        return await self._session.get(self.model, entity_id)

    def add(self, entity: ModelT) -> None:
        self._session.add(entity)

    async def delete(self, entity: ModelT) -> None:
        await self._session.delete(entity)
