from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import asyncio
import httpx
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from starlette.middleware.sessions import SessionMiddleware

from acm.api.error_handlers import register_exception_handlers
from acm.api.routers import health, pages, scheduler, studio, tiktok, users
from acm.api.routers.api import api_router
from acm.core.config import Settings, get_settings
from acm.core.logging import configure_logging
from acm.db.session import create_engine, create_session_factory
from acm.integrations.tiktok import TikTokClient, TikTokClientConfig
from acm.services.container import Services
from acm.storage import LocalFileStorage
from acm.worker import worker_loop


DESCRIPTION = """
**ACM** — manage TikTok accounts and publish videos programmatically.

## Authentication

Two ways:

1. **API token** (recommended for clients):
POST /api/v1/auth/register (or /login)
POST /api/v1/auth/tokens → returns acm_... token once
Authorization: Bearer acm_...
2. **Session cookie** (for browsers): `POST /api/v1/auth/login` sets a cookie
that is sent automatically by the client.

## Workflow

1. Create account or log in
2. Connect a TikTok account (`GET /accounts/connect-url`, then complete OAuth in a browser)
3. Upload videos (`POST /accounts/{id}/videos`)
4. Publish (`POST .../videos/{vid}/publish` or `.../drafts`) or schedule (`/schedule/*`)
"""

TAGS_METADATA = [
 {"name": "Auth", "description": "Register, log in, manage API tokens"},
 {"name": "Accounts", "description": "Connected TikTok accounts"},
 {"name": "Videos", "description": "Upload, list, edit and delete videos"},
 {"name": "Publishing", "description": "Send videos to TikTok"},
 {"name": "Analytics", "description": "Metrics and history"},
 {"name": "Scheduler", "description": "Auto-publish plan and queue"},
]


def create_app(settings: Settings | None = None) -> FastAPI:
 settings = settings or get_settings()
 configure_logging(debug=settings.debug)

 @asynccontextmanager
 async def lifespan(app: FastAPI) -> AsyncIterator[None]:
     engine = create_engine(settings.database_url, echo=False)
     http = httpx.AsyncClient(timeout=settings.tiktok_http_timeout_seconds)
     session_factory = create_session_factory(engine)

     from acm.db.uow import UnitOfWork

     uow_factory = lambda: UnitOfWork(session_factory)

     app.state.settings = settings
     app.state.engine = engine
     app.state.session_factory = session_factory
     app.state.file_storage = LocalFileStorage(Path(settings.upload_dir))
     app.state.tiktok_client = TikTokClient(http, TikTokClientConfig(
         client_key=settings.tiktok_client_key,
         client_secret=settings.tiktok_client_secret.get_secret_value(),
         redirect_uri=settings.tiktok_redirect_uri,
         scopes=settings.tiktok_scope_list,
         auth_base_url=settings.tiktok_auth_base_url,
         api_base_url=settings.tiktok_api_base_url,
     ))
     app.state.services = Services(
         uow_factory=uow_factory,
         tiktok_client=app.state.tiktok_client,
         storage=app.state.file_storage,
         settings=settings,
     )

     worker = asyncio.create_task(worker_loop(app.state.services))
     try:
         yield
     finally:
         worker.cancel()
         try:
             await worker
         except asyncio.CancelledError:
             pass
         await http.aclose()
         await engine.dispose()

 app = FastAPI(
     title="ACM API",
     version="1.0.0",
     description=DESCRIPTION,
     openapi_tags=TAGS_METADATA,
     lifespan=lifespan,
 )
 app.add_middleware(
     SessionMiddleware,
     secret_key=settings.secret_key.get_secret_value(),
     max_age=settings.session_max_age_seconds,
     same_site="lax",
     https_only=settings.session_https_only,
 )
 register_exception_handlers(app)

 # HTML (hidden from OpenAPI)
 app.include_router(health.router)
 app.include_router(pages.router)
 app.include_router(users.router)
 app.include_router(tiktok.router)
 app.include_router(studio.router)
 app.include_router(scheduler.router)

 # JSON API
 app.include_router(api_router)

 # OpenAPI security scheme: session cookie (Bearer tokens are documented per route via HTTPBearer)
 def custom_openapi():
     if app.openapi_schema:
         return app.openapi_schema
     schema = get_openapi(
         title=app.title,
         version=app.version,
         description=app.description,
         routes=app.routes,
         tags=TAGS_METADATA,
     )
     schema.setdefault("components", {}).setdefault("securitySchemes", {})["cookieAuth"] = {
         "type": "apiKey",
         "in": "cookie",
         "name": "session",
         "description": "Session cookie set by POST /api/v1/auth/login",
     }
     # Every /api/v1/* operation accepts either Bearer or cookie
     for path, ops in schema.get("paths", {}).items():
         if not path.startswith("/api/v1"):
             continue
         for op in ops.values():
             op.setdefault("security", []).append({"cookieAuth": []})
             op["security"].append({"bearerAuth": []})
     schema["components"]["securitySchemes"]["bearerAuth"] = {
         "type": "http",
         "scheme": "bearer",
         "description": "API token from POST /api/v1/auth/tokens",
     }
     app.openapi_schema = schema
     return schema

 app.openapi = custom_openapi  # type: ignore[method-assign]
 return app