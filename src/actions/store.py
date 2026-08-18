from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .schemas import ActionProposal, ApprovalDecision


class ActionStoreConflict(RuntimeError):
    pass


def canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class ActionStore:
    """SQLite ledger for approval decisions and synthetic CDP action events."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self._setup()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "ActionStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _setup(self) -> None:
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS action_proposals (
                action_id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                proposal_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS action_decisions (
                action_id TEXT PRIMARY KEY REFERENCES action_proposals(action_id),
                decision TEXT NOT NULL CHECK (decision IN ('APPROVED', 'REJECTED')),
                reviewer_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                decided_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS action_audit (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_id TEXT NOT NULL REFERENCES action_proposals(action_id),
                event_type TEXT NOT NULL,
                details_json TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                UNIQUE (action_id, event_type)
            );
            CREATE TABLE IF NOT EXISTS synthetic_cdp_events (
                event_id TEXT PRIMARY KEY,
                action_id TEXT NOT NULL UNIQUE REFERENCES action_proposals(action_id),
                customer_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                event_payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)
        self.connection.commit()

    def record_proposal(self, proposal: ActionProposal) -> None:
        payload = proposal.model_dump(mode="json")
        proposal_json = canonical_json(payload)
        payload_hash = hashlib.sha256(proposal_json.encode()).hexdigest()
        with self.connection:
            existing = self.connection.execute(
                "SELECT proposal_json FROM action_proposals WHERE action_id = ?",
                (proposal.action_id,),
            ).fetchone()
            if existing and existing["proposal_json"] != proposal_json:
                raise ActionStoreConflict(
                    f"Action {proposal.action_id} already has a different payload"
                )
            self.connection.execute(
                """
                INSERT OR IGNORE INTO action_proposals
                    (action_id, customer_id, action_type, payload_sha256,
                     proposal_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal.action_id,
                    proposal.customer_id,
                    proposal.action.action_type,
                    payload_hash,
                    proposal_json,
                    utc_now(),
                ),
            )
            self._audit(
                proposal.action_id,
                "PROPOSED",
                {"proposal_sha256": payload_hash},
            )

    def record_approval_request(self, proposal: ActionProposal) -> None:
        with self.connection:
            self._require_exact_proposal(proposal)
            self._audit(
                proposal.action_id,
                "APPROVAL_REQUESTED",
                {"action_type": proposal.action.action_type},
            )

    def record_decision(
        self,
        proposal: ActionProposal,
        decision: ApprovalDecision,
    ) -> None:
        if decision.action_id != proposal.action_id:
            raise ActionStoreConflict("decision action_id does not match proposal")
        decision_json = decision.model_dump(mode="json")
        with self.connection:
            self._require_exact_proposal(proposal)
            existing = self.connection.execute(
                "SELECT decision, reviewer_id, reason FROM action_decisions "
                "WHERE action_id = ?",
                (proposal.action_id,),
            ).fetchone()
            expected = (
                decision.decision,
                decision.reviewer_id,
                decision.reason,
            )
            if existing and tuple(existing) != expected:
                raise ActionStoreConflict(
                    f"Action {proposal.action_id} already has a different decision"
                )
            self.connection.execute(
                """
                INSERT OR IGNORE INTO action_decisions
                    (action_id, decision, reviewer_id, reason, decided_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (*((proposal.action_id,) + expected), utc_now()),
            )
            self._audit(proposal.action_id, decision.decision, decision_json)

    def execute_approved(self, proposal: ActionProposal) -> tuple[str, bool]:
        event_id = f"EVT-{proposal.action_id.removeprefix('ACT-')}"
        with self.connection:
            self._require_exact_proposal(proposal)
            decision = self.connection.execute(
                "SELECT decision FROM action_decisions WHERE action_id = ?",
                (proposal.action_id,),
            ).fetchone()
            if not decision or decision["decision"] != "APPROVED":
                raise ActionStoreConflict(
                    f"Action {proposal.action_id} has not been approved"
                )
            cursor = self.connection.execute(
                """
                INSERT OR IGNORE INTO synthetic_cdp_events
                    (event_id, action_id, customer_id, action_type,
                     event_payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    proposal.action_id,
                    proposal.customer_id,
                    proposal.action.action_type,
                    canonical_json(proposal.action.model_dump(mode="json")),
                    utc_now(),
                ),
            )
            created = cursor.rowcount == 1
            self._audit(
                proposal.action_id,
                "EXECUTED",
                {"event_id": event_id},
            )
        return event_id, created

    def audit_events(self, action_id: str) -> list[str]:
        rows = self.connection.execute(
            "SELECT event_type FROM action_audit WHERE action_id = ? "
            "ORDER BY audit_id",
            (action_id,),
        ).fetchall()
        return [row["event_type"] for row in rows]

    def event_count(self, action_id: str | None = None) -> int:
        if action_id is None:
            row = self.connection.execute(
                "SELECT COUNT(*) AS count FROM synthetic_cdp_events"
            ).fetchone()
        else:
            row = self.connection.execute(
                "SELECT COUNT(*) AS count FROM synthetic_cdp_events "
                "WHERE action_id = ?",
                (action_id,),
            ).fetchone()
        return int(row["count"])

    def decision_for(self, action_id: str) -> str | None:
        row = self.connection.execute(
            "SELECT decision FROM action_decisions WHERE action_id = ?",
            (action_id,),
        ).fetchone()
        return None if row is None else str(row["decision"])

    def _require_exact_proposal(self, proposal: ActionProposal) -> None:
        expected = canonical_json(proposal.model_dump(mode="json"))
        row = self.connection.execute(
            "SELECT proposal_json FROM action_proposals WHERE action_id = ?",
            (proposal.action_id,),
        ).fetchone()
        if row is None:
            raise ActionStoreConflict(f"Unknown action {proposal.action_id}")
        if row["proposal_json"] != expected:
            raise ActionStoreConflict(
                f"Stored payload for {proposal.action_id} does not match"
            )

    def _audit(
        self,
        action_id: str,
        event_type: str,
        details: dict[str, Any],
    ) -> None:
        self.connection.execute(
            """
            INSERT OR IGNORE INTO action_audit
                (action_id, event_type, details_json, recorded_at)
            VALUES (?, ?, ?, ?)
            """,
            (action_id, event_type, canonical_json(details), utc_now()),
        )
