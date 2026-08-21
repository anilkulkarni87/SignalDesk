from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from src.actions.schemas import ActionProposal

from .schemas import InvestigationView


class InvestigationNotFound(KeyError):
    pass


class InvestigationStore:
    """Minimal product state for reloading owned investigations and actions."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._connection:
            self._connection.executescript("""
                CREATE TABLE IF NOT EXISTS investigations (
                    investigation_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    customer_id TEXT NOT NULL,
                    view_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS investigation_actions (
                    action_id TEXT PRIMARY KEY,
                    investigation_id TEXT NOT NULL REFERENCES investigations(investigation_id),
                    user_id TEXT NOT NULL,
                    proposal_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)

    def close(self) -> None:
        self._connection.close()

    def save(self, user_id: str, view: InvestigationView) -> None:
        payload = view.model_dump_json()
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO investigations
                    (investigation_id, user_id, customer_id, view_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    view.investigation_id,
                    user_id,
                    view.customer_id,
                    payload,
                    view.created_at,
                ),
            )

    def get(self, user_id: str, investigation_id: str) -> InvestigationView:
        with self._lock:
            row = self._connection.execute(
                "SELECT view_json FROM investigations "
                "WHERE investigation_id = ? AND user_id = ?",
                (investigation_id, user_id),
            ).fetchone()
        if row is None:
            raise InvestigationNotFound(investigation_id)
        return InvestigationView.model_validate_json(row["view_json"])

    def link_action(
        self,
        user_id: str,
        investigation_id: str,
        proposal: ActionProposal,
    ) -> None:
        self.get(user_id, investigation_id)
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT OR IGNORE INTO investigation_actions
                    (action_id, investigation_id, user_id, proposal_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    proposal.action_id,
                    investigation_id,
                    user_id,
                    proposal.model_dump_json(),
                    datetime.now(UTC).isoformat(),
                ),
            )

    def get_action(
        self,
        user_id: str,
        action_id: str,
    ) -> tuple[str, ActionProposal]:
        with self._lock:
            row = self._connection.execute(
                "SELECT investigation_id, proposal_json FROM investigation_actions "
                "WHERE action_id = ? AND user_id = ?",
                (action_id, user_id),
            ).fetchone()
        if row is None:
            raise InvestigationNotFound(action_id)
        return (
            str(row["investigation_id"]),
            ActionProposal.model_validate_json(row["proposal_json"]),
        )
