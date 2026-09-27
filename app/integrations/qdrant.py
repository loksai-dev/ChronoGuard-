from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.config import Settings, get_settings
from app.integrations.embeddings import Embedder, build_embedder
from app.observability.logging import get_logger
from app.observability.metrics import QDRANT_LATENCY

logger = get_logger(__name__)


class QdrantUnavailable(RuntimeError):
    pass


class QdrantStore:
    def __init__(self, settings: Settings | None = None, embedder: Embedder | None = None) -> None:
        self.settings = settings or get_settings()
        self.embedder = embedder or build_embedder(self.settings)
        self.client = QdrantClient(url=self.settings.qdrant_url, timeout=10.0)
        self.collection = self.settings.qdrant_collection

    def ping(self) -> bool:
        try:
            self.client.get_collections()
            return True
        except Exception:
            return False

    def ensure_collection(self) -> None:
        try:
            existing = {c.name for c in self.client.get_collections().collections}
            if self.collection not in existing:
                self.client.create_collection(
                    collection_name=self.collection,
                    vectors_config=VectorParams(
                        size=self.settings.embedding_dim,
                        distance=Distance.COSINE,
                    ),
                )
        except Exception as exc:
            raise QdrantUnavailable(str(exc)) from exc

    def upsert(self, documents: list[dict[str, Any]]) -> None:
        self.ensure_collection()
        vectors = self.embedder.embed([doc["text"] for doc in documents])
        points = [
            PointStruct(
                id=doc.get("id") or str(uuid4()),
                vector=vector,
                payload={k: v for k, v in doc.items() if k != "vector"},
            )
            for doc, vector in zip(documents, vectors)
        ]
        self.client.upsert(collection_name=self.collection, points=points)

    def search(self, query: str, limit: int = 5, kind: str | None = None) -> list[dict[str, Any]]:
        started = time.perf_counter()
        try:
            self.ensure_collection()
            vector = self.embedder.embed([query])[0]
            try:
                results = self.client.query_points(
                    collection_name=self.collection,
                    query=vector,
                    limit=limit * 3 if kind else limit,
                    with_payload=True,
                )
                points = getattr(results, "points", results)
            except Exception:
                points = self.client.search(
                    collection_name=self.collection,
                    query_vector=vector,
                    limit=limit * 3 if kind else limit,
                    with_payload=True,
                )
        except (UnexpectedResponse, OSError, Exception) as exc:
            raise QdrantUnavailable(str(exc)) from exc
        finally:
            QDRANT_LATENCY.observe(time.perf_counter() - started)

        hits = []
        for point in points:
            payload = dict(getattr(point, "payload", {}) or {})
            if kind and payload.get("kind") != kind:
                continue
            hits.append(
                {
                    "id": str(getattr(point, "id", "")),
                    "score": float(getattr(point, "score", 0.0)),
                    "payload": payload,
                }
            )
        return hits[:limit]
