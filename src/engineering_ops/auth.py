from __future__ import annotations

import hmac

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
