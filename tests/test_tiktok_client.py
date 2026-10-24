from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from acm.integrations.tiktok import TikTokAPIError, TikTokClient, TikTokClientConfig
from acm.integrations.tiktok.scopes import fields_for_scopes


def make_client(handler: httpx.MockTransport | None = None) -> TikTokClient:
    http = httpx.AsyncClient(transport=handler)
    return TikTokClient(
        http,
        TikTokClientConfig(
            client_key="ck",
            client_secret="cs",
            redirect_uri="https://example.com/cb",
            scopes=["user.info.basic", "video.list"],
        ),
    )


def test_authorization_url() -> None:
    url = make_client().build_authorization_url("st4te")
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == (
        "https://www.tiktok.com/v2/auth/authorize/"
    )
    assert qs["client_key"] == ["ck"]
    assert qs["scope"] == ["user.info.basic,video.list"]
    assert qs["response_type"] == ["code"]
    assert qs["redirect_uri"] == ["https://example.com/cb"]
    assert qs["state"] == ["st4te"]


async def test_exchange_code_ok() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v2/oauth/token/"
        body = parse_qs(request.content.decode())
        assert body["grant_type"] == ["authorization_code"]
        assert body["code"] == ["abc"]
        return httpx.Response(
            200,
            json={
                "access_token": "at",
                "refresh_token": "rt",
                "open_id": "oid",
                "scope": "user.info.basic,video.list",
                "token_type": "Bearer",
                "expires_in": 86400,
                "refresh_expires_in": 31536000,
            },
        )

    tokens = await make_client(httpx.MockTransport(handler)).exchange_code("abc")
    assert tokens.open_id == "oid"
    assert tokens.scopes == ["user.info.basic", "video.list"]


async def test_oauth_error_body_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"error": "invalid_grant", "error_description": "bad code", "log_id": "L1"}
        )

    with pytest.raises(TikTokAPIError) as exc:
        await make_client(httpx.MockTransport(handler)).exchange_code("x")
    assert exc.value.code == "invalid_grant"
    assert exc.value.log_id == "L1"


async def test_get_user_info() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer at"
        assert request.url.params["fields"] == "open_id,display_name"
        return httpx.Response(
            200,
            json={
                "data": {"user": {"open_id": "oid", "display_name": "Neo"}},
                "error": {"code": "ok", "message": "", "log_id": "L"},
            },
        )

    client = make_client(httpx.MockTransport(handler))
    user = await client.get_user_info("at", ["open_id", "display_name"])
    assert user.display_name == "Neo"


async def test_user_info_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401, json={"data": {}, "error": {"code": "access_token_invalid", "message": "nope"}}
        )

    with pytest.raises(TikTokAPIError) as exc:
        await make_client(httpx.MockTransport(handler)).get_user_info("at", ["open_id"])
    assert exc.value.code == "access_token_invalid"


def test_fields_for_scopes() -> None:
    fields = fields_for_scopes(["user.info.basic", "user.info.stats", "video.list"])
    assert "open_id" in fields
    assert "follower_count" in fields
    assert "username" not in fields
