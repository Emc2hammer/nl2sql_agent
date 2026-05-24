"""Persistent failure-case memory for NL2SQL self-learning."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[2]
FAILURE_CASES_PATH = BACKEND_DIR / "data" / "knowledge" / "failure_cases.jsonl"


class FailureCaseStore:
    """JSONL-backed failure memory with lightweight BM25-style retrieval."""

    def __init__(self, path: Path = FAILURE_CASES_PATH) -> None:
        self.path = path

    def append(
        self,
        *,
        question: str,
        generated_sql: str,
        error_type: str,
        error_message: str,
        corrected_sql: str,
        lesson: str,
        tables: list[str],
        columns: list[str],
        difficulty: str,
        domain: str,
    ) -> dict[str, Any]:
        case = {
            "question": question,
            "generated_sql": generated_sql,
            "error_type": error_type,
            "error_message": error_message,
            "corrected_sql": corrected_sql,
            "lesson": lesson,
            "tables": tables,
            "columns": columns,
            "difficulty": difficulty,
            "domain": domain,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(case, ensure_ascii=False) + "\n")
        return case

    def retrieve(
        self,
        *,
        question: str,
        tables: list[str],
        patterns: list[str],
        top_k: int = 3,
    ) -> list[dict[str, Any]]:
        cases = self._load()
        if not cases:
            return []

        query_tokens = self._tokens(" ".join([question, *tables, *patterns]))
        case_tokens = [self._tokens(self._search_text(case)) for case in cases]
        doc_freq: dict[str, int] = {}
        for tokens in case_tokens:
            for token in set(tokens):
                doc_freq[token] = doc_freq.get(token, 0) + 1

        avg_len = sum(len(tokens) for tokens in case_tokens) / max(len(case_tokens), 1)
        scored = []
        for case, tokens in zip(cases, case_tokens):
            score = self._bm25_score(query_tokens, tokens, doc_freq, len(cases), avg_len)
            score += self._metadata_score(case, tables, patterns)
            if score > 0:
                enriched = dict(case)
                enriched["score"] = round(score, 4)
                scored.append(enriched)

        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:top_k]

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        cases = []
        with self.path.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    cases.append(item)
        return cases

    def _bm25_score(
        self,
        query_tokens: list[str],
        doc_tokens: list[str],
        doc_freq: dict[str, int],
        doc_count: int,
        avg_len: float,
    ) -> float:
        if not query_tokens or not doc_tokens:
            return 0.0
        k1 = 1.5
        b = 0.75
        doc_len = len(doc_tokens)
        term_freq: dict[str, int] = {}
        for token in doc_tokens:
            term_freq[token] = term_freq.get(token, 0) + 1

        score = 0.0
        for token in set(query_tokens):
            tf = term_freq.get(token, 0)
            if tf == 0:
                continue
            df = doc_freq.get(token, 0)
            idf = math.log(1 + (doc_count - df + 0.5) / (df + 0.5))
            denom = tf + k1 * (1 - b + b * doc_len / max(avg_len, 1))
            score += idf * (tf * (k1 + 1)) / denom
        return score

    def _metadata_score(self, case: dict[str, Any], tables: list[str], patterns: list[str]) -> float:
        score = 0.0
        case_tables = set(case.get("tables") or [])
        case_patterns = set(case.get("patterns") or [])
        score += 2.0 * len(set(tables) & case_tables)
        score += 1.5 * len(set(patterns) & case_patterns)
        return score

    def _search_text(self, case: dict[str, Any]) -> str:
        return " ".join(
            str(part)
            for part in [
                case.get("question", ""),
                case.get("generated_sql", ""),
                case.get("error_type", ""),
                case.get("error_message", ""),
                case.get("lesson", ""),
                " ".join(case.get("tables") or []),
                " ".join(case.get("columns") or []),
            ]
        )

    def _tokens(self, text: str) -> list[str]:
        return [token.lower() for token in re.findall(r"[\w\u4e00-\u9fff]+", text) if len(token) > 1]
