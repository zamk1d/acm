from enum import StrEnum

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from acm.db.base import Base, TimestampMixin


class VideoStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


class Video(Base, TimestampMixin):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("tiktok_accounts.id", ondelete="CASCADE"), index=True
    )
    video_name: Mapped[str] = mapped_column(String(255))  # original file name, for display
    file_name: Mapped[str] = mapped_column(String(255), unique=True)  # name on disk
    status: Mapped[str] = mapped_column(String(32), default=VideoStatus.DRAFT.value)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(255))