import uuid

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from acm.api.deps import CurrentUserId, TikTokServiceDep
from acm.api.session import OAUTH_STATE_KEY
from acm.core.exceptions import InvalidOAuthStateError, OAuthDeniedError
from acm.core.security import generate_state, states_match

# NOTE: /auth/tiktok/callback is the Redirect URI registered in the TikTok portal.
router = APIRouter(prefix="/auth/tiktok", tags=["tiktok"])


@router.get("/login")
async def connect_start(
    request: Request, user_id: CurrentUserId, service: TikTokServiceDep
) -> RedirectResponse:
    state = generate_state()
    request.session[OAUTH_STATE_KEY] = state
    return RedirectResponse(service.build_authorization_url(state), status_code=302)


@router.get("/callback")
async def callback(
    request: Request,
    user_id: CurrentUserId,
    service: TikTokServiceDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> RedirectResponse:
    expected_state = request.session.pop(OAUTH_STATE_KEY, None)  # one-time use

    if error:
        raise OAuthDeniedError(error_description or error)
    if not expected_state or not state or not states_match(expected_state, state):
        raise InvalidOAuthStateError()
    if not code:
        raise OAuthDeniedError("Authorization code is missing")

    # The user is already logged in to OUR service; we only attach the TikTok account to them.
    await service.connect_account(user_id, code)
    return RedirectResponse("/dashboard", status_code=303)


@router.post("/{account_id}/refresh")
async def refresh(
    account_id: int, user_id: CurrentUserId, service: TikTokServiceDep
) -> RedirectResponse:
    await service.refresh_tokens(user_id, account_id)
    return RedirectResponse("/dashboard", status_code=303)


@router.post("/{account_id}/disconnect")
async def disconnect(
    account_id: int, user_id: CurrentUserId, service: TikTokServiceDep
) -> RedirectResponse:
    await service.disconnect(user_id, account_id)
    return RedirectResponse("/dashboard", status_code=303)