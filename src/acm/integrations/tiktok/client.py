"""Thin async client for TikTok Login Kit (Web) + User Info.

Docs: https://developers.tiktok.com/doc/login-kit-web
      https://developers.tiktok.com/doc/login-kit-manage-user-access-tokens
      https://developers.tiktok.com/doc/tiktok-api-v2-get-user-info
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from acm.integrations.tiktok.errors import TikTokAPIError, TikTokTransportError
from acm.integrations.tiktok.schemas import TikTokUser, TokenResponse

AUTHORIZE_PATH = "/v2/auth/authorize/"
TOKEN_PATH = "/v2/oauth/token/"
REVOKE_PATH = "/v2/oauth/revoke/"
USER_INFO_PATH = "/v2/user/info/"


@dataclass(frozen=True, slots=True)
class TikTokClientConfig:
    client_key: str
    client_secret: str
    redirect_uri: str
    scopes: Sequence[str]
    auth_base_url: str = "https://www.tiktok.com"
    api_base_url: str = "https://open.tiktokapis.com"


class TikTokClient:
    def __init__(self, http: httpx.AsyncClient, config: TikTokClientConfig) -> None:
        self._http = http
        self._config = config

    # --- authorization (browser redirect) ---------------------------------------------------

    def build_authorization_url(self, state: str) -> str:
        params = {
            "client_key": self._config.client_key,
            "scope": ",".join(self._config.scopes),
            "response_type": "code",
            "redirect_uri": self._config.redirect_uri,
            "state": state,
        }
        query = urlencode(params, quote_via=quote, safe=",")
        return f"{self._config.auth_base_url}{AUTHORIZE_PATH}?{query}"

    # --- token management ------------------------------------------------------------------

    async def exchange_code(self, code: str) -> TokenResponse:
        payload = await self._post_form(
            TOKEN_PATH,
            {
                "client_key": self._config.client_key,
                "client_secret": self._config.client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": self._config.redirect_uri,
            },
        )
        return TokenResponse.model_validate(payload)

    async def refresh_access_token(self, refresh_token: str) -> TokenResponse:
        payload = await self._post_form(
            TOKEN_PATH,
            {
                "client_key": self._config.client_key,
                "client_secret": self._config.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
        return TokenResponse.model_validate(payload)

    async def revoke_token(self, token: str) -> None:
        await self._post_form(
            REVOKE_PATH,
            {
                "client_key": self._config.client_key,
                "client_secret": self._config.client_secret,
                "token": token,
            },
        )

    # --- resources -------------------------------------------------------------------------

    async def get_user_info(self, access_token: str, fields: Sequence[str]) -> TikTokUser:
        payload = await self._request(
            "GET",
            USER_INFO_PATH,
            params={"fields": ",".join(fields)},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        try:
            return TikTokUser.model_validate(payload["data"]["user"])
        except (KeyError, TypeError, ValueError) as exc:
            raise TikTokAPIError("invalid_response", "Unexpected user info payload") from exc

    # --- internals -------------------------------------------------------------------------

    async def _post_form(self, path: str, data: dict[str, str]) -> dict[str, Any]:
        return await self._request(
            "POST",
            path,
            data=data,
            headers={"Cache-Control": "no-cache"},
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self._config.api_base_url}{path}"
        try:
            response = await self._http.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise TikTokTransportError() from exc
        return self._parse(response)

    @staticmethod
    def _parse(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if not isinstance(payload, dict):
            if response.is_error:
                raise TikTokAPIError(f"http_{response.status_code}")
            raise TikTokAPIError("invalid_response", "Response is not a JSON object")

        error = _extract_error(payload)
        if error is not None:
            code, description, log_id = error
            raise TikTokAPIError(code, description, log_id)
        if response.is_error:
            raise TikTokAPIError(f"http_{response.status_code}")
        return payload


def _extract_error(payload: dict[str, Any]) -> tuple[str, str, str | None] | None:
    """Handles both error shapes:
    - OAuth endpoints: {"error": "invalid_grant", "error_description": "...", "log_id": "..."}
    - API endpoints:   {"error": {"code": "ok" | "<code>", "message": "...", "log_id": "..."}}
    """
    error = payload.get("error")
    if not error:
        return None
    if isinstance(error, dict):
        code = str(error.get("code", "unknown"))
        if code == "ok":
            return None
        return code, str(error.get("message", "")), error.get("log_id")
    return str(error), str(payload.get("error_description", "")), payload.get("log_id")
