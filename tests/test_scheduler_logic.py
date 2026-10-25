import pytest
from httpx import AsyncClient
from acm.models import TikTokAccount, Video

@pytest.mark.asyncio
async def test_scheduler_invalid_timezone(client: AsyncClient, account_a: TikTokAccount):
    payload = {
        "enabled": True,
        "timezone": "UTC+2", # Invalid, must be IANA
        "posts_per_day": 1,
        "window_start": "09:00:00",
        "window_end": "17:00:00",
        "weekdays": [0,1,2,3,4],
        "method": "draft",
        "privacy_level": "SELF_ONLY",
    }
    resp = await client.put(f"/api/v1/accounts/{account_a.id}/schedule", json=payload)
    assert resp.status_code == 422
    assert "Unknown timezone" in resp.text

@pytest.mark.asyncio
async def test_scheduler_end_before_start(client: AsyncClient, account_a: TikTokAccount):
    payload = {
        "enabled": True,
        "timezone": "Europe/Tallinn",
        "posts_per_day": 1,
        "window_start": "17:00:00",
        "window_end": "09:00:00", # Before start
        "weekdays": [0],
        "method": "draft",
        "privacy_level": "SELF_ONLY",
    }
    resp = await client.put(f"/api/v1/accounts/{account_a.id}/schedule", json=payload)
    assert resp.status_code == 422
    assert "end of the time window must be after its start" in resp.text

@pytest.mark.asyncio
async def test_publishing_queued_video(client: AsyncClient, account_a: TikTokAccount, queued_video: Video):
    resp = await client.post(
        f"/api/v1/accounts/{account_a.id}/videos/{queued_video.id}/publish",
        json={"method": "direct", "privacy_level": "SELF_ONLY"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "publishing"