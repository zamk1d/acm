import secrets


def generate_state() -> str:
    """Anti-forgery token for the OAuth `state` parameter."""
    return secrets.token_urlsafe(32)


def states_match(expected: str, received: str) -> bool:
    return secrets.compare_digest(expected.encode(), received.encode())
