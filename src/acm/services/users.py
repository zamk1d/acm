import asyncio
import uuid
from collections.abc import Callable

from pwdlib import PasswordHash
from sqlalchemy.exc import IntegrityError

from acm.core.exceptions import EmailTakenError, InvalidCredentialsError, InvalidInputError
from acm.db.uow import UnitOfWork
from acm.models.user import User
from acm.schemas.user import UserRead

# Created once per process: hashing is deliberately slow, we don't want to redo it per request.
_hasher = PasswordHash.recommended()
# Verified against when the email is unknown, so "no such user" takes as long as "wrong password".
_DUMMY_HASH = _hasher.hash("dummy-password-for-constant-time")


def _normalize_email(email: str) -> str:
    return email.strip().lower()


class UserService:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def register(self, email: str, password: str) -> UserRead:
        email = _normalize_email(email)
        if not (3 <= len(email) <= 320) or "@" not in email:
            raise InvalidInputError("Enter a valid email address")
        if not (8 <= len(password) <= 128):
            raise InvalidInputError("Password must be between 8 and 128 characters")

        # argon2 is CPU-heavy: run it in a thread so the event loop isn't blocked
        password_hash = await asyncio.to_thread(_hasher.hash, password)

        async with self._uow_factory() as uow:
            if await uow.users.get_by_email(email):
                raise EmailTakenError()
            user = User(email=email, password_hash=password_hash)
            uow.users.add(user)
            try:
                await uow.commit()
            except IntegrityError as exc:  # two simultaneous registrations with the same email
                raise EmailTakenError() from exc
            return UserRead.model_validate(user)

    async def authenticate(self, email: str, password: str) -> UserRead:
        email = _normalize_email(email)

        async with self._uow_factory() as uow:
            user = await uow.users.get_by_email(email)
            stored_hash = user.password_hash if user else _DUMMY_HASH
            user_read = UserRead.model_validate(user) if user else None

        password_ok = await asyncio.to_thread(_hasher.verify, password, stored_hash)
        if user_read is None or not password_ok:
            raise InvalidCredentialsError()
        return user_read

    async def get_by_id(self, user_id: uuid.UUID) -> UserRead | None:
        async with self._uow_factory() as uow:
            user = await uow.users.get(user_id)
            return UserRead.model_validate(user) if user else None