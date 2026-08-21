from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class APIConfig:
    database: Path = Path("data/warehouse/signaldesk.duckdb")
    corpus_dir: Path = Path("data/generated/knowledge")
    runtime_dir: Path = Path("data/runtime/commit16")
    access_code: str = field(default="", repr=False)
    session_secret: str = field(default="", repr=False)
    session_ttl_seconds: int = 8 * 60 * 60
    cookie_secure: bool = False
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
                    "data/runtime/commit16",
                )
            ),
            access_code=os.environ.get("SIGNALDESK_ACCESS_CODE", ""),
            session_secret=os.environ.get("SIGNALDESK_SESSION_SECRET", ""),
            cookie_secure=os.environ.get(
                "SIGNALDESK_COOKIE_SECURE",
                "false",
            ).lower()
            == "true",
            allowed_origins=tuple(
                origin.strip() for origin in origins.split(",") if origin.strip()
            ),
        )
