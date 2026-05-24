"""Qdrant-backed semantic context store for NL2SQL retrieval."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ContextItem:
    """One semantic context item to be indexed in Qdrant."""

    id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


class QdrantContextStore:
    """Small wrapper around Qdrant's vector + JSON payload point model."""

    def __init__(
        self,
        url: str | None = None,
        collection_name: str | None = None,
    ) -> None:
        try:
            from qdrant_client import QdrantClient
        except ImportError as exc:
            raise RuntimeError(
                "qdrant-client is not installed. Install it with `pip install qdrant-client`."
            ) from exc

        self.url = url or settings.qdrant_url
        self.collection_name = collection_name or settings.qdrant_collection
        self.client = QdrantClient(url=self.url)

    def ping(self) -> bool:
        """Return True when Qdrant is reachable."""
        self.client.get_collections()
        return True

    def collection_exists(self) -> bool:
        """Return True if the configured collection exists."""
        try:
            return self.client.collection_exists(self.collection_name)
        except AttributeError:
            collections = self.client.get_collections().collections
            return any(item.name == self.collection_name for item in collections)

    def ensure_collection(self, vector_size: int, recreate: bool = False) -> None:
        """Create the collection if missing, optionally deleting it first."""
        from qdrant_client import models

        if recreate and self.collection_exists():
            self.client.delete_collection(self.collection_name)

        if self.collection_exists():
            return

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=models.VectorParams(
                size=vector_size,
                distance=models.Distance.COSINE,
            ),
        )

    def upsert_contexts(self, items: list[ContextItem | dict[str, Any]]) -> int:
        """Upsert context items. Each item must include a vector in metadata."""
        from qdrant_client import models

        points = []
        for item in items:
            context_item = self._coerce_item(item)
            metadata = dict(context_item.metadata)
            vector = metadata.pop("vector", None)
            if not vector:
                raise ValueError(f"Context item {context_item.id} is missing metadata.vector")
            payload = self._payload(ContextItem(context_item.id, context_item.content, metadata))
            points.append(
                models.PointStruct(
                    id=self._point_id(context_item.id),
                    vector=vector,
                    payload=payload,
                )
            )

        if not points:
            return 0

        self.client.upsert(collection_name=self.collection_name, points=points)
        return len(points)

    def search(
        self,
        query_vector: list[float],
        top_k: int,
        filters: dict[str, Any] | None = None,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """Search Qdrant with optional payload filters."""
        query_filter = self._build_filter(filters or {})
        threshold = settings.qdrant_score_threshold if score_threshold is None else score_threshold

        try:
            hits = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=query_filter,
                limit=top_k,
                score_threshold=threshold,
                with_payload=True,
            )
        except AttributeError:
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=query_filter,
                limit=top_k,
                score_threshold=threshold,
                with_payload=True,
            )
            hits = response.points

        results = []
        for hit in hits:
            payload = dict(hit.payload or {})
            results.append(
                {
                    "id": str(payload.get("source_id") or hit.id),
                    "score": float(hit.score),
                    "payload": payload,
                    "text": payload.get("content", ""),
                }
            )
        return results

    def _payload(self, item: ContextItem) -> dict[str, Any]:
        payload = {
            "type": "unknown",
            "domain": "common",
            "difficulty": "unknown",
            "table_names": [],
            "intent_tags": [],
            "approved": False,
            "source_id": item.id,
            "question": "",
            "sql": "",
            "content": item.content,
        }
        payload.update(item.metadata)
        payload["source_id"] = str(payload.get("source_id") or item.id)
        payload["content"] = item.content
        payload["table_names"] = list(payload.get("table_names") or [])
        payload["intent_tags"] = list(payload.get("intent_tags") or [])
        return payload

    def _build_filter(self, filters: dict[str, Any]):
        if not filters:
            return None

        from qdrant_client import models

        conditions = []
        for key, value in filters.items():
            if value is None or value == []:
                continue
            if isinstance(value, (list, tuple, set)):
                conditions.append(
                    models.FieldCondition(
                        key=key,
                        match=models.MatchAny(any=list(value)),
                    )
                )
            else:
                conditions.append(
                    models.FieldCondition(
                        key=key,
                        match=models.MatchValue(value=value),
                    )
                )

        if not conditions:
            return None
        return models.Filter(must=conditions)

    def _coerce_item(self, item: ContextItem | dict[str, Any]) -> ContextItem:
        if isinstance(item, ContextItem):
            return item
        return ContextItem(
            id=str(item["id"]),
            content=str(item["content"]),
            metadata=dict(item.get("metadata") or {}),
        )

    def _point_id(self, value: str) -> str:
        """Produce a stable UUID-like point id from an arbitrary source id."""
        digest = hashlib.md5(value.encode("utf-8")).hexdigest()
        return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"
