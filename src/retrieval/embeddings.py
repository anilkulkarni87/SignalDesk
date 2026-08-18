from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


@dataclass(frozen=True)
class EmbeddingRun:
    vectors: list[list[float]]
    model: str
    dimensions: int
    input_count: int
    input_tokens: int


class OpenAIEmbedder:
    def __init__(
        self,
        *,
        model: str = DEFAULT_EMBEDDING_MODEL,
        dimensions: int | None = None,
        batch_size: int = 64,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self.model = model
        self.dimensions = dimensions
        self.batch_size = batch_size

    def embed(self, texts: Sequence[str]) -> EmbeddingRun:
        if not texts:
            raise ValueError("At least one text is required")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "Install the OpenAI SDK from requirements-commit06.txt"
            ) from exc

        client = OpenAI()
        vectors: list[list[float]] = []
        input_tokens = 0

        for start in range(0, len(texts), self.batch_size):
            batch = list(texts[start:start + self.batch_size])
            request = {"model": self.model, "input": batch}
            if self.dimensions is not None:
                request["dimensions"] = self.dimensions
            response = client.embeddings.create(**request)
            vectors.extend(item.embedding for item in response.data)
            if response.usage is not None:
                input_tokens += int(response.usage.prompt_tokens)

        if len(vectors) != len(texts):
            raise RuntimeError(
                f"Expected {len(texts)} embeddings, received {len(vectors)}"
            )
        dimension = len(vectors[0])
        if any(len(vector) != dimension for vector in vectors):
            raise RuntimeError("Embedding response contained mixed dimensions")

        return EmbeddingRun(
            vectors=vectors,
            model=self.model,
            dimensions=dimension,
            input_count=len(texts),
            input_tokens=input_tokens,
        )
