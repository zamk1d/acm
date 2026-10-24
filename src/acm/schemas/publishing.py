from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class PublishMethod(StrEnum):
    DIRECT = "direct"  # post to the profile right away (needs video.publish)
    DRAFT = "draft"  # deliver to the creator's TikTok drafts (needs video.upload)


class PublishOptions(BaseModel):
    """How a video should be sent to TikTok."""

    method: PublishMethod = PublishMethod.DIRECT
    # only for DIRECT; must be one of the creator's `privacy_level_options`
    privacy_level: str | None = None
    disable_comment: bool = False
    disable_duet: bool = False
    disable_stitch: bool = False
    is_aigc: bool = False
    brand_content_toggle: bool = False  # paid partnership / branded content
    brand_organic_toggle: bool = False  # promoting the creator's own business
    cover_timestamp_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _direct_needs_privacy(self) -> "PublishOptions":
        if self.method is PublishMethod.DIRECT and not self.privacy_level:
            raise ValueError("Choose who can view the video")
        if self.brand_content_toggle and self.privacy_level == "SELF_ONLY":
            raise ValueError("Branded content can't be private")
        return self
