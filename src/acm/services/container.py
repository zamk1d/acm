"""Composition root: the one place that knows how services are wired together.

Request handlers and the background worker both get their services from here, so they are
guaranteed to be built the same way.
"""

from collections.abc import Callable
from datetime import datetime

from acm.core.config import Settings
from acm.core.time import utcnow
from acm.db.uow import UnitOfWork
from acm.integrations.tiktok import TikTokClient
from acm.services.analytics import AnalyticsService
from acm.services.publishing import PublishingService
from acm.services.scheduler import SchedulerService
from acm.services.studio import StudioService
from acm.services.tiktok import TikTokService
from acm.services.users import UserService
from acm.storage import FileStorage


class Services:
    def __init__(
        self,
        *,
        uow_factory: Callable[[], UnitOfWork],
        tiktok_client: TikTokClient,
        storage: FileStorage,
        settings: Settings,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._uow_factory = uow_factory
        self._client = tiktok_client
        self._storage = storage
        self._settings = settings
        self._clock = clock

    def users(self) -> UserService:
        return UserService(self._uow_factory)

    def tiktok(self) -> TikTokService:
        return TikTokService(self._uow_factory, self._client, self._clock)

    def studio(self) -> StudioService:
        return StudioService(
            self._uow_factory, self._storage, max_upload_bytes=self._settings.max_upload_bytes
        )

    def publishing(self) -> PublishingService:
        return PublishingService(
            self._uow_factory, self._client, self.tiktok(), self._storage, self._clock
        )

    def scheduler(self) -> SchedulerService:
        return SchedulerService(self._uow_factory, self.publishing(), self._clock)

    def analytics(self) -> AnalyticsService:
        return AnalyticsService(self._uow_factory, self.tiktok(), self._clock)

    def uow_factory(self):
        return self._uow_factory