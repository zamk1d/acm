"""Auto-publishing: a plan (when / how often / how) + a queue of videos waiting for their slot."""

import logging
import math
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from acm.core.exceptions import AppError, VideoNotEditableError, VideoNotFoundError
from acm.core.time import ensure_utc, utcnow
from acm.db.uow import UnitOfWork
from acm.models import PublishPlan
from acm.models.video import Video, VideoStatus
from acm.schemas.publishing import PublishMethod, PublishOptions
from acm.schemas.schedule import PlanRead, PlanRequest, SchedulePreview, SlotPreview
from acm.schemas.video import VideoRead
from acm.services.publishing import PublishingService
from acm.services.slots import ScheduleSpec, next_slot, posts_per_day_that_fit, upcoming_slots

logger = logging.getLogger(__name__)

# A slot that is found "already past" by more than this was missed (server was down...):
# we skip it instead of posting late, and never burst several posts to catch up.
GRACE = timedelta(minutes=10)
PREVIEW_SLOTS = 10


def _spec(plan: PlanRequest | PlanRead) -> ScheduleSpec:
    return ScheduleSpec(
        timezone=plan.timezone,
        posts_per_day=plan.posts_per_day,
        window_start=plan.window_start,
        window_end=plan.window_end,
        interval_minutes=plan.interval_minutes,
        weekdays=frozenset(plan.weekdays),
    )


