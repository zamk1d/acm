import uuid
from typing import Annotated

from fastapi import Depends, Request

from acm.api.session import USER_ID_KEY
from acm.core.config import Settings
from acm.core.exceptions import NotAuthenticatedError
from acm.repositories.api_token import hash_token
from acm.schemas.user import UserRead
from acm.services.analytics import AnalyticsService
from acm.services.container import Services
from acm.services.publishing import PublishingService
from acm.services.scheduler import SchedulerService
from acm.services.studio import StudioService
from acm.services.tiktok import TikTokService
from acm.services.users import UserService


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_services(request: Request) -> Services:
    return request.app.state.services


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
ServicesDep = Annotated[Services, Depends(get_services)]


def get_user_service(services: ServicesDep) -> UserService:
    return services.users()


def get_tiktok_service(services: ServicesDep) -> TikTokService:
    return services.tiktok()


def get_studio_service(services: ServicesDep) -> StudioService:
    return services.studio()


def get_publishing_service(services: ServicesDep) -> PublishingService:
    return services.publishing()


def get_scheduler_service(services: ServicesDep) -> SchedulerService:
    return services.scheduler()


def get_analytics_service(services: ServicesDep) -> AnalyticsService:
    return services.analytics()


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
TikTokServiceDep = Annotated[TikTokService, Depends(get_tiktok_service)]
StudioDep = Annotated[StudioService, Depends(get_studio_service)]
PublishingDep = Annotated[PublishingService, Depends(get_publishing_service)]
SchedulerDep = Annotated[SchedulerService, Depends(get_scheduler_service)]
AnalyticsDep = Annotated[AnalyticsService, Depends(get_analytics_service)]


async def get_current_user_id(request: Request, services: ServicesDep) -> uuid.UUID:
    """Accepts either `Authorization: Bearer <token>` or the session cookie."""

    # 1) Bearer token (API clients)
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        raw = auth.split(" ", 1)[1].strip()
        if not raw:
            raise NotAuthenticatedError()
        async with services.uow_factory() as uow:  # type: ignore[attr-defined]
            token = await uow.api_tokens.get_by_plaintext(raw)
            if token is None:
                raise NotAuthenticatedError()
            user_id = token.user_id
            await uow.api_tokens.touch(token)
            await uow.commit()
            return user_id

    # 2) session cookie (browser)
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
    if user is None:
        request.session.clear()
        raise NotAuthenticatedError()
    return user


CurrentUser = Annotated[UserRead, Depends(get_current_user)]