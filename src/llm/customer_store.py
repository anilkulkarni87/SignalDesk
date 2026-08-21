from __future__ import annotations

from pathlib import Path
from typing import Any

from src.warehouse import configure_semantic_timezone

from .schemas import LLM_FEATURES


class CustomerStore:
    def __init__(self, database: str | Path):
        try:
            import duckdb
        except ImportError as exc:
            raise RuntimeError("Install DuckDB: pip install duckdb") from exc

        self._con = duckdb.connect(str(database), read_only=True)
        configure_semantic_timezone(self._con)

    def get_snapshot(self, customer_id: str) -> dict[str, Any]:
        columns = ", ".join(LLM_FEATURES)
        row = self._con.execute(
            f"SELECT {columns} FROM customer_360 WHERE customer_id = ?",
            [customer_id],
        ).fetchone()

        if row is None:
            raise KeyError(f"Unknown customer_id: {customer_id}")

        description = self._con.description
        names = [col[0] for col in description]
        snapshot = dict(zip(names, row))

        # JSON-safe conversion without teaching the LLM DuckDB/Python types.
        for key, value in list(snapshot.items()):
            if value is None or isinstance(value, (str, int, float, bool)):
                continue
            snapshot[key] = str(value)

        return snapshot
