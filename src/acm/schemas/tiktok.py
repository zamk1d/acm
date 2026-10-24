from datetime import datetime
from typing import Union

from pydantic import BaseModel, ConfigDict, Field

class TikTokVideoPostPostInfo(BaseModel):
    privacy_level: str = "SELF_ONLY"
    disable_duet: bool = False
    disable_stitch: bool = False
    disable_comment: bool = False
    video_cover_timestamp_ms: int | None = None
    brand_content_toggle: bool = False
    is_aigc: bool = False

class TikTokVideoPostSourceInfo(BaseModel):
    source: str = "FILE_UPLOAD"
    video_url: str | None = None

class TikTokVideoPostRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    post_info: TikTokVideoPostPostInfo
    source_info: TikTokVideoPostSourceInfo