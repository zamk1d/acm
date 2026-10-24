from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from acm.api.error_handlers import register_exception_handlers
from acm.api.routers import tiktok, health, pages, users, studio
from acm.core.config import Settings, get_settings
from acm.core.logging import configure_logging
from acm.db.session import create_engine, create_session_factory
from acm.integrations.tiktok import TikTokClient, TikTokClientConfig


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(debug=settings.debug)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings.database_url, echo=False)
        http = httpx.AsyncClient(timeout=settings.tiktok_http_timeout_seconds)

        app.state.settings = settings
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
        app.state.tiktok_client = TikTokClient(
            http,
            TikTokClientConfig(
                client_key=settings.tiktok_client_key,
                client_secret=settings.tiktok_client_secret.get_secret_value(),
                redirect_uri=settings.tiktok_redirect_uri,
                scopes=settings.tiktok_scope_list,
                auth_base_url=settings.tiktok_auth_base_url,
                api_base_url=settings.tiktok_api_base_url,
            ),
        )
        try:
            yield
        finally:
            await http.aclose()
            await engine.dispose()

    app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key.get_secret_value(),
        max_age=settings.session_max_age_seconds,
        same_site="lax",  # must stay lax: the OAuth callback is a cross-site top-level redirect
        https_only=settings.session_https_only,
    )
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(pages.router)
    app.include_router(users.router)
    app.include_router(tiktok.router)
    app.include_router(studio.router)
    return app
