"""Reranker service using BAAI/bge-reranker-v2-m3 via SiliconFlow Rerank API."""

import logging
from typing import List

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)


class RerankerService:
    """Rerank candidate documents via SiliconFlow's rerank API."""

    def rerank(
        self,
        query: str,
        candidates: List[dict],
        top_k: int = 3,
    ) -> List[dict]:
        """
        Rerank candidate items by relevance to the query using SiliconFlow API.

        Candidates must include a ``text`` field. The returned dictionaries are
        the original candidates with their ``score`` replaced by rerank scores.
        """
        if not candidates:
            return []

        payload = {
            "model": settings.reranker_model_name,
            "query": query,
            "documents": [candidate["text"] for candidate in candidates],
            "top_n": top_k,
            "return_documents": True,
        }
        headers = {
            "Authorization": f"Bearer {settings.reranker_api_key or settings.siliconflow_api_key}",
            "Content-Type": "application/json",
        }

        try:
            rerank_url = f"{settings.siliconflow_base_url.rstrip('/')}/rerank"
            resp = requests.post(
                rerank_url,
                headers=headers,
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error("Rerank API call failed: %s", e)
            return candidates[:top_k]

        score_map = {
            result.get("index"): result.get("relevance_score", 0.0)
            for result in data.get("results", [])
        }

        reranked = []
        for index, candidate in enumerate(candidates):
            updated = dict(candidate)
            updated["score"] = score_map.get(index, 0.0)
            reranked.append(updated)

        reranked.sort(key=lambda item: item["score"], reverse=True)
        return reranked[:top_k]

    @property
    def is_loaded(self) -> bool:
        """Reranker is served via SiliconFlow API, so no local model is loaded."""
        return True
