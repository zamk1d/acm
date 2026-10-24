import uuid

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from acm.db.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(64), nullable=True)