import uuid

from fastapi import Request

OAUTH_STATE_KEY = "oauth_state"
USER_ID_KEY = "user_id"


def start_user_session(request: Request, user_id: uuid.UUID) -> None:
    request.session.clear()  # fresh session on login (prevents session fixation)
    request.session[USER_ID_KEY] = str(user_id)