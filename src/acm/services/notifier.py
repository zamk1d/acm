import html
import logging

import httpx

from acm.core.config import Settings
from acm.models.video import Video

logger = logging.getLogger(__name__)

TELEGRAM_BASE = "https://api.telegram.org/bot{token}/{method}"


class TelegramNotifier:
    """Sends short notifications to the user's Telegram chat.

    Failures are swallowed and logged: a Telegram hiccup must never break publishing.
    """

    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http
        self._token = (
            settings.telegram_bot_token.get_secret_value()
            if settings.telegram_bot_token
            else None
        )
        self._enabled = settings.telegram_enabled and bool(self._token)
        # explicit override from .env (TELEGRAM_BOT_USERNAME); skips getMe when set
        self._bot_username: str | None = settings.telegram_bot_username or None

    def _url(self, method: str) -> str:
        return TELEGRAM_BASE.format(token=self._token, method=method)

    async def bot_username(self) -> str | None:
        """The bot's @username. From .env if set, otherwise discovered once via getMe."""
        if self._bot_username is not None:
            return self._bot_username
        if not self._enabled:
            return None
        try:
            response = await self._http.get(self._url("getMe"), timeout=5.0)
            response.raise_for_status()
            username = (response.json().get("result") or {}).get("username")
            if username:
                self._bot_username = username
            return username
        except httpx.HTTPError:
            logger.warning("Telegram getMe failed", exc_info=True)
            return None

    async def draft_uploaded(self, chat_id: str | None, video: Video) -> None:
        if not self._enabled or not chat_id:
            return
        title = video.title or "Untitled"
        text = (
            "✅ <b>Video uploaded to TikTok drafts</b>\n\n"
            "📹 <b>Title:</b>\n"
            f"<code>{html.escape(title)}</code>\n\n"
            "<i>Tap the title to copy it.</i>"
        )
        await self._send(chat_id, text)

    async def send_test(self, chat_id: str) -> None:
        await self._send(
            chat_id,
            "🔔 <b>Test message</b>\n\n<code>Tap this text to copy it</code>",
        )

    async def _send(self, chat_id: str, text: str) -> None:
        if not self._enabled:
            return
        try:
            response = await self._http.post(
                self._url("sendMessage"),
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=10.0,
            )
            if response.is_error:
                logger.warning(
                    "Telegram sendMessage failed chat_id=%s status=%s body=%s",
                    chat_id,
                    response.status_code,
                    response.text[:200],
                )
        except httpx.HTTPError:
            logger.warning("Telegram is unreachable chat_id=%s", chat_id, exc_info=True)