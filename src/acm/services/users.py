import logging
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta

from pwdlib import PasswordHash

from acm.core.exceptions import AccountNotFoundError, UpstreamError, EmailTakenError, InvalidCredentialsError
from acm.core.time import utcnow
from acm.db.uow import UnitOfWork
from acm.integrations.tiktok import TikTokClient, TikTokUser, TokenResponse
from acm.integrations.tiktok.scopes import fields_for_scopes
from acm.models import TikTokAccount
from acm.models.user import User
from acm.schemas.account import AccountRead
from acm.schemas.user import UserRead

logger = logging.getLogger(__name__)

class UserService:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
    ) -> None:
        self._uow_factory = uow_factory
        self._hasher = PasswordHash.recommended()

    async def register(self, email: str, password: str) -> UserRead:
        async with self._uow_factory() as uow:
            if await uow.users.get_by_email(email):
                raise EmailTakenError()
            user = User(email=email, password_hash=self._hasher.hash(password))
            uow.users.add(user)
            await uow.commit()
            return UserRead.model_validate(user)

    async def authenticate(self, email: str, password: str) -> UserRead:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_email(email)
            if user is None or not self._hasher.verify(password, user.password_hash):
                raise InvalidCredentialsError()
            return UserRead.model_validate(user)