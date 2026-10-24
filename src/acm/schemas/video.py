from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MIN_FRAGMENT_SECONDS = 0.2
MAX_FRAGMENTS = 50


class VideoRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=255)


class VideoUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=255)


class VideoUrlRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


class ImportProgress(BaseModel):
    status: str  # downloading | draft | failed
    percent: int = 0
    error: str | None = None


class FragmentSpec(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    title: str = Field(min_length=1, max_length=255)
    enabled: bool = True

    @model_validator(mode="after")
    def _long_enough(self) -> "FragmentSpec":
        if self.enabled and self.end - self.start < MIN_FRAGMENT_SECONDS:
            raise ValueError("A fragment must be at least 0.2 s long")
        return self


class FragmentsOptions(BaseModel):
    """Cut one source video into several drafts (or queue entries)."""

    fragments: list[FragmentSpec] = Field(min_length=1, max_length=MAX_FRAGMENTS)
    description: str = Field(default="", max_length=255)
    speed: float = Field(default=1.0, ge=0.25, le=4.0)
    queue: bool = False  # True: new videos go straight into the scheduler queue
    # "9:16" renders 1080x1920. zoom 0 = whole frame with black bars (letterbox),
    # 1 = fill the screen (sides cropped), in between = bigger picture, thinner bars, less crop.
    aspect: Literal["original", "9:16"] = "original"
    zoom: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _something_enabled(self) -> "FragmentsOptions":
        if not any(f.enabled for f in self.fragments):
            raise ValueError("Select at least one fragment")
        return self


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