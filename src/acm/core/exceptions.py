"""Application-level errors. The API layer maps them to HTTP responses."""


class AppError(Exception):
    status_code: int = 500
    default_message: str = "Internal error"

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)


class NotAuthenticatedError(AppError):
    status_code = 401
    default_message = "Not authenticated"


class AccountNotFoundError(AppError):
    status_code = 404
    default_message = "Account not found"


class InvalidOAuthStateError(AppError):
    status_code = 400
    default_message = "Invalid or expired OAuth state. Please try logging in again."


class OAuthDeniedError(AppError):
    status_code = 400
    default_message = "Authorization was denied"


class UpstreamError(AppError):
    """An external service (TikTok) failed or returned an error."""

    status_code = 502
    default_message = "Upstream service error"

class InvalidInputError(AppError):
    status_code = 422
    default_message = "Invalid input"


class EmailTakenError(AppError):
    status_code = 409
    default_message = "This email is already registered"


class InvalidCredentialsError(AppError):
    status_code = 401
    default_message = "Invalid email or password"


class AccountAlreadyLinkedError(AppError):
    status_code = 409
    default_message = "This TikTok account is already linked to another user"