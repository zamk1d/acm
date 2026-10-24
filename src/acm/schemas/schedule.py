import datetime as dt
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from acm.schemas.publishing import PublishMethod


class PlanRequest(BaseModel):
    """Auto-publishing settings as submitted by the scheduler form."""

    enabled: bool = False
    timezone: str = "UTC"
    posts_per_day: int = Field(default=1, ge=1, le=10)
    window_start: dt.time = dt.time(9, 0)
    window_end: dt.time = dt.time(21, 0)
    # None = spread posts evenly across the window; N = a post every N minutes from the start
    interval_minutes: int | None = Field(default=None, ge=15, le=720)
    weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])
    method: PublishMethod = PublishMethod.DIRECT
    privacy_level: str | None = "SELF_ONLY"
    disable_comment: bool = False
    disable_duet: bool = False
    disable_stitch: bool = False
    is_aigc: bool = False

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Unknown timezone: {value}") from exc
        return value

    @field_validator("weekdays")
    @classmethod
    def _valid_weekdays(cls, value: list[int]) -> list[int]:
        days = sorted(set(value))
        if not days or any(d < 0 or d > 6 for d in days):
            raise ValueError("Pick at least one day of the week")
        return days

    @model_validator(mode="after")
    def _consistent(self) -> "PlanRequest":
        if self.window_end <= self.window_start:
            raise ValueError("The end of the time window must be after its start")
        if self.method is PublishMethod.DIRECT and not self.privacy_level:
            raise ValueError("Choose who can view the posts")
        return self


class PlanRead(PlanRequest):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    next_run_at: dt.datetime | None = None
    last_run_at: dt.datetime | None = None

    @field_validator("weekdays", mode="before")
    @classmethod
    def _split(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(d) for d in value.split(",") if d != ""]
        return value


class SlotPreview(BaseModel):
    at: dt.datetime  # UTC
    local: str  # human readable, in the plan's timezone
    video_title: str | None = None  # which queued video will go out in this slot


class SchedulePreview(BaseModel):
    slots: list[SlotPreview]
    posts_per_day: int  # how many really fit into the window
    queue_size: int
    queue_lasts_days: float | None = None
    warnings: list[str] = Field(default_factory=list)


class QueueOrder(BaseModel):
    ids: list[int]
