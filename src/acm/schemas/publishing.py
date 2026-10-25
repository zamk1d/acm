from enum import StrEnum
from pydantic import BaseModel, Field, model_validator

class PublishMethod(StrEnum):
    DIRECT = "direct"  # post to the profile right away (needs video.publish)
    DRAFT = "draft"    # deliver to the creator's TikTok drafts (needs video.upload)

class PublishOptions(BaseModel):
    """How a video should be sent to TikTok."""
    method: PublishMethod = Field(default=PublishMethod.DIRECT, description="'direct' posts immediately, 'draft' saves to TikTok inbox.")
    privacy_level: str | None = Field(default=None, description="Required for direct post. E.g., 'PUBLIC_TO_EVERYONE', 'SELF_ONLY'", examples=["SELF_ONLY"])
    disable_comment: bool = Field(default=False)
    disable_duet: bool = Field(default=False)
    disable_stitch: bool = Field(default=False)
    is_aigc: bool = Field(default=False, description="Is this AI-generated content?")
    brand_content_toggle: bool = Field(default=False, description="Paid partnership / branded content")
    brand_organic_toggle: bool = Field(default=False, description="Promoting the creator's own business")
    cover_timestamp_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _direct_needs_privacy(self) -> "PublishOptions":
        if self.method is PublishMethod.DIRECT and not self.privacy_level:
            raise ValueError("Choose who can view the video")
        if self.brand_content_toggle and self.privacy_level == "SELF_ONLY":
            raise ValueError("Branded content can't be private")
        return self