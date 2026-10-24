import hashlib
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select

from acm.models.api_token import ApiToken
from acm.repositories.base import BaseRepository


def hash_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode()).hexdigest()


class ApiTokenRepository(BaseRepository[ApiToken]):
    model = ApiToken

    async def list_by_user(self, user_id: uuid.UUID) -> Sequence[ApiToken]:
        result = await self._session.execute(
            select(ApiToken).where(ApiToken.user_id == user_id).order_by(ApiToken.created_at)
        )
        return result.scalars().all()

    async def get_by_plaintext(self, plaintext: str) -> ApiToken | None:
        result = await self._session.execute(
            select(ApiToken).where(ApiToken.token_hash == hash_token(plaintext))
        )
        return result.scalar_one_or_none()

    async def get_for_user(self, user_id: uuid.UUID, token_id: int) -> ApiToken | None:
        result = await self._session.execute(
            select(ApiToken).where(ApiToken.id == token_id, ApiToken.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def touch(self, token: ApiToken) -> None:
        token.last_used_at = datetime.now(UTC)