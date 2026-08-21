from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError


SESSION_COOKIE = "signaldesk_session"
CSRF_HEADER = "x-signaldesk-csrf"


class SessionClaims(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(pattern=r"^USR-[a-f0-9]{16}$")
    reviewer_id: str = Field(min_length=3, max_length=100)
    csrf_token: str = Field(min_length=32, max_length=128)
    expires_at: int


class InvalidSessionError(ValueError):
    pass


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


@dataclass(frozen=True)
class IssuedSession:
    token: str
    claims: SessionClaims


class SessionManager:
    def __init__(
        self,
        access_code: str,
        session_secret: str,
        *,
        ttl_seconds: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._access_code_digest = hashlib.sha256(access_code.encode()).digest()
        self._secret = session_secret.encode()
        self._ttl_seconds = ttl_seconds
        self._clock = clock

    def authenticate(self, access_code: str, reviewer_id: str) -> IssuedSession:
        candidate = hashlib.sha256(access_code.encode()).digest()
        if not hmac.compare_digest(candidate, self._access_code_digest):
            raise InvalidSessionError("Invalid workspace credentials")
        user_digest = hashlib.sha256(reviewer_id.casefold().encode()).hexdigest()[:16]
        claims = SessionClaims(
            user_id=f"USR-{user_digest}",
            reviewer_id=reviewer_id,
            csrf_token=secrets.token_urlsafe(32),
            expires_at=int(self._clock()) + self._ttl_seconds,
        )
        payload = json.dumps(
            claims.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        encoded_payload = _encode(payload)
        signature = hmac.new(
            self._secret,
            encoded_payload.encode(),
            hashlib.sha256,
        ).digest()
        return IssuedSession(
            token=f"{encoded_payload}.{_encode(signature)}",
            claims=claims,
        )

    def verify(self, token: str) -> SessionClaims:
        try:
            encoded_payload, encoded_signature = token.split(".", maxsplit=1)
            supplied_signature = _decode(encoded_signature)
            expected_signature = hmac.new(
                self._secret,
                encoded_payload.encode(),
                hashlib.sha256,
            ).digest()
            if not hmac.compare_digest(supplied_signature, expected_signature):
                raise InvalidSessionError("Invalid session")
            claims = SessionClaims.model_validate_json(_decode(encoded_payload))
        except (ValueError, TypeError, json.JSONDecodeError, ValidationError) as exc:
            raise InvalidSessionError("Invalid session") from exc
        if claims.expires_at <= int(self._clock()):
            raise InvalidSessionError("Session expired")
        return claims

    @staticmethod
    def verify_csrf(claims: SessionClaims, supplied_token: str | None) -> None:
        if supplied_token is None or not hmac.compare_digest(
            claims.csrf_token,
            supplied_token,
        ):
            raise InvalidSessionError("Invalid CSRF token")
