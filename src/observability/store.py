from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from .schemas import (
    EvaluationResult,
    ObservabilitySummary,
    RunObservation,
    RunObservationList,
)


class ObservationNotFound(KeyError):
    pass


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def summarize(runs: list[RunObservation]) -> ObservabilitySummary:
    total = len(runs)
    successful = sum(run.status == "SUCCESS" for run in runs)
    task_successes = sum(run.task_success for run in runs)
    tool_calls = [call for run in runs for call in run.tool_calls]
    failed_tools = sum(not call.success for call in tool_calls)
    retrieval_calls = [
        call for call in tool_calls if call.tool_name == "search_knowledge_base"
    ]
    failed_retrievals = sum(
        not call.success or call.returned_count == 0 for call in retrieval_calls
    )
    evaluated = [run for run in runs if run.evaluation_result != "NOT_EVALUATED"]
    latencies = [run.latency_seconds for run in runs]
    return ObservabilitySummary(
        total_runs=total,
        successful_runs=successful,
        error_runs=total - successful,
        task_success_rate_pct=round(100 * task_successes / total, 2) if total else 0,
        latency_seconds={
            "p50": round(_percentile(latencies, 0.50), 4),
            "p95": round(_percentile(latencies, 0.95), 4),
        },
        tokens_per_task=(
            round(sum(run.tokens.total for run in runs) / total, 2) if total else 0
        ),
        cost_per_task_usd=(
            round(sum(run.cost_usd or 0 for run in runs) / total, 6) if total else 0
        ),
        tool_failure_rate_pct=(
            round(100 * failed_tools / len(tool_calls), 2) if tool_calls else 0
        ),
        retrieval_failure_rate_pct=(
            round(100 * failed_retrievals / len(retrieval_calls), 2)
            if retrieval_calls
            else 0
        ),
        evaluated_runs=len(evaluated),
        evaluation_pass_rate_pct=(
            round(
                100
                * sum(run.evaluation_result == "PASS" for run in evaluated)
                / len(evaluated),
                2,
            )
            if evaluated
            else None
        ),
    )


class ObservabilityStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._connection:
            self._connection.executescript("""
                CREATE TABLE IF NOT EXISTS run_observations (
                    request_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    observation_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_run_observations_user_created
                    ON run_observations(user_id, created_at DESC);
            """)

    def close(self) -> None:
        self._connection.close()

    def ping(self) -> None:
        with self._lock:
            self._connection.execute("SELECT 1").fetchone()

    def record(self, observation: RunObservation) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO run_observations
                    (request_id, user_id, status, created_at, observation_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    observation.request_id,
                    observation.user_id,
                    observation.status,
                    observation.started_at,
                    observation.model_dump_json(),
                ),
            )

    def get(self, user_id: str, request_id: str) -> RunObservation:
        with self._lock:
            row = self._connection.execute(
                "SELECT observation_json FROM run_observations "
                "WHERE request_id = ? AND user_id = ?",
                (request_id, user_id),
            ).fetchone()
        if row is None:
            raise ObservationNotFound(request_id)
        return RunObservation.model_validate_json(row["observation_json"])

    def list_for_user(self, user_id: str, limit: int = 100) -> RunObservationList:
        with self._lock:
            rows = self._connection.execute(
                "SELECT observation_json FROM run_observations "
                "WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return RunObservationList(
            runs=[
                RunObservation.model_validate_json(row["observation_json"])
                for row in rows
            ]
        )

    def summary_for_user(self, user_id: str) -> ObservabilitySummary:
        return summarize(self.list_for_user(user_id, limit=1000).runs)

    def update_evaluation(
        self,
        user_id: str,
        request_id: str,
        result: EvaluationResult,
        note: str,
    ) -> RunObservation:
        values = self.get(user_id, request_id).model_dump(mode="json")
        values.update(evaluation_result=result, evaluation_note=note)
        observation = RunObservation.model_validate(values)
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "UPDATE run_observations SET observation_json = ? "
                "WHERE request_id = ? AND user_id = ?",
                (observation.model_dump_json(), request_id, user_id),
            )
        if cursor.rowcount != 1:
            raise ObservationNotFound(request_id)
        return observation
