from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from acm.core.config import Settings
from acm.main import create_app


def test_login_redirects_to_tiktok_with_state(settings: Settings) -> None:
    with TestClient(create_app(settings), follow_redirects=False) as client:
        resp = client.get("/auth/tiktok/login")
        assert resp.status_code == 302
        location = urlparse(resp.headers["location"])
        assert location.netloc == "www.tiktok.com"
        assert parse_qs(location.query)["state"][0]


def test_callback_rejects_wrong_state(settings: Settings) -> None:
    with TestClient(create_app(settings), follow_redirects=False) as client:
        client.get("/auth/tiktok/login")
        resp = client.get("/auth/tiktok/callback", params={"code": "c", "state": "forged"})
        assert resp.status_code == 400


def test_callback_reports_user_denial(settings: Settings) -> None:
    with TestClient(create_app(settings), follow_redirects=False) as client:
        resp = client.get(
            "/auth/tiktok/callback",
            params={"error": "access_denied", "error_description": "User cancelled"},
        )
        assert resp.status_code == 400
        assert "User cancelled" in resp.text


def test_dashboard_requires_login(settings: Settings) -> None:
    with TestClient(create_app(settings), follow_redirects=False) as client:
        resp = client.get("/dashboard")
        assert resp.status_code == 303
        assert resp.headers["location"] == "/"
