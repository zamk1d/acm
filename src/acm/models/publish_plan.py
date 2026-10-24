from datetime import datetime, time

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Time
from sqlalchemy.orm import Mapped, mapped_column

from acm.db.base import Base, TimestampMixin


class PublishPlan(Base, TimestampMixin):
    __tablename__ = "publish_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("tiktok_accounts.id", ondelete="CASCADE"), unique=True, index=True
    )

    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    posts_per_day: Mapped[int] = mapped_column(Integer, default=1)
    window_start: Mapped[time] = mapped_column(Time, default=time(9, 0))
    window_end: Mapped[time] = mapped_column(Time, default=time(21, 0))
    interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weekdays: Mapped[str] = mapped_column(String(32), default="0,1,2,3,4,5,6")

    method: Mapped[str] = mapped_column(String(16), default="direct")
    privacy_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    disable_comment: Mapped[bool] = mapped_column(Boolean, default=False)
    disable_duet: Mapped[bool] = mapped_column(Boolean, default=False)
    disable_stitch: Mapped[bool] = mapped_column(Boolean, default=False)
    is_aigc: Mapped[bool] = mapped_column(Boolean, default=False)

    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)