class SchedulerService:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        publishing: PublishingService,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._uow_factory = uow_factory
        self._publishing = publishing
        self._clock = clock

    # --- plan ------------------------------------------------------------------------------

    async def get_plan(self, user_id: uuid.UUID, account_id: int) -> PlanRead:
        async with self._uow_factory() as uow:
            await uow.tiktok_accounts.require_for_user(user_id, account_id)
            plan = await uow.plans.get_by_account(account_id)
            # no plan yet: show the defaults, nothing is stored until the user saves
            return PlanRead.model_validate(plan) if plan else PlanRead()

    async def save_plan(
        self, user_id: uuid.UUID, account_id: int, request: PlanRequest
    ) -> PlanRead:
        async with self._uow_factory() as uow:
            await uow.tiktok_accounts.require_for_user(user_id, account_id)
            plan = await uow.plans.get_by_account(account_id)
            if plan is None:
                plan = PublishPlan(account_id=account_id)
                uow.plans.add(plan)
            plan.enabled = request.enabled
            plan.timezone = request.timezone
            plan.posts_per_day = request.posts_per_day
            plan.window_start = request.window_start
            plan.window_end = request.window_end
            plan.interval_minutes = request.interval_minutes
            plan.weekdays = ",".join(str(d) for d in request.weekdays)
            plan.method = request.method.value
            plan.privacy_level = request.privacy_level
            plan.disable_comment = request.disable_comment
            plan.disable_duet = request.disable_duet
            plan.disable_stitch = request.disable_stitch
            plan.is_aigc = request.is_aigc
            plan.next_run_at = next_slot(_spec(request), self._clock()) if request.enabled else None
            await uow.commit()
            return PlanRead.model_validate(plan)

    async def preview(
        self,
        user_id: uuid.UUID,
        account_id: int,
        request: PlanRequest,
        pending_titles: list[str] | None = None,
    ) -> SchedulePreview:
        """What the plan would do, without saving it: next slots and which video takes each.

        `pending_titles` are videos that will be queued right after the saved queue (fragments
        the user is still editing in the creative studio).
        """
        queue = await self.list_queue(user_id, account_id)
        pending = [t[:255] for t in (pending_titles or [])]
        titles = [v.title for v in queue] + pending
        spec = _spec(request)
        tz = ZoneInfo(request.timezone)
        slots = upcoming_slots(spec, self._clock(), PREVIEW_SLOTS)
        per_day = posts_per_day_that_fit(spec)

        warnings = []
        if per_day < request.posts_per_day:
            warnings.append(
                f"Only {per_day} of {request.posts_per_day} posts fit into the time window "
                "with this interval."
            )
        if not slots:
            warnings.append("No slots match these settings.")
        if not titles:
            warnings.append("The queue is empty: nothing will be posted until you add videos.")

        days_active = max(len(request.weekdays), 1) / 7 * per_day
        lasts = len(titles) / days_active if days_active and titles else None
        return SchedulePreview(
            slots=[
                SlotPreview(
                    at=slot,
                    local=slot.astimezone(tz).strftime("%a %d %b, %H:%M"),
                    video_title=titles[i] if i < len(titles) else None,
                    pending=len(queue) <= i < len(titles),
                )
                for i, slot in enumerate(slots)
            ],
            posts_per_day=per_day,
            queue_size=len(titles),
            queue_lasts_days=math.ceil(lasts) if lasts else None,
            warnings=warnings,
        )

    # --- queue -----------------------------------------------------------------------------

    async def list_queue(self, user_id: uuid.UUID, account_id: int) -> list[VideoRead]:
        async with self._uow_factory() as uow:
            await uow.tiktok_accounts.require_for_user(user_id, account_id)
            return [VideoRead.model_validate(v) for v in await uow.videos.list_queue(account_id)]

    async def enqueue(self, user_id: uuid.UUID, account_id: int, video_id: int) -> VideoRead:
        async with self._uow_factory() as uow:
            await uow.tiktok_accounts.require_for_user(user_id, account_id)
            position = await uow.videos.next_queue_position(account_id)
            claimed = await uow.videos.claim(
                account_id,
                video_id,
                from_statuses=(VideoStatus.DRAFT, VideoStatus.FAILED),
                values={"status": VideoStatus.QUEUED.value, "queue_position": position, "error": None},
            )
            if not claimed:
                raise VideoNotEditableError("Only drafts and failed videos can be queued")
            await uow.commit()
        return await self._read(account_id, video_id)

    async def dequeue(self, user_id: uuid.UUID, account_id: int, video_id: int) -> VideoRead:
        async with self._uow_factory() as uow:
            await uow.tiktok_accounts.require_for_user(user_id, account_id)
            claimed = await uow.videos.claim(
                account_id,
                video_id,
                from_statuses=(VideoStatus.QUEUED,),
                values={"status": VideoStatus.DRAFT.value, "queue_position": None},
            )
            if not claimed:
                raise VideoNotEditableError("This video isn't in the queue")
            await uow.commit()
        return await self._read(account_id, video_id)

    async def reorder_queue(
        self, user_id: uuid.UUID, account_id: int, ids: list[int]
    ) -> list[VideoRead]:
        async with self._uow_factory() as uow:
            await uow.tiktok_accounts.require_for_user(user_id, account_id)
            queue = {v.id: v for v in await uow.videos.list_queue(account_id)}
            ordered = [queue[i] for i in ids if i in queue]
            ordered += [v for i, v in queue.items() if i not in set(ids)]  # unknown ids: keep tail
            for position, video in enumerate(ordered, start=1):
                video.queue_position = position
            await uow.commit()
        return await self.list_queue(user_id, account_id)

    # --- the worker side -------------------------------------------------------------------

    async def run_due_plans(self) -> int:
        """Called by the worker. For every plan whose slot has come, sends the next queued video."""
        now = self._clock()
        async with self._uow_factory() as uow:
            due = await uow.plans.list_due(now)
        started = 0
        for plan in due:
            if plan.next_run_at is None:
                continue
            slot = ensure_utc(plan.next_run_at)
            new_next = next_slot(_spec(PlanRead.model_validate(plan)), now)
            async with self._uow_factory() as uow:
                # optimistic lock: with several workers only one gets to serve this slot
                if not await uow.plans.claim_run(plan.id, plan.next_run_at, new_next, now):
                    continue
                await uow.commit()
            if now - slot > GRACE:
                logger.info("Missed slot skipped account_id=%s slot=%s", plan.account_id, slot)
                continue
            if await self._publish_next(plan):
                started += 1
        return started

    async def _publish_next(self, plan: PublishPlan) -> bool:
        async with self._uow_factory() as uow:
            head = await uow.videos.queue_head(plan.account_id)
            account = await uow.tiktok_accounts.get(plan.account_id)
            if head is None or account is None:
                return False
            video_id, user_id = head.id, account.user_id

        options = PublishOptions(
            method=PublishMethod(plan.method),
            privacy_level=plan.privacy_level,
            disable_comment=plan.disable_comment,
            disable_duet=plan.disable_duet,
            disable_stitch=plan.disable_stitch,
            is_aigc=plan.is_aigc,
        )
        try:
            await self._publishing.start(user_id, plan.account_id, video_id, options)
        except AppError as exc:
            logger.warning("Scheduled publish failed video_id=%s: %s", video_id, exc.message)
            # Не переводим в FAILED, просто логируем. Планировщик попробует в следующий слот.
            return False
        return True

    async def _read(self, account_id: int, video_id: int) -> VideoRead:
        async with self._uow_factory() as uow:
            video: Video | None = await uow.videos.get_in_account(account_id, video_id)
            if video is None:
                raise VideoNotFoundError()
            return VideoRead.model_validate(video)