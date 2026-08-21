from __future__ import annotations

from typing import Any


SEMANTIC_TIMEZONE = "America/Los_Angeles"


def configure_semantic_timezone(connection: Any) -> None:
    """Keep Customer 360 date calculations independent of the host timezone."""
    connection.execute("SET TimeZone = ?", [SEMANTIC_TIMEZONE])
