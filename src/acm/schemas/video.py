from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

MIN_FRAGMENT_SECONDS = 0.2
MAX_FRAGMENTS = 50

class VideoRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="Video title", examples=["My awesome video"])
    description: str = Field(default="", max_length=255, description="Video description", examples=["Check out this cool edit!"])

class VideoUpdateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, examples=["Updated title"])
    description: str = Field(default="", max_length=255, examples=["Updated description"])

class ImportProgress(BaseModel):
    status: str = Field(..., description="Status of the import: downloading, draft, or failed", examples=["downloading"])
    percent: int = Field(default=0, description="Progress percentage from 0 to 100", examples=[45])
    error: str | None = Field(default=None, description="Error message if status is failed")

class FragmentSpec(BaseModel):
    start: float = Field(..., ge=0, description="Start time in seconds", examples=[10.5])
    end: float = Field(..., gt=0, description="End time in seconds", examples=[25.0])
    title: str = Field(..., min_length=1, max_length=255, description="Title for this specific fragment", examples=["Part 1"])
    enabled: bool = Field(default=True, description="Whether to generate this fragment")

    @model_validator(mode="after")
    def _long_enough(self) -> "FragmentSpec":
        if self.enabled and self.end - self.start < MIN_FRAGMENT_SECONDS:
            raise ValueError("A fragment must be at least 0.2 s long")
        return self

class FragmentsOptions(BaseModel):
    """Cut one source video into several drafts (or queue entries)."""
    fragments: list[FragmentSpec] = Field(..., min_length=1, max_length=MAX_FRAGMENTS)
    description: str = Field(default="", max_length=255, description="Description applied to all fragments")
    speed: float = Field(default=1.0, ge=0.25, le=4.0, description="Playback speed multiplier", examples=[1.05])
    queue: bool = Field(default=False, description="If true, new videos go straight into the scheduler queue")
    aspect: Literal["original", "9:16"] = Field(default="original", description="Output aspect ratio. '9:16' renders 1080x1920.")
    zoom: float = Field(default=0.0, ge=0.0, le=1.0, description="Used with 9:16. 0 = letterbox, 1 = full crop.")

    @model_validator(mode="after")
    def _something_enabled(self) -> "FragmentsOptions":
        if not any(f.enabled for f in self.fragments):
            raise ValueError("Select at least one fragment")
        return self

class VideoRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "account_id": 3,
                "video_name": "video.mp4",
                "file_name": "a1b2c3d4.mp4",
                "status": "draft",
                "title": "My video",
                "description": "Test",
                "tiktok_video_id": None,
                "error": None,
                "published_at": None
            }
        }
    )
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

class VideoListRead(VideoRead):
    pass

class AudioTrackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    language: str = Field(..., examples=["ru"])
    language_name: str = Field(..., examples=["Russian"])
    format_id: str = Field(..., examples=["251-1"])
    is_original: bool = Field(default=False)

class VideoProbeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    title: str
    duration: float | None = None
    audio_tracks: list[AudioTrackRead] = []
    default_language: str | None = None

class VideoUrlProbeRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=2048, examples=["https://www.youtube.com/watch?v=dQw4w9WgXcQ"])

class VideoUrlRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=2048, examples=["https://www.youtube.com/watch?v=dQw4w9WgXcQ"])
    audio_language: str | None = Field(default=None, description="BCP-47 language code for audio track", examples=["en", "ru"])
    metadata_language: str | None = Field(default=None, description="BCP-47 language code for title/description", examples=["en", "ru"])