"""Composition root: the one place that knows how services are wired together.

Request handlers and the background worker both get their services from here, so they are
guaranteed to be built the same way.
"""

from collections.abc import Callable
from datetime import datetime

from acm.core.config import Settings
from acm.core.time import utcnow
from acm.db.uow import UnitOfWork
from acm.integrations.telegram_bot import TelegramBot
from acm.integrations.tiktok import TikTokClient
from acm.services.analytics import AnalyticsService
from acm.services.notifier import TelegramNotifier
from acm.services.publishing import PublishingService
from acm.services.scheduler import SchedulerService
from acm.services.studio import StudioService
from acm.services.tiktok import TikTokService
from acm.services.users import UserService
from acm.storage import FileStorage


class Services:
    def __init__(self, *, uow_factory, tiktok_client, storage, settings, http, clock=utcnow):
        self._uow_factory = uow_factory
        self._client = tiktok_client
        self._storage = storage
        self._settings = settings
        self._http = http
        self._clock = clock
        self._notifier = TelegramNotifier(http, settings)
        self._telegram_bot = TelegramBot(http, settings)

    def users(self) -> UserService:
        return UserService(self._uow_factory)

    def tiktok(self) -> TikTokService:
        return TikTokService(self._uow_factory, self._client, self._clock)

    def studio(self) -> StudioService:
        return StudioService(
            self._uow_factory, self._storage, max_upload_bytes=self._settings.max_upload_bytes
        )

    def notifier(self) -> TelegramNotifier:
        return self._notifier

    def telegram_bot(self) -> TelegramBot:
        return self._telegram_bot

    def publishing(self) -> PublishingService:
        return PublishingService(
            self._uow_factory,
            self._client,
            self.tiktok(),
            self._storage,
            self.notifier(),
            self._clock,
        )

    def scheduler(self) -> SchedulerService:
        return SchedulerService(self._uow_factory, self.publishing(), self._clock)

    def analytics(self) -> AnalyticsService:
        return AnalyticsService(self._uow_factory, self.tiktok(), self._clock)

    def uow_factory(self) -> UnitOfWork:
        """Fresh UnitOfWork. Historical name — returns the unit itself, not the factory."""
        return self._uow_factory()