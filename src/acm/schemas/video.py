from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class VideoRequest(BaseModel):
    """Form fields that accompany an uploaded video."""
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=255)


class VideoUpdateRequest(BaseModel):
    """JSON body for editing an existing draft."""
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=255)


class VideoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_id: int
    video_name: str
    file_name: str
    status: str
    title: str
    description: str | None = None


class VideoDetailRead(VideoRead):
    created_at: datetime
    updated_at: datetime


class VideoListRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    video_name: str
    file_name: str
    status: str
    title: str
    description: str | None = None