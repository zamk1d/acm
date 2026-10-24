"""Thin async client for the TikTok APIs we use: Login Kit, Display API, Content Posting API.

Docs: https://developers.tiktok.com/doc/login-kit-web
      https://developers.tiktok.com/doc/tiktok-api-v2-video-list
      https://developers.tiktok.com/doc/content-posting-api-get-started
"""

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from acm.integrations.tiktok.errors import TikTokAPIError, TikTokTransportError
from acm.integrations.tiktok.media import ChunkPlan
from acm.integrations.tiktok.schemas import (
    TikTokCreatorInfo,
    TikTokPostStatus,
    TikTokUser,
    TikTokVideo,
    TikTokVideoPage,
    TikTokVideoPost,
    TokenResponse,
)

logger = logging.getLogger(__name__)

AUTHORIZE_PATH = "/v2/auth/authorize/"
TOKEN_PATH = "/v2/oauth/token/"
REVOKE_PATH = "/v2/oauth/revoke/"
USER_INFO_PATH = "/v2/user/info/"
VIDEO_LIST_PATH = "/v2/video/list/"
VIDEO_QUERY_PATH = "/v2/video/query/"
CREATOR_INFO_PATH = "/v2/post/publish/creator_info/query/"
DIRECT_POST_PATH = "/v2/post/publish/video/init/"
INBOX_UPLOAD_PATH = "/v2/post/publish/inbox/video/init/"
POST_STATUS_PATH = "/v2/post/publish/status/fetch/"

# Uploading a big file is slow: generous write timeout for chunks, short for everything else.
UPLOAD_TIMEOUT = httpx.Timeout(10.0, write=300.0)


@dataclass(frozen=True, slots=True)
class TikTokClientConfig:
    client_key: str
    client_secret: str
    redirect_uri: str
    scopes: Sequence[str]
    auth_base_url: str = "https://www.tiktok.com"
    api_base_url: str = "https://open.tiktokapis.com"


