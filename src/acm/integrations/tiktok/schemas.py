from pydantic import BaseModel, ConfigDict


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
