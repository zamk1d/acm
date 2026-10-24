from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class TokenResponse(BaseModel):
    """Response of POST /v2/oauth/token/ (both authorization_code and refresh_token grants)."""

    model_config = ConfigDict(extra="ignore")

    access_token: str
    refresh_token: str
    open_id: str
    scope: str = ""
    token_type: str = "Bearer"
    expires_in: int
    refresh_expires_in: int

    @property
    def scopes(self) -> list[str]:
        return [s.strip() for s in self.scope.split(",") if s.strip()]


class TikTokUser(BaseModel):
    """`data.user` of GET /v2/user/info/. Which fields are present depends on granted scopes."""

    model_config = ConfigDict(extra="ignore")

    open_id: str
    union_id: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    avatar_url_100: str | None = None
    avatar_large_url: str | None = None
    bio_description: str | None = None
    profile_deep_link: str | None = None
    is_verified: bool | None = None
    username: str | None = None
    follower_count: int | None = None
    following_count: int | None = None
    likes_count: int | None = None
    video_count: int | None = None


class TikTokVideo(BaseModel):
    """One item of /v2/video/list/. Only requested fields are present, hence all optional."""

    model_config = ConfigDict(extra="ignore")

    id: str
    title: str = ""
    video_description: str | None = None
    duration: int | None = Field(default=None, description="Seconds")
    cover_image_url: HttpUrl | None = None  # expires after a while, re-fetch the list
    share_url: HttpUrl | None = None
    embed_link: HttpUrl | None = None
    like_count: int | None = None
    comment_count: int | None = None
    share_count: int | None = None
    view_count: int | None = None


class TikTokVideoPage(BaseModel):
    """`data` of /v2/video/list/. Default instance = empty page."""

    model_config = ConfigDict(extra="ignore")

    videos: list[TikTokVideo] = Field(default_factory=list)
    cursor: int | None = None  # ms timestamp; pass it back to get the next page
    has_more: bool = False

class TikTokVideoPost(BaseModel):
    model_config = ConfigDict(extra="ignore")

    publish_id: str
    upload_url: str

class TikTokPostStatus(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str
    fail_reason: str
    publicaly_available_post_id: list
    uploaded_bytes: int