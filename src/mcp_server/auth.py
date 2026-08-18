from __future__ import annotations

import hashlib
import secrets

from mcp.server.auth.provider import AccessToken, TokenVerifier


class StaticBearerTokenVerifier(TokenVerifier):
    """Verify one pre-issued bearer token for the learning server."""

    def __init__(self, token: str, *, scope: str) -> None:
        if len(token) < 16:
            raise ValueError("SIGNALDESK_MCP_TOKEN must contain at least 16 characters")
        if token != token.strip():
            raise ValueError("SIGNALDESK_MCP_TOKEN must not have surrounding whitespace")
        self._token_digest = hashlib.sha256(token.encode("utf-8")).digest()
        self._scope = scope

    async def verify_token(self, token: str) -> AccessToken | None:
        candidate_digest = hashlib.sha256(token.encode("utf-8")).digest()
        if not secrets.compare_digest(candidate_digest, self._token_digest):
            return None
        return AccessToken(
            token=token,
            client_id="signaldesk-preissued-client",
            scopes=[self._scope],
            subject="signaldesk-local-user",
        )
