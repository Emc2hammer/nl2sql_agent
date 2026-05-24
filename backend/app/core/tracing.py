"""Structured tracing utilities for NL2SQL requests."""

from __future__ import annotations

import json
import os
import time
import uuid
import hashlib
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar

BACKEND_DIR = Path(__file__).resolve().parents[2]
TRACE_DIR = BACKEND_DIR / "logs" / "traces"

T = TypeVar("T")


@dataclass
class TraceStep:
    """One structured step in an NL2SQL request trace."""

    name: str
    input: Any = None
    output: Any = None
    status: str = "success"
    error: str | None = None
    latency_ms: float = 0.0
    started_at: str = ""
    ended_at: str = ""


@dataclass
class RequestTrace:
    """Trace document persisted for one /api/chat request."""

    trace_id: str
    request_path: str
    question: str
    started_at: str
    ended_at: str | None = None
    status: str = "running"
    steps: list[TraceStep] = field(default_factory=list)


def truncate_for_trace(value: Any, max_chars: int = 1000, *, _key: str = "") -> Any:
    """Recursively trim large values before persisting trace data."""
    lowered_key = _key.lower()
    if any(token in lowered_key for token in ["embedding", "vector", "token_stream"]):
        return "[omitted]"

    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        if len(value) <= max_chars:
            return value
        return value[:max_chars] + f"...[truncated {len(value) - max_chars} chars]"
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return truncate_for_trace(asdict(value), max_chars=max_chars, _key=_key)
    if hasattr(value, "model_dump"):
        return truncate_for_trace(value.model_dump(), max_chars=max_chars, _key=_key)
    if hasattr(value, "dict"):
        return truncate_for_trace(value.dict(), max_chars=max_chars, _key=_key)
    if isinstance(value, dict):
        trimmed = {}
        for key, item in value.items():
            key_str = str(key)
            if any(token in key_str.lower() for token in ["embedding", "vector", "token_stream"]):
                continue
            if key_str == "rows" and isinstance(item, list):
                trimmed["row_count"] = len(item)
                trimmed["first_rows_preview"] = [
                    truncate_for_trace(row, max_chars=max_chars, _key=key_str)
                    for row in item[:5]
                ]
                continue
            trimmed[key_str] = truncate_for_trace(item, max_chars=max_chars, _key=key_str)
        return trimmed
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        return [truncate_for_trace(item, max_chars=max_chars, _key=_key) for item in items[:20]]
    return truncate_for_trace(repr(value), max_chars=max_chars, _key=_key)


