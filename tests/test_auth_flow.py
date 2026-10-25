from urllib.parse import parse_qs, urlparse
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_login_redirects_to_tiktok_with_state(client: AsyncClient) -> None:
    resp = await client.get("/auth/tiktok/login", follow_redirects=False)
    assert resp.status_code == 302
    location = urlparse(resp.headers["location"])
    assert location.netloc == "www.tiktok.com"
    assert parse_qs(location.query)["state"][0]

@pytest.mark.asyncio
async def test_callback_rejects_wrong_state(client: AsyncClient) -> None:
    await client.get("/auth/tiktok/login", follow_redirects=False)
    resp = await client.get("/auth/tiktok/callback", params={"code": "c", "state": "forged"}, follow_redirects=False)
    assert resp.status_code == 400

@pytest.mark.asyncio
async def test_callback_reports_user_denial(client: AsyncClient) -> None:
    resp = await client.get(
        "/auth/tiktok/callback",
        params={"error": "access_denied", "error_description": "User cancelled"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "User cancelled" in resp.text