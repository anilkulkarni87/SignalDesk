from __future__ import annotations

import json
import math
import os
import re
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from .chunking import KnowledgeChunk


DEFAULT_PG_DSN = "postgresql://signaldesk:signaldesk@localhost:5432/signaldesk"
SQL_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


@dataclass(frozen=True)
class VectorSearchResult:
    chunk_id: str
    document_id: str
    title: str
    family: str
    document_type: str
    status: str
    authority: str
    topic: str
    score: float
    content: str
    source_path: str

    def to_dict(self) -> dict:
        return asdict(self)


def resolve_dsn(value: str | None = None) -> str:
    return value or os.getenv("SIGNALDESK_PG_DSN", DEFAULT_PG_DSN)


def vector_literal(vector: Iterable[float]) -> str:
    values = [float(value) for value in vector]
    if not values:
        raise ValueError("Vector must not be empty")
    if any(not math.isfinite(value) for value in values):
        raise ValueError("Vector values must be finite")
    return "[" + ",".join(format(value, ".9g") for value in values) + "]"


def validate_sql_identifier(value: str) -> str:
    if not SQL_IDENTIFIER_RE.fullmatch(value):
        raise ValueError(
            "SQL identifiers must start with a lowercase letter, contain only "
            "lowercase letters, numbers, and underscores, and be at most 63 characters"
        )
    return value


