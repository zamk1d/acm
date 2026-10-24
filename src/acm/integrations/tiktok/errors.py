from acm.core.exceptions import UpstreamError


class TikTokTransportError(UpstreamError):
    """Network-level failure talking to TikTok (timeout, DNS, connection reset)."""

    default_message = "Could not reach TikTok"


class TikTokAPIError(UpstreamError):
    """TikTok answered with an error payload."""

    def __init__(self, code: str, description: str = "", log_id: str | None = None) -> None:
        self.code = code
        self.description = description
        self.log_id = log_id
        text = f"TikTok error: {code}"
        if description:
            text += f" ({description})"
        super().__init__(text)
