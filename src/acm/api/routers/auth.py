from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from acm.api.deps import AuthServiceDep, CurrentAccountId
from acm.api.session import ACCOUNT_ID_KEY, OAUTH_STATE_KEY
from acm.core.exceptions import InvalidOAuthStateError, OAuthDeniedError
from acm.core.security import generate_state, states_match

router = APIRouter(tags=["auth"])


@router.get("/auth/tiktok/login")
async def login(request: Request, service: AuthServiceDep) -> RedirectResponse:
    state = generate_state()
    request.session[OAUTH_STATE_KEY] = state
    return RedirectResponse(service.build_authorization_url(state), status_code=302)


@router.get("/auth/tiktok/callback")
async def callback(
    request: Request,
    service: AuthServiceDep,
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

    account = await service.complete_login(code)

    request.session.clear()  # new session after login (prevents session fixation)
    request.session[ACCOUNT_ID_KEY] = str(account.id)
    return RedirectResponse("/dashboard", status_code=303)


@router.post("/auth/tiktok/refresh")
async def refresh(account_id: CurrentAccountId, service: AuthServiceDep) -> RedirectResponse:
    await service.refresh_tokens(account_id)
    return RedirectResponse("/dashboard", status_code=303)


@router.post("/auth/tiktok/disconnect")
async def disconnect(
    request: Request, account_id: CurrentAccountId, service: AuthServiceDep
) -> RedirectResponse:
    await service.disconnect(account_id)
    request.session.clear()
    return RedirectResponse("/", status_code=303)


@router.post("/auth/logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse("/", status_code=303)
