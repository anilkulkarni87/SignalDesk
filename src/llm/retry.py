from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def with_exponential_backoff(
    operation: Callable[[], T],
    *,
    retryable_exceptions: tuple[type[BaseException], ...],
    max_attempts: int = 4,
    base_delay_seconds: float = 0.5,
    max_delay_seconds: float = 8.0,
) -> tuple[T, int]:
    """Execute operation with bounded exponential backoff + jitter.

    Returns:
        (result, attempts_used)

    The OpenAI client is configured with max_retries=0 in client.py so retry
    behavior remains visible and measurable in this learning commit.
    """

    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    for attempt in range(1, max_attempts + 1):
        try:
            return operation(), attempt
        except retryable_exceptions:
            if attempt == max_attempts:
                raise

            delay = min(
                max_delay_seconds,
                base_delay_seconds * (2 ** (attempt - 1)),
            )
            delay *= random.uniform(0.75, 1.25)
            time.sleep(delay)

    raise AssertionError("unreachable")
