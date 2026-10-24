import uuid

from pydantic import BaseModel, ConfigDict


class UserRead(BaseModel):
    """Public view of a user. Never contains password_hash."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str