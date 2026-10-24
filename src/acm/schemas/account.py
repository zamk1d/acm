import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class AccountRead(BaseModel):
    """Public view of an account. Never contains tokens."""

    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    open_id: str
    union_id: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    scopes: list[str] = []
    access_token_expires_at: datetime
    refresh_token_expires_at: datetime

    @field_validator("scopes", mode="before")
    @classmethod
    def _split_scopes(cls, value: object) -> object:
        if isinstance(value, str):
            return [s for s in value.split(",") if s]
        return value
