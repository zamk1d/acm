import pytest
from httpx import AsyncClient
from fastapi import FastAPI
from acm.models import TikTokAccount
from acm.api.deps import get_current_user, get_current_user_id


@pytest.mark.asyncio
async def test_cannot_access_other_users_account(client: AsyncClient):
    resp = await client.get("/api/v1/accounts/999/videos")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cannot_access_other_users_video(client: AsyncClient, account_a: TikTokAccount):
    resp = await client.get(f"/api/v1/accounts/{account_a.id}/videos/999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_without_token(client: AsyncClient, app: FastAPI):
    # Временно удаляем переопределение авторизации
    backup_overrides = app.dependency_overrides.copy()
    app.dependency_overrides.pop(get_current_user_id, None)
    app.dependency_overrides.pop(get_current_user, None)

    try:
        resp = await client.get("/api/v1/accounts")
        # FastAPI вернет 401 или редирект на логин (303)
        assert resp.status_code in (401, 303)
    finally:
        # Возвращаем как было, чтобы не сломать другие тесты
        app.dependency_overrides = backup_overrides