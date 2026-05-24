"""Embedding service using BAAI/bge-m3 via SiliconFlow Embedding API."""

import numpy as np
from typing import List
from openai import OpenAI
from app.core.config import settings


class EmbeddingService:
    """Generate embeddings using BAAI/bge-m3 via SiliconFlow's OpenAI-compatible API."""

    def __init__(self):
        self.client = OpenAI(
            api_key=settings.embedding_api_key or settings.siliconflow_api_key,
            base_url=settings.siliconflow_base_url,
        )
        self.model = settings.embedding_model_name

    def embed_query(self, text: str) -> List[float]:
        """
        Embed a single query text.

        Args:
            text: The text to embed.

        Returns:
            A list of floats representing the embedding vector.
        """
        return self._embed(text)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Embed multiple documents/texts.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors.
        """
        # Batch single call if possible, otherwise fallback to one-by-one
        try:
            resp = self.client.embeddings.create(
                model=self.model,
                input=texts,
            )
            # Sort by index to preserve order
            sorted_data = sorted(resp.data, key=lambda x: x.index)
            return [item.embedding for item in sorted_data]
        except Exception:
                return [self._embed(t) for t in texts]
    def _embed(self, text: str) -> List[float]:
        """Call SiliconFlow Embedding API for a single text."""
        resp = self.client.embeddings.create(
            model=self.model,
            input=text,
        )
        return resp.data[0].embedding

    def cosine_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        a = np.array(vec_a, dtype=np.float32)
        b = np.array(vec_b, dtype=np.float32)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))
