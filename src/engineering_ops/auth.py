from __future__ import annotations

import hmac
from functools import wraps

from starlette.responses import JSONResponse

from mcp.server.auth.provider import AccessToken


class StaticBearerTokenVerifier:
    """Constant-time verifier for a deployment-managed MCP bearer token."""

    def __init__(self, expected_token: str):
        self._expected_token = expected_token

    async def verify_token(self, token: str) -> AccessToken | None:
        if not hmac.compare_digest(token, self._expected_token):
            return None
        return AccessToken(
            token=token,
            client_id="engineering-ops-client",
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
        return await handler(request)
    return authenticated
