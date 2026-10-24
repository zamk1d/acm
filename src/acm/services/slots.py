"""Publishing slots: pure functions, no I/O, easy to test.

A plan says "N posts a day between START and END (local time), on these weekdays".
Slots are either evenly spread over the window or `interval_minutes` apart from START.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True, slots=True)
class ScheduleSpec:
    timezone: str
    posts_per_day: int
    window_start: time
    window_end: time
    interval_minutes: int | None
    weekdays: frozenset[int]


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def slots_for_day(spec: ScheduleSpec, day: date) -> list[datetime]:
    """Slots of one local calendar day (aware datetimes in the plan's timezone)."""
    if day.weekday() not in spec.weekdays:
        return []
    start, end, count = _minutes(spec.window_start), _minutes(spec.window_end), spec.posts_per_day
    if spec.interval_minutes:
        offsets = [start + i * spec.interval_minutes for i in range(count)]
        offsets = [o for o in offsets if o <= end]  # whatever doesn't fit the window is dropped
    elif count == 1:
        offsets = [start]
    else:
        step = (end - start) / (count - 1)
        offsets = [round(start + i * step) for i in range(count)]
    midnight = datetime.combine(day, time(0), tzinfo=ZoneInfo(spec.timezone))
    return [midnight + timedelta(minutes=o) for o in offsets]


def posts_per_day_that_fit(spec: ScheduleSpec) -> int:
    """How many posts a working day really gets (interval + window may cut the requested count)."""
    working_day = next(iter(sorted(spec.weekdays)), 0)
    monday = date(2024, 1, 1)  # a Monday; only the weekday matters here
    return len(slots_for_day(spec, monday + timedelta(days=working_day)))


def upcoming_slots(
    spec: ScheduleSpec, after: datetime, count: int, *, horizon_days: int = 90
) -> list[datetime]:
    """The next `count` slots strictly after `after`, as UTC datetimes."""
    tz = ZoneInfo(spec.timezone)
    first_day = after.astimezone(tz).date()
    found: list[datetime] = []
    for offset in range(horizon_days):
        for slot in slots_for_day(spec, first_day + timedelta(days=offset)):
            slot_utc = slot.astimezone(UTC)
            if slot_utc > after:
                found.append(slot_utc)
                if len(found) == count:
                    return found
    return found


def next_slot(spec: ScheduleSpec, after: datetime) -> datetime | None:
    slots = upcoming_slots(spec, after, 1)
    return slots[0] if slots else None

