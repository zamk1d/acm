from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from acm.db.base import Base, TimestampMixin


class VideoStatus(StrEnum):
    DOWNLOADING = "downloading"  # импорт с YouTube идёт в фоне
    DRAFT = "draft"           # загружено, ещё не отправлено
    QUEUED = "queued"         # стоит в очереди планировщика
    PUBLISHING = "publishing" # идёт загрузка/публикация
    PUBLISHED = "published"   # опубликовано в профиль (direct post)
    INBOX = "inbox"           # отправлено в черновики TikTok
    FAILED = "failed"


# Из DRAFT и FAILED можно начать публикацию
STARTABLE_STATUSES: tuple[VideoStatus, ...] = (VideoStatus.DRAFT, VideoStatus.FAILED)
# Всё, что видно в рабочей области (не финальные состояния)
ACTIVE_STATUSES: tuple[VideoStatus, ...] = (
    VideoStatus.DOWNLOADING,
    VideoStatus.DRAFT,
    VideoStatus.QUEUED,
    VideoStatus.PUBLISHING,
    VideoStatus.FAILED,
)
# История
DONE_STATUSES: tuple[VideoStatus, ...] = (VideoStatus.PUBLISHED, VideoStatus.INBOX)


class Video(Base, TimestampMixin):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("tiktok_accounts.id", ondelete="CASCADE"), index=True
    )

    video_name: Mapped[str] = mapped_column(String(255))       # оригинальное имя файла (для UI)
    file_name: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)  # на диске
    status: Mapped[str] = mapped_column(
        String(32), default=VideoStatus.DRAFT.value, index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(255))

    # Состояние публикации
    publish_options: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    publish_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    tiktok_video_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Очередь планировщика
    queue_position: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Worker locking
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)