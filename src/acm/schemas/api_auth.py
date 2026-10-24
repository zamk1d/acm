import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    email: str = Field(description="User email")
    password: str = Field(description="User password")


class RegisterRequest(BaseModel):
    email: str = Field(description="User email")
    password: str = Field(min_length=8, max_length=128, description="Min 8 characters")


class UserMe(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str


class TokenCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100, description="Human-readable label")


class TokenCreatedResponse(BaseModel):
    id: int
    name: str
    token: str = Field(description="Plaintext token. Store it — it's shown only once.")
    created_at: datetime


class TokenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    last_used_at: datetime | None = None