from fastapi import APIRouter, Query, status
from fastapi.responses import RedirectResponse

from acm.api.deps import CurrentUser, CurrentUserId, TikTokServiceDep
from acm.core.security import generate_state
from acm.schemas.account import AccountRead

router = APIRouter(prefix="/accounts", tags=["Accounts"])


@router.get("", response_model=list[AccountRead], summary="List connected TikTok accounts")
async def list_accounts(user: CurrentUser, service: TikTokServiceDep) -> list[AccountRead]:
    return await service.list_accounts(user.id)


@router.get("/{account_id}", response_model=AccountRead, summary="Get one account")
async def get_account(
    account_id: int, user_id: CurrentUserId, service: TikTokServiceDep
) -> AccountRead:
    return await service.get_account(user_id, account_id)


@router.post(
    "/{account_id}/refresh",
    response_model=AccountRead,
    summary="Refresh access token",
)
async def refresh(
    account_id: int, user_id: CurrentUserId, service: TikTokServiceDep
) -> AccountRead:
    return await service.refresh_tokens(user_id, account_id)


@router.delete(
    "/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Disconnect and revoke a TikTok account",
)
async def disconnect(
    account_id: int, user_id: CurrentUserId, service: TikTokServiceDep
):
    await service.disconnect(user_id, account_id)


@router.get(
    "/connect-url",
    summary="Get TikTok OAuth URL",
    description=(
        "Returns the URL to send the user to. "
        "After the user approves on TikTok, TikTok redirects them to the configured "
        "callback which attaches the account. For headless clients, follow the URL "
        "in a browser and then call `GET /accounts` to see the new account."
    ),
)
async def connect_url(
    user: CurrentUser,
    service: TikTokServiceDep,
    request_state: str | None = Query(default=None, description="Optional CSRF state"),
) -> dict[str, str]:
    state = request_state or generate_state()
    return {"url": service.build_authorization_url(state), "state": state}