import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_oauth_callback_invalid_state(client: AsyncClient):
    resp = await client.get("/auth/tiktok/callback?code=123&state=forged", follow_redirects=False)
    assert resp.status_code == 400
    assert "Invalid or expired OAuth state" in resp.text


@pytest.mark.asyncio
async def test_oauth_callback_missing_code(client: AsyncClient):
    resp_login = await client.get("/auth/tiktok/login", follow_redirects=False)
    location = resp_login.headers["location"]
    state = location.split("state=")[1]

    resp = await client.get(f"/auth/tiktok/callback?state={state}", follow_redirects=False)
    assert resp.status_code == 400
    assert "Authorization code is missing" in resp.text