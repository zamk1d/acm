import logging
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta

from acm.core.exceptions import AccountNotFoundError, UpstreamError
from acm.core.time import utcnow
from acm.db.uow import UnitOfWork
from acm.integrations.tiktok import TikTokClient, TikTokUser, TokenResponse
from acm.integrations.tiktok.scopes import fields_for_scopes
from acm.models import TikTokAccount
from acm.schemas.account import AccountRead

logger = logging.getLogger(__name__)


class AuthService:
    """Use-cases around TikTok authorization. Knows nothing about HTTP/sessions."""

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        tiktok: TikTokClient,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._uow_factory = uow_factory
        self._tiktok = tiktok
        self._clock = clock

    def build_authorization_url(self, state: str) -> str:
        return self._tiktok.build_authorization_url(state)

    async def complete_login(self, code: str) -> AccountRead:
        tokens = await self._tiktok.exchange_code(code)
        user = await self._tiktok.get_user_info(
            tokens.access_token, fields_for_scopes(tokens.scopes)
        )

        async with self._uow_factory() as uow:
            account = await uow.tiktok_accounts.get_by_open_id(tokens.open_id)
            if account is None:
                account = TikTokAccount(open_id=tokens.open_id)
                uow.tiktok_accounts.add(account)
            self._apply_tokens(account, tokens)
            self._apply_profile(account, user)
            await uow.commit()
            logger.info("TikTok login completed open_id=%s", account.open_id)
            return AccountRead.model_validate(account)

    async def get_account(self, account_id: uuid.UUID) -> AccountRead:
        async with self._uow_factory() as uow:
            account = await uow.tiktok_accounts.get(account_id)
            if account is None:
                raise AccountNotFoundError()
            return AccountRead.model_validate(account)

    async def refresh_tokens(self, account_id: uuid.UUID) -> AccountRead:
        async with self._uow_factory() as uow:
            account = await uow.tiktok_accounts.get(account_id)
            if account is None:
                raise AccountNotFoundError()
            tokens = await self._tiktok.refresh_access_token(account.refresh_token)
            self._apply_tokens(account, tokens)
            await uow.commit()
            return AccountRead.model_validate(account)

    async def disconnect(self, account_id: uuid.UUID) -> None:
        async with self._uow_factory() as uow:
            account = await uow.tiktok_accounts.get(account_id)
            if account is None:
                raise AccountNotFoundError()
            try:
                await self._tiktok.revoke_token(account.access_token)
            except UpstreamError:
                # Token may already be expired/revoked; the user still wants the account gone.
                logger.warning("Token revoke failed open_id=%s", account.open_id, exc_info=True)
            await uow.tiktok_accounts.delete(account)
            await uow.commit()

    # --- helpers ---------------------------------------------------------------------------

    def _apply_tokens(self, account: TikTokAccount, tokens: TokenResponse) -> None:
        now = self._clock()
        account.access_token = tokens.access_token
        account.refresh_token = tokens.refresh_token
        account.scopes = ",".join(tokens.scopes)
        account.access_token_expires_at = now + timedelta(seconds=tokens.expires_in)
        account.refresh_token_expires_at = now + timedelta(seconds=tokens.refresh_expires_in)

    @staticmethod
    def _apply_profile(account: TikTokAccount, user: TikTokUser) -> None:
        account.union_id = user.union_id
        account.display_name = user.display_name
        account.avatar_url = user.avatar_large_url or user.avatar_url_100 or user.avatar_url
