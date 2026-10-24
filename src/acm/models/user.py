import uuid

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from acm.db.base import TimestampMixin, Base


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.UUID)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)