class TraceRecorder:
    """Record structured step data and persist it to disk as split JSON files."""

    def __init__(self, question: str, request_path: str = "/api/chat", trace_id: str | None = None) -> None:
        self.trace = RequestTrace(
            trace_id=trace_id or uuid.uuid4().hex,
            request_path=request_path,
            question=question,
            started_at=self._now(),
        )

    @property
    def trace_id(self) -> str:
        return self.trace.trace_id

    def record_step(
        self,
        name: str,
        *,
        input: Any = None,
        output: Any = None,
        status: str = "success",
        error: str | None = None,
        latency_ms: float = 0.0,
        started_at: str | None = None,
        ended_at: str | None = None,
    ) -> TraceStep:
        step = TraceStep(
            name=name,
            input=self._to_jsonable(input),
            output=self._to_jsonable(output),
            status=status,
            error=error,
            latency_ms=round(latency_ms, 3),
            started_at=started_at or self._now(),
            ended_at=ended_at or self._now(),
        )
        self.trace.steps.append(step)
        return step

    def run(self, name: str, input: Any, func: Callable[[], T]) -> T:
        """Run a callable and record success/error with latency."""
        started_at = self._now()
        started = time.perf_counter()
        try:
            output = func()
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            self.record_step(
                name,
                input=input,
                status="error",
                error=str(exc),
                latency_ms=latency_ms,
                started_at=started_at,
                ended_at=self._now(),
            )
            raise

        latency_ms = (time.perf_counter() - started) * 1000
        self.record_step(
            name,
            input=input,
            output=output,
            latency_ms=latency_ms,
            started_at=started_at,
            ended_at=self._now(),
        )
        return output

    def save(self, status: str = "success", error: str | None = None) -> Path:
        """Persist the trace under backend/logs/traces/{trace_id}/."""
        from app.services.tracing.trace_summary_service import TraceSummaryService

        try:
            from app.core.config import settings

            trace_level = settings.trace_level
        except Exception:
            trace_level = os.getenv("TRACE_LEVEL", "normal").strip().lower()
            if trace_level not in {"lite", "normal", "debug"}:
                trace_level = "normal"

        self.trace.status = status
        self.trace.ended_at = self._now()
        if error:
            self.record_step("request", status="error", error=error)

        trace_dir = TRACE_DIR / self.trace.trace_id
        trace_dir.mkdir(parents=True, exist_ok=True)

        summary = TraceSummaryService().build_summary(self.trace)
        self._write_json(trace_dir / "summary.json", truncate_for_trace(summary, max_chars=1000))
        self._write_json(trace_dir / "steps.json", self._steps_for_level(trace_level))

        if trace_level == "debug":
            self._write_json(
                trace_dir / "debug.json",
                truncate_for_trace(self._to_jsonable(self.trace), max_chars=4000),
            )

        return trace_dir

    def _steps_for_level(self, level: str) -> list[dict[str, Any]]:
        if level == "lite":
            return [self._lite_step(step) for step in self.trace.steps]
        return [self._normal_step(step) for step in self.trace.steps]

    def _lite_step(self, step: TraceStep) -> dict[str, Any]:
        return {
            "step_name": step.name,
            "status": step.status,
            "latency_ms": step.latency_ms,
            "error": truncate_for_trace(step.error, max_chars=1000),
        }

    def _normal_step(self, step: TraceStep) -> dict[str, Any]:
        data = self._lite_step(step)
        data.update(
            {
                "input_summary": self._input_summary(step),
                "output_summary": self._output_summary(step),
                "started_at": step.started_at,
                "ended_at": step.ended_at,
            }
        )
        return truncate_for_trace(data, max_chars=1000)

    def _input_summary(self, step: TraceStep) -> Any:
        if isinstance(step.input, dict):
            return {
                key: value
                for key, value in step.input.items()
                if key in {"question", "sql", "tables", "patterns", "top_k", "difficulty", "trace_id", "error_type"}
            }
        return None

    def _output_summary(self, step: TraceStep) -> Any:
        output = step.output
        if step.name == "schema" and isinstance(output, list):
            return {
                "table_count": len(output),
                "schema_cache_hit": False,
                "schema_hash": self._schema_hash(output),
            }
        if step.name == "difficulty_router" and isinstance(output, dict):
            return {
                "level": output.get("level"),
                "label": output.get("label"),
                "reasons": output.get("reasons", []),
            }
        if step.name == "query_router" and isinstance(output, dict):
            return {
                "domain": output.get("domain"),
                "matched_keywords": output.get("matched_keywords", []),
                "selected_tables": output.get("selected_tables", []),
                "selected_columns": output.get("selected_columns", []),
                "column_similarity_scores": output.get("column_similarity_scores", []),
                "routing_reason": output.get("routing_reason", []),
                "why_alias_table_selected": output.get("why_alias_table_selected", ""),
                "why_main_table_field_rejected": output.get("why_main_table_field_rejected", ""),
            }
        if step.name.endswith("query_service") and isinstance(output, dict):
            rows = output.get("rows") or []
            return {
                "row_count": len(rows),
                "columns": output.get("columns", []),
                "first_rows_preview": rows[:5],
                "error": output.get("error"),
                "execution_time": output.get("execution_time"),
            }
        if step.name.endswith("sql_guard") and isinstance(output, list):
            return {
                "passed": bool(output[0]) if len(output) > 0 else False,
                "reason": output[1] if len(output) > 1 else "",
                "risk_level": output[2] if len(output) > 2 else "",
            }
        if step.name.endswith("sql_semantic_verifier") and isinstance(output, list):
            return {
                "issue_count": len(output),
                "first_issue": output[0] if output else None,
            }
        if step.name.endswith("result_sanity") and isinstance(output, list):
            return {
                "issue_count": len(output),
                "first_issue": output[0] if output else None,
            }
        if step.name == "context_builder" and isinstance(output, dict):
            return {
                "selected_tables": [
                    table.get("name")
                    for table in output.get("tables", [])
                    if isinstance(table, dict)
                ],
                "retrieved_patterns": [
                    pattern.get("name")
                    for pattern in output.get("patterns", [])
                    if isinstance(pattern, dict)
                ],
                "rules_count": len(output.get("rules", []) or []),
                "joins_count": len(output.get("joins", []) or []),
                "selected_columns": output.get("selected_columns", []),
                "column_similarity_scores": output.get("column_scores", []),
                "routing_reason": output.get("routing_reason", []),
                "why_alias_table_selected": output.get("why_alias_table_selected", ""),
                "why_main_table_field_rejected": output.get("why_main_table_field_rejected", ""),
            }
        if step.name in {"example_store", "failure_case_store"} and isinstance(output, list):
            return {
                "top_k_ids": [item.get("id") or item.get("error_type") for item in output[:3] if isinstance(item, dict)],
                "top_k_scores": [item.get("score") for item in output[:3] if isinstance(item, dict)],
                "selected_example_ids": [item.get("id") for item in output[:3] if isinstance(item, dict) and item.get("id")],
            }
        if step.name == "validated_template_service" and isinstance(output, dict):
            return {
                "template_reuse_checked": output.get("template_reuse_checked"),
                "template_reuse_hit": output.get("template_reuse_hit"),
                "template_reuse_allowed": output.get("template_reuse_allowed"),
                "template_reuse_reason": output.get("template_reuse_reason"),
                "template_id": output.get("template_id"),
                "template_score": output.get("template_score"),
                "pattern": output.get("pattern"),
                "source": output.get("source"),
                "approved": output.get("approved"),
                "replacement_keys": list((output.get("replacements") or {}).keys()),
            }
        if step.name == "supervisor_llm_service" and isinstance(output, dict):
            parsed = output.get("parsed_result") or {}
            return {
                "supervisor_model": output.get("supervisor_model"),
                "supervisor_latency_ms": output.get("supervisor_latency_ms"),
                "supervisor_raw_output_preview": output.get("supervisor_raw_output_preview"),
                "supervisor_raw_output_len": output.get("supervisor_raw_output_len"),
                "diagnosis": parsed,
            }
        if step.name == "empty_result_diagnoser" and isinstance(output, dict):
            return {
                "where_conditions": output.get("where_conditions", []),
                "suspect_conditions": output.get("suspect_conditions", []),
                "condition_probe_results": output.get("condition_probe_results", []),
                "value_probe_results": output.get("value_probe_results", []),
                "diagnosis_reason": output.get("diagnosis_reason"),
                "retry_advice": output.get("retry_advice"),
                "allow_retry": output.get("allow_retry"),
                "errors": output.get("errors", []),
            }
        if step.name == "condition_probe" and isinstance(output, dict):
            return {
                "where_conditions": output.get("where_conditions", []),
                "condition_probe_results": output.get("condition_probe_results", []),
                "suspect_conditions": output.get("suspect_conditions", []),
            }
        if step.name == "value_resolver" and isinstance(output, dict):
            return {
                "enabled": output.get("enabled"),
                "value_probe_results": output.get("value_probe_results", []),
                "retry_advice": output.get("retry_advice"),
                "allow_retry": output.get("allow_retry"),
            }
        if isinstance(output, dict):
            return {
                key: output.get(key)
                for key in ["error", "columns", "execution_time", "enabled", "reason", "error_type", "should_retry"]
                if key in output
            } or list(output.keys())[:8]
        if isinstance(output, list):
            return {"count": len(output), "first": output[0] if output else None}
        return output

    def _schema_hash(self, schema_info: list[Any]) -> str:
        compact = []
        for table in schema_info:
            if not isinstance(table, dict):
                continue
            compact.append(
                {
                    "table_name": table.get("table_name"),
                    "columns": [
                        {
                            "name": column.get("name"),
                            "type": column.get("type"),
                        }
                        for column in table.get("columns", [])
                        if isinstance(column, dict)
                    ],
                }
            )
        payload = json.dumps(compact, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def _write_json(self, path: Path, data: Any) -> None:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _to_jsonable(self, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {str(key): self._to_jsonable(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._to_jsonable(item) for item in value]
        if is_dataclass(value):
            return self._to_jsonable(asdict(value))
        if hasattr(value, "model_dump"):
            return self._to_jsonable(value.model_dump())
        if hasattr(value, "dict"):
            return self._to_jsonable(value.dict())
        return repr(value)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
