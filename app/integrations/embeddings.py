from __future__ import annotations

import hashlib
import math
from typing import Protocol

from app.config import Settings, get_settings


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class HashingEmbedder:
    """Local deterministic embeddings for demo/offline retrieval."""

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(text) for text in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = text.lower().replace("/", " ").replace("_", " ").split()
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class OpenAICompatibleEmbedder:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx

        key = self.settings.openai_compat_api_key.get_secret_value()
        if not self.settings.openai_compat_base_url or not key:
            raise RuntimeError("openai_compatible embeddings are not configured")
        url = self.settings.openai_compat_base_url.rstrip("/") + "/embeddings"
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {key}"},
            json={"model": self.settings.openai_compat_embedding_model, "input": texts},
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()["data"]
        return [item["embedding"] for item in sorted(data, key=lambda x: x["index"])]


def build_embedder(settings: Settings | None = None) -> Embedder:
    settings = settings or get_settings()
    if settings.embedding_provider == "openai_compatible":
        return OpenAICompatibleEmbedder(settings)
    return HashingEmbedder(settings.embedding_dim)