@dataclass(frozen=True, slots=True)
class DirectPostInfo:
    """`post_info` of a Direct Post (what the viewer will see on TikTok)."""

    caption: str  # TikTok calls it `title`; up to 2200 chars, may contain #hashtags and @mentions
    privacy_level: str
    disable_comment: bool = False
    disable_duet: bool = False
    disable_stitch: bool = False
    is_aigc: bool = False
    brand_content_toggle: bool = False
    brand_organic_toggle: bool = False
    cover_timestamp_ms: int | None = None


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

    # --- Display API: profile and videos ---------------------------------------------------

    async def get_user_info(self, access_token: str, fields: Sequence[str]) -> TikTokUser:
        payload = await self._request(
            "GET",
            USER_INFO_PATH,
            params={"fields": ",".join(fields)},
            headers=_bearer(access_token),
        )
        try:
            return TikTokUser.model_validate(payload["data"]["user"])
        except (KeyError, TypeError, ValueError) as exc:
            raise TikTokAPIError("invalid_response", "Unexpected user info payload") from exc

    async def get_user_videos(
        self,
        access_token: str,
        fields: Sequence[str],
        *,
        cursor: int | None = None,
        max_count: int = 20,
    ) -> TikTokVideoPage:
        """Needs `video.list`. max_count is capped by TikTok at 20."""
        body: dict[str, int] = {"max_count": max_count}
        if cursor is not None:  # TikTok expects an int or no key at all, never null
            body["cursor"] = cursor
        payload = await self._request(
            "POST",
            VIDEO_LIST_PATH,
            params={"fields": ",".join(fields)},
            json=body,
            headers=_bearer(access_token),
        )
        try:
            return TikTokVideoPage.model_validate(payload["data"])
        except (KeyError, TypeError, ValueError) as exc:
            raise TikTokAPIError("invalid_response", "Unexpected video list payload") from exc

    async def query_videos(
        self, access_token: str, video_ids: Sequence[str], fields: Sequence[str]
    ) -> list[TikTokVideo]:
        """Details of specific videos (max 20). TikTok verifies they belong to the token's user,
        so ids of other people's videos simply don't come back. Needs `video.list`."""
        payload = await self._request(
            "POST",
            VIDEO_QUERY_PATH,
            params={"fields": ",".join(fields)},
            json={"filters": {"video_ids": list(video_ids)}},
            headers=_bearer(access_token),
        )
        try:
            return TikTokVideoPage.model_validate(payload["data"]).videos
        except (KeyError, TypeError, ValueError) as exc:
            raise TikTokAPIError("invalid_response", "Unexpected video query payload") from exc

    # --- Content Posting API ---------------------------------------------------------------

    async def query_creator_info(self, access_token: str) -> TikTokCreatorInfo:
        """Must be called before a Direct Post: it says which privacy levels etc. are allowed."""
        payload = await self._request(
            "POST",
            CREATOR_INFO_PATH,
            headers={**_bearer(access_token), "Content-Type": "application/json; charset=UTF-8"},
        )
        try:
            return TikTokCreatorInfo.model_validate(payload["data"])
        except (KeyError, TypeError, ValueError) as exc:
            raise TikTokAPIError("invalid_response", "Unexpected creator info payload") from exc

    async def init_direct_post(
        self, access_token: str, info: DirectPostInfo, plan: ChunkPlan
    ) -> TikTokVideoPost:
        """Needs `video.publish`. Posts to the creator's profile once the upload is processed."""
        post_info: dict[str, Any] = {
            "title": info.caption,
            "privacy_level": info.privacy_level,
            "disable_comment": info.disable_comment,
            "disable_duet": info.disable_duet,
            "disable_stitch": info.disable_stitch,
            "is_aigc": info.is_aigc,
            "brand_content_toggle": info.brand_content_toggle,
            "brand_organic_toggle": info.brand_organic_toggle,
        }
        if info.cover_timestamp_ms is not None:
            post_info["video_cover_timestamp_ms"] = info.cover_timestamp_ms
        return await self._init_upload(
            DIRECT_POST_PATH, access_token, {"post_info": post_info, "source_info": _source(plan)}
        )

    async def init_inbox_upload(self, access_token: str, plan: ChunkPlan) -> TikTokVideoPost:
        """Needs `video.upload`. The video lands in the creator's TikTok drafts (inbox);
        they finish and publish it in the TikTok app. No post_info: nothing to configure here."""
        return await self._init_upload(INBOX_UPLOAD_PATH, access_token, {"source_info": _source(plan)})

    async def upload_video_file(
        self, upload_url: str, path: Path, plan: ChunkPlan, content_type: str
    ) -> None:
        """PUTs the file to `upload_url` chunk by chunk (reading from disk off the event loop)."""
        for start, end in plan.ranges():
            chunk = await asyncio.to_thread(_read_range, path, start, end)
            headers = {
                "Content-Type": content_type,
                "Content-Range": f"bytes {start}-{end}/{plan.video_size}",
            }
            try:
                response = await self._http.put(
                    upload_url, content=chunk, headers=headers, timeout=UPLOAD_TIMEOUT
                )
            except httpx.HTTPError as exc:
                raise TikTokTransportError() from exc
            # 206 = chunk accepted, more expected; 201 = last chunk accepted. Body is empty.
            if response.status_code not in (200, 201, 206):
                raise TikTokAPIError(f"upload_http_{response.status_code}", "Chunk upload failed")

    async def check_posting_status(self, access_token: str, publish_id: str) -> TikTokPostStatus:
        payload = await self._request(
            "POST",
            POST_STATUS_PATH,
            json={"publish_id": publish_id},
            headers={**_bearer(access_token), "Content-Type": "application/json; charset=UTF-8"},
        )
        try:
            return TikTokPostStatus.model_validate(payload["data"])
        except (KeyError, TypeError, ValueError) as exc:
            raise TikTokAPIError("invalid_response", "Unexpected publish status payload") from exc

    # --- internals -------------------------------------------------------------------------

    async def _init_upload(
        self, path: str, access_token: str, body: dict[str, Any]
    ) -> TikTokVideoPost:
        payload = await self._request(
            "POST",
            path,
            json=body,
            headers={**_bearer(access_token), "Content-Type": "application/json; charset=UTF-8"},
        )
        try:
            return TikTokVideoPost.model_validate(payload["data"])
        except (KeyError, TypeError, ValueError) as exc:
            raise TikTokAPIError("invalid_response", "Unexpected upload init payload") from exc

    async def _post_form(self, path: str, data: dict[str, str]) -> dict[str, Any]:
        return await self._request("POST", path, data=data, headers={"Cache-Control": "no-cache"})

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


def _bearer(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _source(plan: ChunkPlan) -> dict[str, Any]:
    return {
        "source": "FILE_UPLOAD",
        "video_size": plan.video_size,
        "chunk_size": plan.chunk_size,
        "total_chunk_count": plan.total_chunk_count,
    }


def _read_range(path: Path, start: int, end: int) -> bytes:
    with path.open("rb") as fh:
        fh.seek(start)
        return fh.read(end - start + 1)


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
