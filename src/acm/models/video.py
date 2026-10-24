import uuid
from datetime import datetime, timedelta

from sqlalchemy import DateTime, String, Text, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from acm.db.base import Base, TimestampMixin


class Video(Base, TimestampMixin):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("tiktok_accounts.id", ondelete="CASCADE"), index=True
    )
    video_name: Mapped[str] = mapped_column(String(255), unique=False)
    file_name: Mapped[str] = mapped_column(String(255), unique=True)
    status: Mapped[str] = mapped_column(String(255), default="draft")
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(255))