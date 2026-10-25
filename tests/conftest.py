import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from acm.api.deps import get_current_user, get_current_user_id, get_services
from acm.core.config import Settings
from acm.db.base import Base
from acm.db.uow import UnitOfWork
from acm.integrations.tiktok import TikTokClient, TikTokClientConfig
from acm.main import create_app
from acm.models import TikTokAccount, User, Video
from acm.models.video import VideoStatus
from acm.schemas.user import UserRead
from acm.services.container import Services
from acm.storage import LocalFileStorage


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        secret_key="test-secret",
        database_url="sqlite+aiosqlite:///:memory:",
        tiktok_client_key="ck",
        tiktok_client_secret="cs",
        tiktok_redirect_uri="https://example.com/auth/tiktok/callback",
        tiktok_scopes="user.info.basic,video.list",
        session_https_only=False,
        run_worker=False,
        upload_dir="test_uploads",
    )


@pytest_asyncio.fixture
async def db_session(settings: Settings):
    engine = create_async_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    yield session_factory
    await engine.dispose()


@pytest.fixture
def mock_tiktok_client() -> TikTokClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200)))
    return TikTokClient(
        http=http,
        config=TikTokClientConfig(
            client_key="ck", client_secret="cs",
            redirect_uri="https://example.com/cb", scopes=[]
        )
    )


@pytest_asyncio.fixture
async def test_services(settings: Settings, db_session, mock_tiktok_client) -> Services:
    def uow_factory():
        return UnitOfWork(db_session)

    return Services(
        uow_factory=uow_factory,
        tiktok_client=mock_tiktok_client,
        storage=LocalFileStorage(Path(settings.upload_dir)),
        settings=settings,
        http=httpx.AsyncClient(),
    )


@pytest_asyncio.fixture
async def mock_user(db_session) -> User:
    async with UnitOfWork(db_session) as uow:
        user = User(email="test@example.com", password_hash="hash")
        uow.users.add(user)
        await uow.commit()
        return user


@pytest.fixture
def app(settings: Settings, test_services: Services, mock_user: User) -> FastAPI:
    app = create_app(settings)
    app.dependency_overrides[get_services] = lambda: test_services

    user_read = UserRead.model_validate(mock_user)
    app.dependency_overrides[get_current_user_id] = lambda: mock_user.id
    app.dependency_overrides[get_current_user] = lambda: user_read
    return app


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# --- Фикстуры данных ---

@pytest_asyncio.fixture
async def account_a(db_session, mock_user: User) -> TikTokAccount:
    async with UnitOfWork(db_session) as uow:
        acc = TikTokAccount(
            open_id="open_a",
            user_id=mock_user.id,
            access_token="at",
            refresh_token="rt",
            access_token_expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
            refresh_token_expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        )
        uow.tiktok_accounts.add(acc)
        await uow.commit()
        return acc


@pytest_asyncio.fixture
async def video_a(db_session, account_a: TikTokAccount) -> Video:
    async with UnitOfWork(db_session) as uow:
        vid = Video(
            account_id=account_a.id,
            video_name="test.mp4",
            file_name="uuid.mp4",
            title="My video",
            description="", # <-- ДОБАВЛЕНО
            status=VideoStatus.DRAFT.value,
        )
        uow.videos.add(vid)
        await uow.commit()
        return vid


@pytest_asyncio.fixture
async def queued_video(db_session, account_a: TikTokAccount) -> Video:
    async with UnitOfWork(db_session) as uow:
        vid = Video(
            account_id=account_a.id,
            video_name="queued.mp4",
            file_name="uuid_queued.mp4",
            title="Queued video",
            description="", # <-- ДОБАВЛЕНО
            status=VideoStatus.QUEUED.value,
        )
        uow.videos.add(vid)
        await uow.commit()
        return vid