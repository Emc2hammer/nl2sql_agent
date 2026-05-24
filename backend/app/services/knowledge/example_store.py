"""Few-shot example store with difficulty-aware retrieval."""

import json
import logging
from pathlib import Path
from typing import Optional, List

from app.core.config import settings
from app.services.knowledge.knowledge_base import lexical_score

logger = logging.getLogger(__name__)


class ExampleStore:
    """
    Stores NL2SQL example pairs and retrieves the most relevant ones
    for a given question using embedding similarity + reranking.
    """

    def __init__(self, embedding_service=None, reranker_service=None):
        self.embedding_service = embedding_service
        self.reranker_service = reranker_service
        self.examples: List[dict] = []
        self.embeddings: List[List[float]] = []
        self._loaded = False

    def load(self, path: Optional[str] = None):
        """
        Load examples from a JSON file.

        JSON format:
        [
            {"question": "...", "sql": "...", "description": "..."},
            ...
        ]
        """
        file_path = path or settings.example_store_path
        p = Path(file_path)

        if not p.exists():
            logger.warning(f"Example store file not found: {file_path}, using empty store.")
            self._loaded = True
            return

        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            self.examples = data.get("examples", []) or []
        elif isinstance(data, list):
            self.examples = data
        else:
            self.examples = []

        self.embeddings = []
        logger.info(f"Loaded {len(self.examples)} examples from {file_path}")

        self._loaded = True

    def retrieve(
        self,
        question: str,
        top_k: Optional[int] = None,
        use_reranker: bool = True,
        difficulty: Optional[str] = None,
        intent_tags: Optional[list[str]] = None,
        patterns: Optional[list[str]] = None,
        table_names: Optional[list[str]] = None,
    ) -> List[dict]:
        """
        Retrieve the most relevant examples for a question.

        Args:
            question: The user's question.
            top_k: Number of examples to return.
            use_reranker: Whether to apply the reranker.

        Returns:
            List of example dicts with 'score' field added.
        """
        if not self._loaded:
            self.load()

        k = settings.example_retrieval_top_k if top_k is None else top_k

        if not self.examples or k <= 0:
            return []

        has_metadata_filters = any([difficulty, intent_tags, patterns, table_names])
        if has_metadata_filters or not self.embedding_service or len(self.embeddings) != len(self.examples):
            return self._retrieve_ranked(
                question=question,
                top_k=k,
                difficulty=difficulty,
                intent_tags=intent_tags,
                patterns=patterns,
                table_names=table_names,
            )

        # 1. Embed the query
        try:
            query_vec = self.embedding_service.embed_query(question)
        except Exception as e:
            logger.warning(f"Embedding query failed, using lexical example retrieval: {e}")
            return self._retrieve_ranked(
                question=question,
                top_k=k,
                difficulty=difficulty,
                intent_tags=intent_tags,
                patterns=patterns,
                table_names=table_names,
            )

        # 2. Compute cosine similarity
        scored = []
        for i, example in enumerate(self.examples):
            emb = self.embeddings[i] if i < len(self.embeddings) else None
            if emb is None:
                continue
            metadata_score = self._metadata_score(
                example,
                difficulty=difficulty,
                intent_tags=intent_tags,
                patterns=patterns,
                table_names=table_names,
            )
            sim = self.embedding_service.cosine_similarity(query_vec, emb)
            scored.append({
                **example,
                "score": sim + metadata_score,
                "text": self._format_example_text(example),
            })

        # 3. Sort by similarity
        scored.sort(key=lambda x: x["score"], reverse=True)

        # 4. Optionally rerank top candidates
        if use_reranker and self.reranker_service and scored:
            scored = self.reranker_service.rerank(question, scored, top_k=k)
        else:
            scored = scored[:k]

        return scored

    def _format_example_text(self, example: dict) -> str:
        """Format an example into a single text for embedding/reranking."""
        q = example.get("question", "")
        s = example.get("sql", "")
        d = example.get("description", "")
        tags = " ".join(example.get("intent_tags", []) or [])
        features = " ".join(example.get("sql_features", []) or [])
        pattern = example.get("pattern", "")
        tables = " ".join(example.get("tables", []) or [])
        joins = " ".join(example.get("join_paths", []) or [])
        return (
            f"Question: {q}\nSQL: {s}\nDescription: {d}\nPattern: {pattern}\n"
            f"Tags: {tags}\nFeatures: {features}\nTables: {tables}\nJoins: {joins}"
        )

    def _retrieve_ranked(
        self,
        question: str,
        top_k: int,
        difficulty: Optional[str] = None,
        intent_tags: Optional[list[str]] = None,
        patterns: Optional[list[str]] = None,
        table_names: Optional[list[str]] = None,
    ) -> List[dict]:
        scored = []
        for example in self.examples:
            text = self._format_example_text(example)
            score = lexical_score(question, text) + self._metadata_score(
                example,
                difficulty=difficulty,
                intent_tags=intent_tags,
                patterns=patterns,
                table_names=table_names,
            )
            if score:
                scored.append({**example, "score": score, "text": text})
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:top_k]

    def _metadata_score(
        self,
        example: dict,
        difficulty: Optional[str] = None,
        intent_tags: Optional[list[str]] = None,
        patterns: Optional[list[str]] = None,
        table_names: Optional[list[str]] = None,
    ) -> float:
        score = 0.0

        if difficulty and example.get("difficulty") == difficulty:
            score += 20.0

        requested_tags = set(intent_tags or [])
        example_tags = set(example.get("intent_tags", []) or [])
        score += 8.0 * len(requested_tags & example_tags)

        requested_patterns = set(patterns or [])
        example_pattern = example.get("pattern", "")
        if example_pattern in requested_patterns:
            score += 12.0
        for pattern in requested_patterns:
            if pattern and pattern in example_pattern:
                score += 6.0

        requested_tables = set(table_names or [])
        example_tables = set(example.get("tables", []) or [])
        score += 3.0 * len(requested_tables & example_tables)

        return score
