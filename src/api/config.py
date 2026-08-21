from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _secret_from_env(name: str) -> str:
    value = os.environ.get(name)
    file_value = os.environ.get(f"{name}_FILE")
    if value and file_value:
        raise ValueError(f"Set only one of {name} or {name}_FILE")
    if not file_value:
        return value or ""
    try:
        return Path(file_value).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ValueError(f"Unable to read {name}_FILE") from exc


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


@dataclass(frozen=True)
class APIConfig:
    database: Path = Path("data/warehouse/signaldesk.duckdb")
    corpus_dir: Path = Path("data/generated/knowledge")
    runtime_dir: Path = Path("data/runtime/commit17")
    access_code: str = field(default="", repr=False)
    session_secret: str = field(default="", repr=False)
    session_ttl_seconds: int = 8 * 60 * 60
    cookie_secure: bool = False
    llm_timeout_seconds: float = 45.0
    llm_max_attempts: int = 4
    max_model_rounds: int = 8
    max_tool_calls: int = 8
    investigation_rate_limit: int = 30
    login_rate_limit: int = 30
    rate_limit_window_seconds: int = 60
    idempotency_pending_ttl_seconds: int = 300
    allowed_origins: tuple[str, ...] = (
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    )

    def __post_init__(self) -> None:
        if len(self.access_code) < 8:
            raise ValueError(
                "SIGNALDESK_ACCESS_CODE must contain at least 8 characters"
            )
        if len(self.session_secret) < 32:
            raise ValueError(
                "SIGNALDESK_SESSION_SECRET must contain at least 32 characters"
            )
        if self.session_ttl_seconds < 300:
            raise ValueError("session_ttl_seconds must be at least 300")
        if not 1 <= self.llm_timeout_seconds <= 300:
            raise ValueError("llm_timeout_seconds must be between 1 and 300")
        if not 1 <= self.llm_max_attempts <= 5:
            raise ValueError("llm_max_attempts must be between 1 and 5")
        if not 1 <= self.max_model_rounds <= 16:
            raise ValueError("max_model_rounds must be between 1 and 16")
        if not 1 <= self.max_tool_calls <= 32:
            raise ValueError("max_tool_calls must be between 1 and 32")
        if self.investigation_rate_limit < 1 or self.login_rate_limit < 1:
            raise ValueError("rate limits must be positive")
        if self.rate_limit_window_seconds < 1:
            raise ValueError("rate_limit_window_seconds must be positive")
        if self.idempotency_pending_ttl_seconds < 30:
            raise ValueError("idempotency_pending_ttl_seconds must be at least 30")

    @classmethod
    def from_env(cls) -> "APIConfig":
        origins = os.environ.get(
            "SIGNALDESK_ALLOWED_ORIGINS",
            "http://127.0.0.1:3000,http://localhost:3000",
        )
        return cls(
            database=Path(
                os.environ.get(
                    "SIGNALDESK_DATABASE",
                    "data/warehouse/signaldesk.duckdb",
                )
            ),
            corpus_dir=Path(
                os.environ.get(
                    "SIGNALDESK_CORPUS_DIR",
                    "data/generated/knowledge",
                )
            ),
            runtime_dir=Path(
                os.environ.get(
                    "SIGNALDESK_RUNTIME_DIR",
                    "data/runtime/commit17",
                )
            ),
            access_code=_secret_from_env("SIGNALDESK_ACCESS_CODE"),
            session_secret=_secret_from_env("SIGNALDESK_SESSION_SECRET"),
            session_ttl_seconds=_env_int(
                "SIGNALDESK_SESSION_TTL_SECONDS",
                8 * 60 * 60,
            ),
            cookie_secure=os.environ.get(
                "SIGNALDESK_COOKIE_SECURE",
                "false",
            ).lower()
            == "true",
            llm_timeout_seconds=_env_float("SIGNALDESK_LLM_TIMEOUT_SECONDS", 45),
            llm_max_attempts=_env_int("SIGNALDESK_LLM_MAX_ATTEMPTS", 4),
            max_model_rounds=_env_int("SIGNALDESK_MAX_MODEL_ROUNDS", 8),
            max_tool_calls=_env_int("SIGNALDESK_MAX_TOOL_CALLS", 8),
            investigation_rate_limit=_env_int(
                "SIGNALDESK_INVESTIGATION_RATE_LIMIT",
                30,
            ),
            login_rate_limit=_env_int("SIGNALDESK_LOGIN_RATE_LIMIT", 30),
            rate_limit_window_seconds=_env_int(
                "SIGNALDESK_RATE_LIMIT_WINDOW_SECONDS",
                60,
            ),
            idempotency_pending_ttl_seconds=_env_int(
                "SIGNALDESK_IDEMPOTENCY_PENDING_TTL_SECONDS",
                300,
            ),
            allowed_origins=tuple(
                origin.strip() for origin in origins.split(",") if origin.strip()
            ),
        )
