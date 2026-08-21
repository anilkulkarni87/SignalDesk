from __future__ import annotations

import sqlite3
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal


class IdempotencyConflict(RuntimeError):
    pass


class IdempotencyInProgress(RuntimeError):
    pass


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int


class SlidingWindowRateLimiter:
    def __init__(
        self,
        limit: int,
        window_seconds: int,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if limit < 1 or window_seconds < 1:
            raise ValueError("rate-limit values must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> RateLimitDecision:
        now = self._clock()
        cutoff = now - self.window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                retry_after = max(1, int(events[0] + self.window_seconds - now) + 1)
                return RateLimitDecision(False, retry_after)
            events.append(now)
        return RateLimitDecision(True, 0)


IdempotencyAction = Literal["PROCEED", "REPLAY"]


@dataclass(frozen=True)
class IdempotencyReservation:
    action: IdempotencyAction
    investigation_id: str | None = None


class IdempotencyStore:
    def __init__(
        self,
        path: str | Path,
        *,
        pending_ttl_seconds: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._clock = clock
        self._pending_ttl_seconds = pending_ttl_seconds
        with self._connection:
            self._connection.executescript("""
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    user_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    request_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN ('PENDING', 'COMPLETED', 'FAILED')
                    ),
                    request_id TEXT NOT NULL,
                    investigation_id TEXT,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (user_id, idempotency_key)
                );
            """)

    def close(self) -> None:
        self._connection.close()

    def ping(self) -> None:
        with self._lock:
            self._connection.execute("SELECT 1").fetchone()

    def begin(
        self,
        user_id: str,
        idempotency_key: str,
        request_sha256: str,
        request_id: str,
    ) -> IdempotencyReservation:
        now = self._clock()
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT request_sha256, status, investigation_id, updated_at "
                "FROM idempotency_keys WHERE user_id = ? AND idempotency_key = ?",
                (user_id, idempotency_key),
            ).fetchone()
            if row is None:
                self._insert_pending(
                    user_id,
                    idempotency_key,
                    request_sha256,
                    request_id,
                    now,
                )
                return IdempotencyReservation("PROCEED")
            if row["request_sha256"] != request_sha256:
                raise IdempotencyConflict(
                    "Idempotency key already belongs to a different request"
                )
            if row["status"] == "COMPLETED":
                return IdempotencyReservation(
                    "REPLAY",
                    str(row["investigation_id"]),
                )
            is_stale = now - float(row["updated_at"]) >= self._pending_ttl_seconds
            if row["status"] == "PENDING" and not is_stale:
                raise IdempotencyInProgress(
                    "Request with this key is still in progress"
                )
            self._connection.execute(
                "UPDATE idempotency_keys SET status = 'PENDING', request_id = ?, "
                "investigation_id = NULL, updated_at = ? "
                "WHERE user_id = ? AND idempotency_key = ?",
                (request_id, now, user_id, idempotency_key),
            )
            return IdempotencyReservation("PROCEED")

    def _insert_pending(
        self,
        user_id: str,
        idempotency_key: str,
        request_sha256: str,
        request_id: str,
        now: float,
    ) -> None:
        self._connection.execute(
            "INSERT INTO idempotency_keys "
            "(user_id, idempotency_key, request_sha256, status, request_id, "
            "investigation_id, updated_at) VALUES (?, ?, ?, 'PENDING', ?, NULL, ?)",
            (user_id, idempotency_key, request_sha256, request_id, now),
        )

    def complete(
        self,
        user_id: str,
        idempotency_key: str,
        investigation_id: str,
    ) -> None:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "UPDATE idempotency_keys SET status = 'COMPLETED', "
                "investigation_id = ?, updated_at = ? "
                "WHERE user_id = ? AND idempotency_key = ? AND status = 'PENDING'",
                (investigation_id, self._clock(), user_id, idempotency_key),
            )
        if cursor.rowcount != 1:
            raise IdempotencyConflict("Idempotency reservation was not pending")

    def fail(self, user_id: str, idempotency_key: str) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE idempotency_keys SET status = 'FAILED', updated_at = ? "
                "WHERE user_id = ? AND idempotency_key = ? AND status = 'PENDING'",
                (self._clock(), user_id, idempotency_key),
            )
