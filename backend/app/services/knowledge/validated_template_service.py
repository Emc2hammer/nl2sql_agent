"""Approved validated-template retrieval for optional SQL reuse."""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional

from app.services.knowledge.knowledge_base import KNOWLEDGE_DIR


TEMPLATE_STORE_PATH = KNOWLEDGE_DIR / "validated_templates.jsonl"
ALLOWED_REUSE_SOURCE = "approved_template"


@dataclass
class TemplateDecision:
    """Decision record for one template-reuse check."""

    template_reuse_checked: bool
    template_reuse_hit: bool
    template_reuse_allowed: bool
    template_reuse_reason: str
    template_id: str | None = None
    template_score: float | None = None
    sql: str | None = None
    pattern: str = ""
    source: str = ""
    approved: bool = False
    replacements: dict[str, str] | None = None
    retrieved_example: dict[str, Any] | None = None

    def to_trace(self) -> dict[str, Any]:
        return asdict(self)


class ValidatedTemplateService:
    """Retrieve approved templates without reading few-shot or question-bank files.

    The service is domain-agnostic: it does not route on business keywords. It
    only reads records from ``validated_templates.jsonl``, scores question/table
    similarity, and performs generic SQL literal replacement.
    """

    MIN_QUESTION_SIMILARITY = 0.55

    def __init__(
        self,
        template_path: Path | str = TEMPLATE_STORE_PATH,
        templates: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        self.template_path = Path(template_path)
        self._templates = templates

    def decide(
        self,
        question: str,
        context,
        *,
        enable_reuse: Optional[bool] = None,
        threshold: Optional[float] = None,
    ) -> TemplateDecision:
        templates = self._load_templates()
        candidates = self._rank_candidates(question, context, templates)
        if not candidates:
            return TemplateDecision(
                template_reuse_checked=True,
                template_reuse_hit=False,
                template_reuse_allowed=False,
                template_reuse_reason="no_template_candidate",
            )

        best = candidates[0]
        default_enabled, default_threshold = self._settings_defaults()
        enabled = default_enabled if enable_reuse is None else enable_reuse
        min_score = default_threshold if threshold is None else threshold
        allowed, reason = self._allow_reuse(best, enabled=enabled, threshold=min_score)
        return TemplateDecision(
            template_reuse_checked=True,
            template_reuse_hit=True,
            template_reuse_allowed=allowed,
            template_reuse_reason=reason,
            template_id=best["id"],
            template_score=best["score"],
            sql=best["sql"],
            pattern=best["pattern"],
            source=best["source"],
            approved=best["approved"],
            replacements=best["replacements"],
            retrieved_example=self._to_retrieved_example(best),
        )

    def retrieve_preview(self, question: str, context, top_k: int = 5) -> list[dict[str, Any]]:
        return [
            {
                "id": item["id"],
                "score": item["score"],
                "source": item["source"],
                "approved": item["approved"],
                "pattern": item["pattern"],
            }
            for item in self._rank_candidates(question, context, self._load_templates())[:top_k]
        ]

    def _load_templates(self) -> list[dict[str, Any]]:
        if self._templates is not None:
            return self._templates
        if not self.template_path.exists():
            return []

        templates = []
        for line in self.template_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                templates.append(item)
        return templates

    def _rank_candidates(self, question: str, context, templates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candidates = []
        for template in templates:
            sql = template.get("sql") or template.get("template_sql")
            template_question = template.get("question", "")
            if not sql or not template_question:
                continue

            question_similarity = self._question_similarity(question, template_question)
            if question_similarity < self.MIN_QUESTION_SIMILARITY:
                continue

            rendered_sql, replacements = self._render_sql(
                template_sql=sql,
                template_question=template_question,
                question=question,
            )
            table_score = self._table_overlap(context.table_names, template.get("tables", []) or [])
            pattern_score = self._pattern_score(context, template)
            score = round(question_similarity + table_score + pattern_score, 4)
            candidates.append(
                {
                    "id": template.get("id") or template.get("template_id") or "unknown",
                    "score": score,
                    "sql": rendered_sql,
                    "question": template_question,
                    "pattern": template.get("pattern", ""),
                    "tables": template.get("tables", []) or [],
                    "source": template.get("source", ""),
                    "approved": bool(template.get("approved", False)),
                    "replacements": replacements,
                }
            )

        candidates.sort(key=lambda item: (item["score"], item["id"]), reverse=True)
        return candidates

    def _allow_reuse(self, candidate: dict[str, Any], *, enabled: bool, threshold: float) -> tuple[bool, str]:
        if not enabled:
            return False, "template_reuse_disabled"
        if candidate["source"] != ALLOWED_REUSE_SOURCE:
            return False, f"source_not_allowed:{candidate['source'] or 'unknown'}"
        if not candidate["approved"]:
            return False, "template_not_approved"
        if candidate["score"] < threshold:
            return False, f"score_below_threshold:{candidate['score']}<{threshold}"
        return True, "approved_template_reused"

    def _settings_defaults(self) -> tuple[bool, float]:
        try:
            from app.core.config import settings

            return settings.enable_template_reuse, settings.template_reuse_threshold
        except Exception:
            enabled = os.getenv("ENABLE_TEMPLATE_REUSE", "false").strip().lower() in {"1", "true", "yes", "on"}
            try:
                threshold = float(os.getenv("TEMPLATE_REUSE_THRESHOLD", "0.95"))
            except ValueError:
                threshold = 0.95
            return enabled, threshold

    def _to_retrieved_example(self, candidate: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": candidate["id"],
            "question": candidate["question"],
            "sql": candidate["sql"],
            "pattern": candidate["pattern"],
            "tables": candidate["tables"],
            "score": candidate["score"],
            "source": candidate["source"],
        }

    def _question_similarity(self, question: str, template_question: str) -> float:
        q_tokens = self._tokens(question)
        t_tokens = self._tokens(template_question)
        token_similarity = self._jaccard(q_tokens, t_tokens)
        sequence_similarity = SequenceMatcher(None, question, template_question).ratio()
        return 0.65 * token_similarity + 0.35 * sequence_similarity

    def _tokens(self, text: str) -> set[str]:
        tokens = {token.lower() for token in re.findall(r"[A-Za-z0-9_\-]+", text) if len(token) > 1}
        cjk_chars = [char for char in text if "\u4e00" <= char <= "\u9fff"]
        tokens.update("".join(cjk_chars[i : i + 2]) for i in range(max(len(cjk_chars) - 1, 0)))
        tokens.update("".join(cjk_chars[i : i + 3]) for i in range(max(len(cjk_chars) - 2, 0)))
        return {token for token in tokens if token}

    def _jaccard(self, left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        return len(left & right) / len(left | right)

    def _table_overlap(self, context_tables: list[str], template_tables: list[str]) -> float:
        context_set = set(context_tables)
        template_set = set(template_tables)
        if not context_set or not template_set:
            return 0.0
        return 0.18 * (len(context_set & template_set) / len(context_set | template_set))

    def _pattern_score(self, context, template: dict[str, Any]) -> float:
        context_patterns = {pattern.name for pattern in context.patterns}
        template_pattern = template.get("pattern", "")
        return 0.12 if template_pattern and template_pattern in context_patterns else 0.0

    def _render_sql(
        self,
        template_sql: str,
        template_question: str,
        question: str,
    ) -> tuple[str, dict[str, str]]:
        replacements = self._literal_replacements(template_sql, template_question, question)
        rendered = template_sql
        for old, new in replacements.items():
            rendered = rendered.replace(f"'{old}'", f"'{new}'")
        return rendered, replacements

    def _literal_replacements(
        self,
        template_sql: str,
        template_question: str,
        question: str,
    ) -> dict[str, str]:
        literals = list(dict.fromkeys(re.findall(r"'([^']+)'", template_sql)))
        replacements: dict[str, str] = {}
        for literal in literals:
            replacement = self._replacement_for_literal(literal, template_question, question)
            if replacement and replacement != literal:
                replacements[literal] = replacement
        return replacements

    def _replacement_for_literal(
        self,
        literal: str,
        template_question: str,
        question: str,
    ) -> Optional[str]:
        if literal in question:
            return literal

        literal_shape = self._literal_shape(literal)
        if literal_shape == "date8":
            return self._single_candidate(r"\b\d{8}\b", template_question, question)
        if literal_shape == "month6":
            return self._single_candidate(r"\b\d{6}\b", template_question, question)
        if literal_shape == "identifier":
            return self._single_candidate(self._identifier_pattern(literal), template_question, question)
        if literal_shape == "number":
            return self._single_candidate(r"\b\d+(?:\.\d+)?\b", template_question, question)
        return None

    def _literal_shape(self, literal: str) -> str:
        if re.fullmatch(r"\d{8}", literal):
            return "date8"
        if re.fullmatch(r"\d{6}", literal):
            return "month6"
        if re.fullmatch(r"\d+(?:\.\d+)?", literal):
            return "number"
        if re.fullmatch(r"[A-Za-z]+[A-Za-z0-9_\-]*\d[A-Za-z0-9_\-]*", literal):
            return "identifier"
        return "text"

    def _identifier_pattern(self, literal: str) -> str:
        if "-" in literal:
            return r"\b[A-Za-z]+[A-Za-z0-9]*-[A-Za-z0-9_\-]*\d[A-Za-z0-9_\-]*\b"
        if "_" in literal:
            return r"\b[A-Za-z]+[A-Za-z0-9]*_[A-Za-z0-9_]*\d[A-Za-z0-9_]*\b"
        return r"\b[A-Za-z]+[A-Za-z0-9_]*\d[A-Za-z0-9_]*\b"

    def _single_candidate(self, pattern: str, template_question: str, question: str) -> Optional[str]:
        template_values = set(re.findall(pattern, template_question, flags=re.IGNORECASE))
        question_values = list(dict.fromkeys(re.findall(pattern, question, flags=re.IGNORECASE)))
        new_values = [value for value in question_values if value not in template_values]
        if len(new_values) == 1:
            return new_values[0]
        return None
