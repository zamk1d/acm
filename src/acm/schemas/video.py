from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class VideoRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=255)


class VideoUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=255)


class VideoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_id: int
    video_name: str
    file_name: str | None = None
    status: str
    title: str
    description: str | None = None
    tiktok_video_id: str | None = None
    error: str | None = None
    published_at: datetime | None = None


class VideoDetailRead(VideoRead):
    created_at: datetime
    updated_at: datetime


class VideoListRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    video_name: str
    file_name: str | None = None
    status: str
    title: str
    description: str | None = None