class PgVectorStore:
    def __init__(
        self,
        dsn: str | None = None,
        *,
        table_name: str = "knowledge_chunks",
        metadata_table_name: str | None = None,
    ) -> None:
        self.dsn = resolve_dsn(dsn)
        self.table_name = validate_sql_identifier(table_name)
        if metadata_table_name is None:
            metadata_table_name = (
                "knowledge_index_metadata"
                if table_name == "knowledge_chunks"
                else f"{table_name}_metadata"
            )
        self.metadata_table_name = validate_sql_identifier(metadata_table_name)

    @staticmethod
    def _connect(dsn: str):
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "Install psycopg from requirements-commit06.txt"
            ) from exc
        return psycopg.connect(dsn)

    def ensure_schema(self, dimension: int, *, recreate: bool = False) -> None:
        if dimension <= 0 or dimension > 2000:
            raise ValueError("pgvector vector dimensions must be between 1 and 2000")

        with self._connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
                if recreate:
                    cursor.execute(f"DROP TABLE IF EXISTS {self.table_name}")
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.table_name} (
                        chunk_id TEXT PRIMARY KEY,
                        document_id TEXT NOT NULL,
                        title TEXT NOT NULL,
                        family TEXT NOT NULL,
                        document_type TEXT NOT NULL,
                        status TEXT NOT NULL,
                        authority TEXT NOT NULL,
                        topic TEXT NOT NULL,
                        position INTEGER NOT NULL,
                        content TEXT NOT NULL,
                        source_path TEXT NOT NULL,
                        metadata JSONB NOT NULL,
                        embedding vector({dimension}) NOT NULL
                    )
                """)
                cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.metadata_table_name} (
                        key TEXT PRIMARY KEY,
                        value JSONB NOT NULL
                    )
                """)
                cursor.execute(f"""
                    CREATE INDEX IF NOT EXISTS {self.table_name}_filter_idx
                    ON {self.table_name} (status, authority, family)
                """)

    def check_connection(self) -> None:
        with self._connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                if cursor.fetchone() != (1,):
                    raise RuntimeError("PostgreSQL connection check failed")

    def upsert_chunks(
        self,
        rows: Iterable[tuple[KnowledgeChunk, list[float]]],
        *,
        batch_size: int = 200,
    ) -> int:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")

        sql = f"""
            INSERT INTO {self.table_name} (
                chunk_id, document_id, title, family, document_type,
                status, authority, topic, position, content, source_path,
                metadata, embedding
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s::jsonb, %s::vector
            )
            ON CONFLICT (chunk_id) DO UPDATE SET
                document_id = EXCLUDED.document_id,
                title = EXCLUDED.title,
                family = EXCLUDED.family,
                document_type = EXCLUDED.document_type,
                status = EXCLUDED.status,
                authority = EXCLUDED.authority,
                topic = EXCLUDED.topic,
                position = EXCLUDED.position,
                content = EXCLUDED.content,
                source_path = EXCLUDED.source_path,
                metadata = EXCLUDED.metadata,
                embedding = EXCLUDED.embedding
        """

        pending = []
        inserted = 0
        with self._connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                for chunk, vector in rows:
                    pending.append((
                        chunk.chunk_id,
                        chunk.document_id,
                        chunk.title,
                        chunk.family,
                        chunk.document_type,
                        chunk.status,
                        chunk.authority,
                        chunk.topic,
                        chunk.position,
                        chunk.content,
                        chunk.source_path,
                        json.dumps(chunk.to_dict()),
                        vector_literal(vector),
                    ))
                    if len(pending) >= batch_size:
                        cursor.executemany(sql, pending)
                        inserted += len(pending)
                        pending = []
                if pending:
                    cursor.executemany(sql, pending)
                    inserted += len(pending)
        return inserted

    def create_hnsw_index(self) -> None:
        with self._connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"""
                    CREATE INDEX IF NOT EXISTS {self.table_name}_embedding_hnsw_idx
                    ON {self.table_name} USING hnsw (embedding vector_cosine_ops)
                """)

    def set_metadata(self, metadata: dict[str, Any]) -> None:
        sql = f"""
            INSERT INTO {self.metadata_table_name} (key, value)
            VALUES (%s, %s::jsonb)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """
        with self._connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    sql,
                    [(key, json.dumps(value)) for key, value in metadata.items()],
                )

    def get_metadata(self) -> dict[str, Any]:
        with self._connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regclass(%s)", (self.metadata_table_name,))
                if cursor.fetchone()[0] is None:
                    return {}
                cursor.execute(
                    f"SELECT key, value FROM {self.metadata_table_name}"
                )
                return {key: value for key, value in cursor.fetchall()}

    def search(
        self,
        query_vector: list[float],
        *,
        top_k: int = 5,
        statuses: set[str] | None = None,
        authorities: set[str] | None = None,
        families: set[str] | None = None,
    ) -> list[VectorSearchResult]:
        if top_k <= 0:
            raise ValueError("top_k must be positive")

        query_literal = vector_literal(query_vector)
        where = []
        filter_params: list[Any] = []
        if statuses:
            where.append("status = ANY(%s)")
            filter_params.append(sorted(statuses))
        if authorities:
            where.append("authority = ANY(%s)")
            filter_params.append(sorted(authorities))
        if families:
            where.append("family = ANY(%s)")
            filter_params.append(sorted(families))

        filter_sql = " WHERE " + " AND ".join(where) if where else ""
        candidate_limit = max(top_k * 10, 50)
        params = [
            query_literal,
            *filter_params,
            query_literal,
            candidate_limit,
            top_k,
        ]
        sql = f"""
            WITH candidates AS (
                SELECT
                    chunk_id, document_id, title, family, document_type,
                    status, authority, topic, content, source_path,
                    embedding <=> %s::vector AS distance
                FROM {self.table_name}
                {filter_sql}
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            ), document_best AS (
                SELECT DISTINCT ON (document_id)
                    chunk_id, document_id, title, family, document_type,
                    status, authority, topic, content, source_path, distance
                FROM candidates
                ORDER BY document_id, distance
            )
            SELECT
                chunk_id, document_id, title, family, document_type,
                status, authority, topic, content, source_path, distance
            FROM document_best
            ORDER BY distance, document_id
            LIMIT %s
        """
        with self._connect(self.dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL hnsw.iterative_scan = strict_order")
                cursor.execute(sql, params)
                rows = cursor.fetchall()

        return [
            VectorSearchResult(
                chunk_id=row[0],
                document_id=row[1],
                title=row[2],
                family=row[3],
                document_type=row[4],
                status=row[5],
                authority=row[6],
                topic=row[7],
                content=row[8],
                source_path=row[9],
                score=round(1.0 - float(row[10]), 6),
            )
            for row in rows
        ]
