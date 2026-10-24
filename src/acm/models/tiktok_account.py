import uuid
from datetime import datetime, timedelta
from datetime import UTC, datetime, timedelta
from sqlalchemy import DateTime, String, Text, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from acm.db.base import Base, TimestampMixin


def _as_utc(value: datetime) -> datetime:
    """Postgres returns aware datetimes; SQLite (used in tests) returns naive UTC ones."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)

class TikTokAccount(Base, TimestampMixin):
    __tablename__ = "tiktok_accounts"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    # owner: the service user this TikTok account is connected to
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    # identity (open_id is unique per user per app)
    open_id: Mapped[str] = mapped_column(String(128), unique=True)
    union_id: Mapped[str | None] = mapped_column(String(128))

    # profile snapshot
    display_name: Mapped[str | None] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(Text)

    # tokens
    # NOTE: stored as plain text. Encrypt at rest (e.g. Fernet/KMS) before going to production.
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str] = mapped_column(Text)
    scopes: Mapped[str] = mapped_column(Text, default="")
    access_token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    refresh_token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def is_access_token_expired(self, now: datetime, leeway: timedelta = timedelta(0)) -> bool:
        return _as_utc(self.access_token_expires_at) <= now + leeway

    def is_refresh_token_expired(self, now: datetime) -> bool:
        return _as_utc(self.refresh_token_expires_at) <= now

