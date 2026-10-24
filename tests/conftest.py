import pytest

from acm.core.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        secret_key="test-secret",  # type: ignore[arg-type]
        database_url="postgresql+asyncpg://u:p@localhost:5432/test",
        tiktok_client_key="ck",
        tiktok_client_secret="cs",  # type: ignore[arg-type]
        tiktok_redirect_uri="https://example.com/auth/tiktok/callback",
        tiktok_scopes="user.info.basic,video.list",
        session_https_only=False,
    )
