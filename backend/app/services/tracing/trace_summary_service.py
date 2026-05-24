"""Build compact summaries for persisted request traces."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from app.core.tracing import RequestTrace


class TraceSummaryService:
    """Create the stable summary.json document for one trace."""

    def build_summary(self, trace: RequestTrace) -> dict[str, Any]:
        return {
            "trace_id": trace.trace_id,
            "question": trace.question,
            "steps_count": len(trace.steps),
            "total_latency_ms": round(sum(step.latency_ms or 0 for step in trace.steps), 3),
            "retry_count": self._retry_count(trace),
            "supervisor_used": any(step.name == "supervisor_llm_service" for step in trace.steps),
            "final_status": trace.status,
            "final_sql": self._latest_sql(trace),
            "error_types": self._error_types(trace),
            "selected_tables": self._selected_tables(trace),
            "retrieved_patterns": self._retrieved_patterns(trace),
            "supervisor_diagnosis_summary": self._supervisor_diagnosis_summary(trace),
            "started_at": trace.started_at,
            "ended_at": trace.ended_at,
        }

    def _retry_count(self, trace: RequestTrace) -> int:
        retry_indexes = set()
        for step in trace.steps:
            if step.name.startswith("reflection_retry."):
                parts = step.name.split(".")
                if len(parts) > 1 and parts[1].isdigit():
                    retry_indexes.add(parts[1])
        return len(retry_indexes)

    def _latest_sql(self, trace: RequestTrace) -> str:
        for step in reversed(trace.steps):
            if step.name.endswith("query_service") and isinstance(step.input, dict) and step.input.get("sql"):
                return str(step.input["sql"])
            if step.name.endswith("nl2sql_service") and isinstance(step.output, str):
                return step.output
        return ""

    def _error_types(self, trace: RequestTrace) -> list[str]:
        error_types = []
        for step in trace.steps:
            output = self._as_plain(step.output)
            if isinstance(output, dict):
                candidates = [output]
                for key in ["parsed_result", "fallback_result"]:
                    if isinstance(output.get(key), dict):
                        candidates.append(output[key])
                for candidate in candidates:
                    error_type = candidate.get("error_type")
                    if error_type and error_type not in error_types:
                        error_types.append(error_type)
        return error_types

    def _selected_tables(self, trace: RequestTrace) -> list[str]:
        for step in reversed(trace.steps):
            if step.name == "context_builder":
                output = self._as_plain(step.output)
                if isinstance(output, dict):
                    return [
                        table.get("name")
                        for table in output.get("tables", [])
                        if isinstance(table, dict) and table.get("name")
                    ]
        return []

    def _retrieved_patterns(self, trace: RequestTrace) -> list[str]:
        for step in reversed(trace.steps):
            if step.name == "context_builder":
                output = self._as_plain(step.output)
                if isinstance(output, dict):
                    return [
                        pattern.get("name")
                        for pattern in output.get("patterns", [])
                        if isinstance(pattern, dict) and pattern.get("name")
                    ]
        return []

    def _supervisor_diagnosis_summary(self, trace: RequestTrace) -> dict[str, Any] | None:
        for step in reversed(trace.steps):
            if step.name != "supervisor_llm_service":
                continue
            output = self._as_plain(step.output)
            if not isinstance(output, dict):
                return None
            parsed = output.get("parsed_result")
            if isinstance(parsed, dict):
                return {
                    "error_type": parsed.get("error_type"),
                    "root_cause_step": parsed.get("root_cause_step"),
                    "should_retry": parsed.get("should_retry"),
                    "reason": parsed.get("reason"),
                }
            return {
                "status": step.status,
                "error": step.error,
                "supervisor_model": output.get("supervisor_model"),
            }
        return None

    def _as_plain(self, value: Any) -> Any:
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, dict):
            return {key: self._as_plain(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._as_plain(item) for item in value]
        return value
