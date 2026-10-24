"""Background worker: advances publishing jobs, triggers scheduling plans, snapshots metrics,
and runs the Telegram long-polling bot."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from acm.services.container import Services

logger = logging.getLogger(__name__)

# How often to look for work. Publishing takes minutes so 5s is plenty.
PUBLISH_TICK = 5
# Scheduler ticks less often (it just starts jobs)
SCHEDULER_TICK = 30
# Snapshots: TikTok counters change slowly, hourly is fine
SNAPSHOT_TICK = 60 * 60


async def worker_loop(services: Services) -> None:
    await asyncio.gather(
        _loop_forever("publishing", PUBLISH_TICK, services.publishing().process_pending),
        _loop_forever("scheduler", SCHEDULER_TICK, services.scheduler().run_due_plans),
        _loop_forever("analytics", SNAPSHOT_TICK, services.analytics().snapshot_all),
        services.telegram_bot().run(),  # long-polling bot, has its own loop
    )


async def _loop_forever(
    name: str,
    tick: int,
    job: Callable[[], Awaitable[Any]],
) -> None:
    while True:
        try:
            result = await job()
            if result:
                logger.debug("worker %s: %s", name, result)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("worker %s tick failed", name)
        await asyncio.sleep(tick)