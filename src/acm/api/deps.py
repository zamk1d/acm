import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request

from acm.api.session import USER_ID_KEY
from acm.core.exceptions import NotAuthenticatedError
from acm.db.uow import UnitOfWork
from acm.schemas.user import UserRead
from acm.services.studio import StudioService
from acm.services.tiktok import TikTokService
from acm.services.users import UserService


def get_uow_factory(request: Request) -> Callable[[], UnitOfWork]:
    session_factory = request.app.state.session_factory
    return lambda: UnitOfWork(session_factory)


UowFactoryDep = Annotated[Callable[[], UnitOfWork], Depends(get_uow_factory)]


def get_user_service(uow_factory: UowFactoryDep) -> UserService:
    return UserService(uow_factory)


def get_tiktok_service(request: Request, uow_factory: UowFactoryDep) -> TikTokService:
    return TikTokService(uow_factory, request.app.state.tiktok_client)

def get_studio_service(request: Request, uow_factory: UowFactoryDep) -> StudioService:
    return StudioService(uow_factory, request.app.state.tiktok_client)

UserServiceDep = Annotated[UserService, Depends(get_user_service)]
TikTokServiceDep = Annotated[TikTokService, Depends(get_tiktok_service)]
StudioDep = Annotated[StudioService, Depends(get_studio_service)]


def get_current_user_id(request: Request) -> uuid.UUID:
    raw = request.session.get(USER_ID_KEY)
    if not raw:
        raise NotAuthenticatedError()
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        request.session.clear()
        raise NotAuthenticatedError() from exc


CurrentUserId = Annotated[uuid.UUID, Depends(get_current_user_id)]


async def get_current_user(
    request: Request, user_id: CurrentUserId, service: UserServiceDep
) -> UserRead:
    user = await service.get_by_id(user_id)
    if user is None:  # cookie is valid but the user was deleted
        request.session.clear()
        raise NotAuthenticatedError()
    return user


CurrentUser = Annotated[UserRead, Depends(get_current_user)]
