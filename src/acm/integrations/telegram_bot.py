"""Long-polling Telegram bot: answers with the user's chat_id.

Just enough to let people discover their chat_id and paste it into the dashboard.
Runs in the background; safe to cancel on shutdown.
"""

import asyncio
import logging

import httpx

from acm.core.config import Settings

logger = logging.getLogger(__name__)

TELEGRAM_BASE = "https://api.telegram.org/bot{token}/{method}"
POLL_TIMEOUT = 30  # long polling window, seconds


class TelegramBot:
    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http
        self._token = (
            settings.telegram_bot_token.get_secret_value()
            if settings.telegram_bot_token
            else None
        )
        self._enabled = settings.telegram_enabled and bool(self._token)
        self._offset: int | None = None

    def _url(self, method: str) -> str:
        return TELEGRAM_BASE.format(token=self._token, method=method)

    async def run(self) -> None:
        if not self._enabled:
            logger.info("Telegram bot disabled (no token)")
            return
        await self._drop_webhook()
        logger.info("Telegram bot polling started")
        while True:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Telegram bot poll failed, retrying in 5s")
                await asyncio.sleep(5)

    async def _drop_webhook(self) -> None:
        # getUpdates returns nothing while a webhook is set; drop it so polling works.
        try:
            await self._http.get(self._url("deleteWebhook"), timeout=5.0)
        except httpx.HTTPError:
            logger.warning("Could not delete Telegram webhook", exc_info=True)

    async def _poll_once(self) -> None:
        params: dict[str, object] = {"timeout": POLL_TIMEOUT}
        if self._offset is not None:
            params["offset"] = self._offset
        response = await self._http.get(
            self._url("getUpdates"),
            params=params,
            timeout=POLL_TIMEOUT + 10,  # let the long poll finish
        )
        response.raise_for_status()
        for update in response.json().get("result", []):
            self._offset = update["update_id"] + 1  # advance BEFORE handling
            await self._handle(update)

    async def _handle(self, update: dict) -> None:
        message = update.get("message") or update.get("edited_message")
        if not message:
            return
        chat_id = (message.get("chat") or {}).get("id")
        text = message.get("text") or ""
        if not chat_id:
            return
        if text.startswith("/start"):
            await self._send(
                chat_id,
                "👋 <b>ACM bot</b>\n\n"
                "Your chat ID:\n"
                f"<code>{chat_id}</code>\n\n"
                "<i>Tap the number to copy it, then paste it into the dashboard.</i>",
            )
        else:
            await self._send(chat_id, f"Your chat ID:\n<code>{chat_id}</code>")

    async def _send(self, chat_id: int, text: str) -> None:
        try:
            await self._http.post(
                self._url("sendMessage"),
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=10.0,
            )
        except httpx.HTTPError:
            logger.warning("Telegram bot reply failed chat_id=%s", chat_id, exc_info=True)