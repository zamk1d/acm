from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "acm"
    debug: bool = False

    # web session (signed cookie)
    secret_key: SecretStr
    session_https_only: bool = True
    session_max_age_seconds: int = 60 * 60 * 24 * 14

    # database
    database_url: str
    telegram_bot_token: SecretStr | None = None
    telegram_enabled: bool = True
    # Optional: set the bot's @username directly to skip the getMe call. No "@", just the name.
    telegram_bot_username: str | None = "ACMShedulerBot"
    # TikTok Login Kit
    tiktok_client_key: str
    tiktok_client_secret: SecretStr
    tiktok_redirect_uri: str
    tiktok_scopes: str = "user.info.basic"
    tiktok_auth_base_url: str = "https://www.tiktok.com"
    tiktok_api_base_url: str = "https://open.tiktokapis.com"
    tiktok_http_timeout_seconds: float = 10.0

    upload_dir: str = "uploads"
    max_upload_bytes: int = 512 * 1024 * 1024

    @property
    def tiktok_scope_list(self) -> list[str]:
        return [s.strip() for s in self.tiktok_scopes.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # values come from env / .env
