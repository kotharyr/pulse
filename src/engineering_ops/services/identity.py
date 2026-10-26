"""Trusted request identity shared by MCP and the console; never read actor headers."""
from contextlib import contextmanager
from contextvars import ContextVar
from hashlib import sha256

from mcp.server.auth.middleware.auth_context import get_access_token

_actor = ContextVar("pulse_actor", default=None)


def token_actor(token: str) -> str:
    return "token:" + sha256(token.encode()).hexdigest()[:24]


def current_actor() -> str:
    if _actor.get():
        return _actor.get()
    token = get_access_token()
    return token.client_id if token else "local"


@contextmanager
def actor_context(actor: str):
    token = _actor.set(actor)
    try:
        yield
    finally:
        _actor.reset(token)
