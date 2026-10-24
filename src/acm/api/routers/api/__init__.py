# acm/api/routers/api/__init__.py
from fastapi import APIRouter

from acm.api.routers.api import (
    accounts,
    analytics,
    auth,
    publishing,
    scheduler,
    videos,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(accounts.router)
api_router.include_router(videos.router)
api_router.include_router(publishing.router)
api_router.include_router(analytics.router)
api_router.include_router(scheduler.router)