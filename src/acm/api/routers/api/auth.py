from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from acm.api.deps import CurrentUser, CurrentUserId, ServicesDep, UserServiceDep
from acm.api.session import USER_ID_KEY, start_user_session
from acm.schemas.api_auth import (
    LoginRequest,
    RegisterRequest,
    TokenCreatedResponse,
    TokenCreateRequest,
    TokenRead,
    UserMe,
)

import secrets

from acm.repositories.api_token import hash_token

router = APIRouter(prefix="/auth", tags=["Auth"])
# Optional doc-only security scheme (see main.py for the global cookie scheme)
bearer_scheme = HTTPBearer(auto_error=False, description="API token (Authorization: Bearer acm_...)")


@router.post(
    "/register",
    response_model=UserMe,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user account",
)
async def register(
    request: Request, service: UserServiceDep, body: RegisterRequest
) -> UserMe:
    user = await service.register(body.email, body.password)
    start_user_session(request, user.id)
    return UserMe.model_validate(user)


@router.post("/login", response_model=UserMe, summary="Log in (sets a session cookie)")
async def login(request: Request, service: UserServiceDep, body: LoginRequest) -> UserMe:
    user = await service.authenticate(body.email, body.password)
    start_user_session(request, user.id)
    return UserMe.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Log out")
async def logout(request: Request) -> Response:
    request.session.clear()
    return Response(status_code=204)


@router.get("/me", response_model=UserMe, summary="Current user")
async def me(user: CurrentUser) -> UserMe:
    return UserMe.model_validate(user)


# --- API tokens ------------------------------------------------------------------------


@router.post(
    "/tokens",
    response_model=TokenCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an API token",
    description=(
        "Returns the plaintext token **once**. "
        "Use it as `Authorization: Bearer <token>` for all API calls."
    ),
)
async def create_token(
    user: CurrentUser, services: ServicesDep, body: TokenCreateRequest
) -> TokenCreatedResponse:
    plaintext = f"acm_{secrets.token_urlsafe(32)}"
    async with services.uow_factory() as uow:
        from acm.models.api_token import ApiToken

        token = ApiToken(user_id=user.id, name=body.name, token_hash=hash_token(plaintext))
        uow.api_tokens.add(token)
        await uow.commit()
        return TokenCreatedResponse(
            id=token.id, name=token.name, token=plaintext, created_at=token.created_at
        )


@router.get("/tokens", response_model=list[TokenRead], summary="List API tokens")
async def list_tokens(user: CurrentUser, services: ServicesDep) -> list[TokenRead]:
    async with services.uow_factory() as uow:
        tokens = await uow.api_tokens.list_by_user(user.id)
        return [TokenRead.model_validate(t) for t in tokens]


@router.delete(
    "/tokens/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an API token",
)
async def revoke_token(
    token_id: int, user: CurrentUser, services: ServicesDep
) -> Response:
    async with services.uow_factory() as uow:
        token = await uow.api_tokens.get_for_user(user.id, token_id)
        if token is not None:
            await uow.api_tokens.delete(token)
            await uow.commit()
    return Response(status_code=204)