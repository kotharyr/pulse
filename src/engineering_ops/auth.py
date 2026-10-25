from __future__ import annotations

import hmac
from functools import wraps

from starlette.responses import JSONResponse

from mcp.server.auth.provider import AccessToken

from engineering_ops.services.identity import actor_context, token_actor


class StaticBearerTokenVerifier:
    """Constant-time verifier for a deployment-managed MCP bearer token."""

    def __init__(self, expected_token: str):
        self._expected_token = expected_token

    async def verify_token(self, token: str) -> AccessToken | None:
        if not hmac.compare_digest(token, self._expected_token):
            return None
        return AccessToken(
            token=token,
            client_id=token_actor(self._expected_token),
            scopes=["mcp:tools"],
        )


def protect_http_route(handler, expected_token: str):
    """Apply the configured bearer credential to custom routes as well as MCP."""
    @wraps(handler)
    async def authenticated(request):
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.casefold() != "bearer" or not hmac.compare_digest(token.encode(), expected_token.encode()):
            return JSONResponse(
                {"error": "Authentication required"}, status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        with actor_context(token_actor(expected_token)):
            return await handler(request)
    return authenticated
