import uuid
from typing import Annotated

from fastapi import Depends, Request

from acm.api.session import ACCOUNT_ID_KEY, USER_ID_KEY
from acm.core.exceptions import NotAuthenticatedError
from acm.db.uow import UnitOfWork
from acm.integrations.tiktok import TikTokClient
from acm.schemas.account import AccountRead
from acm.services.auth import AuthService


def get_auth_service(request: Request) -> AuthService:
    state = request.app.state
    tiktok: TikTokClient = state.tiktok_client
    return AuthService(
        uow_factory=lambda: UnitOfWork(state.session_factory),
        tiktok=tiktok,
    )


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def get_current_user_id(request: Request) -> uuid.UUID:
    raw = request.session.get(USER_ID_KEY)
    if not raw:
        raise NotAuthenticatedError()
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        request.session.clear()
        raise NotAuthenticatedError() from exc


CurrentAccountId = Annotated[uuid.UUID, Depends(get_current_user_id)]


async def get_current_account(account_id: CurrentAccountId, service: AuthServiceDep) -> AccountRead:
    return await service.get_account(account_id)


CurrentAccount = Annotated[AccountRead, Depends(get_current_account)]
