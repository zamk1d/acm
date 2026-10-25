import pytest
from httpx import AsyncClient
from acm.models import TikTokAccount
from acm.core.config import Settings

@pytest.mark.asyncio
async def test_upload_invalid_extension(client: AsyncClient, account_a: TikTokAccount):
    files = {"file": ("virus.exe", b"fake", "application/octet-stream")}
    data = {"title": "test", "description": ""}
    resp = await client.post(f"/api/v1/accounts/{account_a.id}/videos", files=files, data=data)
    assert resp.status_code == 415

@pytest.mark.asyncio
async def test_upload_invalid_mime_type(client: AsyncClient, account_a: TikTokAccount):
    files = {"file": ("fake.mp4", b"text", "text/plain")}
    data = {"title": "test", "description": ""}
    resp = await client.post(f"/api/v1/accounts/{account_a.id}/videos", files=files, data=data)
    assert resp.status_code == 415

@pytest.mark.asyncio
async def test_upload_exceed_max_size(client: AsyncClient, account_a: TikTokAccount, settings: Settings):
    settings.max_upload_bytes = 10
    files = {"file": ("test.mp4", b"0123456789ABC", "video/mp4")}
    data = {"title": "test", "description": ""}
    resp = await client.post(f"/api/v1/accounts/{account_a.id}/videos", files=files, data=data)
    assert resp.status_code == 413