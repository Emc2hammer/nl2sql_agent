"""Reflection over structured NL2SQL traces."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from app.core.tracing import RequestTrace, TraceStep

if TYPE_CHECKING:
    from app.services.llm.supervisor_llm_service import SupervisorLLMService


@dataclass(frozen=True)
class ReflectionResult:
    """Diagnosis and retry guidance derived from a request trace."""

    error_type: str
    root_cause_step: str
    reason: str
    repair_suggestion: str
    should_retry: bool


class ReflectionService:
    """Classify NL2SQL failures, optionally using a dedicated supervisor LLM."""

    SQL_SYNTAX_ERROR = "SQL_SYNTAX_ERROR"
    SCHEMA_FIELD_ERROR = "SCHEMA_FIELD_ERROR"
    MISSING_TABLE = "MISSING_TABLE"
    EMPTY_RESULT = "EMPTY_RESULT"
    WRONG_JOIN = "WRONG_JOIN"
    WRONG_AGGREGATION = "WRONG_AGGREGATION"
    WRONG_TIME_FILTER = "WRONG_TIME_FILTER"
    BUSINESS_RULE_MISSING = "BUSINESS_RULE_MISSING"
    UNKNOWN = "UNKNOWN"

    ERROR_TYPES = {
        SQL_SYNTAX_ERROR,
        SCHEMA_FIELD_ERROR,
        MISSING_TABLE,
        EMPTY_RESULT,
        WRONG_JOIN,
        WRONG_AGGREGATION,
        WRONG_TIME_FILTER,
        BUSINESS_RULE_MISSING,
        UNKNOWN,
    }

    def __init__(self, supervisor_service: Optional["SupervisorLLMService"] = None) -> None:
        self.supervisor_service = supervisor_service

    def reflect(self, trace: RequestTrace) -> ReflectionResult:
        rule_result = self._reflect_by_rules(trace)
        if not self._should_call_supervisor(rule_result):
            return rule_result

        supervisor_result = self._reflect_with_supervisor(trace, rule_result)
        return supervisor_result or rule_result

    def _reflect_by_rules(self, trace: RequestTrace) -> ReflectionResult:
        semantic_step = self._last_step(trace, "sql_semantic_verifier")
        semantic_result = self._reflect_semantic_step(semantic_step)
        if semantic_result:
            return semantic_result

        query_step = self._last_success_or_error_step(trace, "query_service")
        query_result = self._reflect_query_step(query_step)
        if query_result:
            return query_result

        sanity_step = self._last_step(trace, "result_sanity")
        sanity_result = self._reflect_sanity_step(sanity_step)
        if sanity_result:
            return sanity_result

        return ReflectionResult(
            error_type=self.UNKNOWN,
            root_cause_step="unknown",
            reason="No known failing trace step matched the reflection rules.",
            repair_suggestion=(
                "Re-check the selected tables, joins, filters, aggregation grain, and business rules. "
                "Regenerate a conservative SELECT using only retrieved schema fields."
            ),
            should_retry=False,
        )

    def _should_call_supervisor(self, rule_result: ReflectionResult) -> bool:
        if not self.supervisor_service or not self.supervisor_service.is_configured:
            return False
        return rule_result.should_retry or rule_result.error_type == self.UNKNOWN

    def _reflect_with_supervisor(
        self,
        trace: RequestTrace,
        fallback: ReflectionResult,
    ) -> Optional[ReflectionResult]:
        payload = self._build_supervisor_payload(trace, fallback)
        system_prompt = self._supervisor_system_prompt()
        started = time.perf_counter()
        raw_output = ""
        try:
            raw_output = self.supervisor_service.reflect(
                system_prompt=system_prompt,
                user_payload=json.dumps(payload, ensure_ascii=False),
            )
            latency_ms = (time.perf_counter() - started) * 1000
            result = self._parse_supervisor_result(raw_output)
            self._record_supervisor_step(
                trace,
                status="success",
                latency_ms=latency_ms,
                raw_output=raw_output,
                parsed_result=result,
            )
            return result
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            self._record_supervisor_step(
                trace,
                status="error",
                latency_ms=latency_ms,
                raw_output=raw_output,
                error=str(exc),
                fallback=fallback,
            )
            return None

    def _supervisor_system_prompt(self) -> str:
        return (
            "You are a strict NL2SQL supervisor. Diagnose whether the generated SQLite SQL is wrong. "
            "Return ONLY valid JSON with exactly these keys: error_type, root_cause_step, reason, "
            "repair_suggestion, should_retry. error_type must be one of: "
            + ", ".join(sorted(self.ERROR_TYPES))
            + ". Do not include markdown, comments, or extra text."
        )

    def _build_supervisor_payload(self, trace: RequestTrace, fallback: ReflectionResult) -> dict[str, Any]:
        context = self._context_summary(trace)
        return {
            "question": trace.question,
            "generated_sql": self._latest_sql(trace),
            "compact_context": context,
            "trace_steps_summary": self._trace_steps_summary(trace),
            "query_error": self._latest_query_error(trace),
            "sanity_warning": self._latest_sanity_warning(trace),
            "retrieved_business_rules": context.get("rules", []),
            "join_paths": context.get("joins", []),
            "rule_initial_reflection": {
                "error_type": fallback.error_type,
                "root_cause_step": fallback.root_cause_step,
                "reason": fallback.reason,
                "repair_suggestion": fallback.repair_suggestion,
                "should_retry": fallback.should_retry,
            },
        }

    def _parse_supervisor_result(self, raw_output: str) -> ReflectionResult:
        text = raw_output.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("Supervisor output must be a JSON object.")

        error_type = str(data.get("error_type", self.UNKNOWN))
        if error_type not in self.ERROR_TYPES:
            error_type = self.UNKNOWN

        return ReflectionResult(
            error_type=error_type,
            root_cause_step=str(data.get("root_cause_step", "unknown")),
            reason=str(data.get("reason", "")),
            repair_suggestion=str(data.get("repair_suggestion", "")),
            should_retry=bool(data.get("should_retry", False)),
        )

    def _record_supervisor_step(
        self,
        trace: RequestTrace,
        *,
        status: str,
        latency_ms: float,
        raw_output: str,
        parsed_result: Optional[ReflectionResult] = None,
        error: Optional[str] = None,
        fallback: Optional[ReflectionResult] = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        model = self.supervisor_service.model if self.supervisor_service else ""
        trace.steps.append(
            TraceStep(
                name="supervisor_llm_service",
                input={"supervisor_model": model},
                output={
                    "supervisor_llm_service": "SupervisorLLMService",
                    "supervisor_model": model,
                    "supervisor_latency_ms": round(latency_ms, 3),
                    "supervisor_raw_output_preview": raw_output[:1000],
                    "supervisor_raw_output_len": len(raw_output),
                    "parsed_result": parsed_result,
                    "fallback_result": fallback,
                },
                status=status,
                error=error,
                latency_ms=round(latency_ms, 3),
                started_at=now,
                ended_at=now,
            )
        )

    def _reflect_semantic_step(self, step: Optional[TraceStep]) -> Optional[ReflectionResult]:
        if not step or not step.output:
            return None

        issues = step.output if isinstance(step.output, list) else []
        blocking = [issue for issue in issues if isinstance(issue, dict) and issue.get("severity") == "error"]
        if not blocking:
            return None

        issue = blocking[-1]
        code = str(issue.get("code", ""))
        message = str(issue.get("message", ""))
        if code in {"unknown_column"}:
            error_type = self.SCHEMA_FIELD_ERROR
            suggestion = "Use only columns listed in the retrieved schema context; replace or remove the unknown column."
        elif code.startswith("missing_"):
            error_type = self.BUSINESS_RULE_MISSING
            suggestion = "Add the missing business-rule predicate or required code-table join before executing."
        elif "grain" in code or "join" in code:
            error_type = self.WRONG_JOIN
            suggestion = "Aggregate facts to the correct business grain before joining, and use retrieved join paths."
        else:
            error_type = self.UNKNOWN
            suggestion = "Fix the semantic issue reported by verification and regenerate SQL."

        return ReflectionResult(
            error_type=error_type,
            root_cause_step=step.name,
            reason=f"{code}: {message}",
            repair_suggestion=suggestion,
            should_retry=True,
        )

    def _reflect_query_step(self, step: Optional[TraceStep]) -> Optional[ReflectionResult]:
        if not step:
            return None

        error = None
        if isinstance(step.output, dict):
            error = step.output.get("error")
        if not error and step.error:
            error = step.error
        if not error:
            return None

        normalized = str(error).lower()
        if "no such table" in normalized:
            error_type = self.MISSING_TABLE
            suggestion = "Replace the missing table with one of the retrieved table names and keep joins within the context."
        elif "no such column" in normalized or "unknown column" in normalized:
            error_type = self.SCHEMA_FIELD_ERROR
            suggestion = "Replace the missing column with a column from the retrieved schema; check aliases carefully."
        elif "syntax" in normalized or "near" in normalized or "parse" in normalized:
            error_type = self.SQL_SYNTAX_ERROR
            suggestion = "Regenerate valid SQLite SELECT syntax only; avoid unsupported functions or malformed clauses."
        elif "ambiguous" in normalized:
            error_type = self.WRONG_JOIN
            suggestion = "Qualify ambiguous columns with aliases and ensure joins use the retrieved join paths."
        else:
            error_type = self.UNKNOWN
            suggestion = "Repair the SQL using the database error, retrieved schema, and existing join hints."

        return ReflectionResult(
            error_type=error_type,
            root_cause_step=step.name,
            reason=str(error),
            repair_suggestion=suggestion,
            should_retry=True,
        )

    def _reflect_sanity_step(self, step: Optional[TraceStep]) -> Optional[ReflectionResult]:
        if not step or not step.output:
            return None

        warnings = step.output if isinstance(step.output, list) else []
        warning = next((item for item in warnings if isinstance(item, dict)), None)
        if not warning:
            return None

        code = str(warning.get("code", ""))
        message = str(warning.get("message", ""))
        if code == "empty_result":
            error_type = self.EMPTY_RESULT
            suggestion = "Relax overly strict filters, verify date ranges, and make sure code-table predicates match valid values."
        elif "date" in code or "time" in code:
            error_type = self.WRONG_TIME_FILTER
            suggestion = "Use the dataset date-key format and derive date ranges from the question precisely."
        elif "rate" in code or "ppm" in code:
            error_type = self.WRONG_AGGREGATION
            suggestion = "Recompute rates from numerator and denominator aggregates at the same grain."
        elif "quantity" in code or "sign" in code:
            error_type = self.WRONG_AGGREGATION
            suggestion = "Separate inbound/outbound quantities or aggregate signs intentionally before calculating totals."
        else:
            error_type = self.UNKNOWN
            suggestion = "Review the suspicious result shape and regenerate SQL with safer filters and aggregation."

        return ReflectionResult(
            error_type=error_type,
            root_cause_step=step.name,
            reason=f"{code}: {message}",
            repair_suggestion=suggestion,
            should_retry=True,
        )

    def _context_summary(self, trace: RequestTrace) -> dict[str, Any]:
        step = self._last_step(trace, "context_builder")
        output = step.output if step and isinstance(step.output, dict) else {}
        tables = []
        for table in output.get("tables", []) or []:
            tables.append(
                {
                    "name": table.get("name"),
                    "description": table.get("description"),
                    "columns": [column.get("name") for column in table.get("columns", [])],
                }
            )
        return {
            "route": output.get("route", {}),
            "tables": tables,
            "rules": output.get("rules", []) or [],
            "joins": output.get("joins", []) or [],
            "patterns": output.get("patterns", []) or [],
            "linked_columns": output.get("linked_columns", []) or [],
        }

    def _trace_steps_summary(self, trace: RequestTrace) -> list[dict[str, Any]]:
        summary = []
        for step in trace.steps[-24:]:
            summary.append(
                {
                    "name": step.name,
                    "status": step.status,
                    "error": step.error,
                    "latency_ms": step.latency_ms,
                    "output_summary": self._short_output(step.output),
                }
            )
        return summary

    def _short_output(self, output: Any) -> Any:
        if isinstance(output, dict):
            compact = {}
            for key in ["error", "columns", "execution_time", "enabled", "reason"]:
                if key in output:
                    compact[key] = output[key]
            if "rows" in output:
                compact["row_count"] = len(output.get("rows") or [])
            return compact or list(output.keys())[:8]
        if isinstance(output, list):
            return {"count": len(output), "first": output[0] if output else None}
        if isinstance(output, str):
            return output[:500]
        return output

    def _latest_sql(self, trace: RequestTrace) -> str:
        for step in reversed(trace.steps):
            if step.name.endswith("query_service") and isinstance(step.input, dict) and step.input.get("sql"):
                return str(step.input["sql"])
            if step.name.endswith("nl2sql_service") and isinstance(step.output, str):
                return step.output
        return ""

    def _latest_query_error(self, trace: RequestTrace) -> Optional[str]:
        for step in reversed(trace.steps):
            if step.name.endswith("query_service") and step.status != "skipped":
                if isinstance(step.output, dict) and step.output.get("error"):
                    return str(step.output["error"])
                if step.error:
                    return step.error
        return None

    def _latest_sanity_warning(self, trace: RequestTrace) -> Any:
        for step in reversed(trace.steps):
            if step.name.endswith("result_sanity") and step.status != "skipped":
                return step.output
        return None

    def _last_step(self, trace: RequestTrace, name: str) -> Optional[TraceStep]:
        for step in reversed(trace.steps):
            if step.name == name or step.name.endswith(f".{name}"):
                return step
        return None

    def _last_success_or_error_step(self, trace: RequestTrace, name: str) -> Optional[TraceStep]:
        for step in reversed(trace.steps):
            if (step.name == name or step.name.endswith(f".{name}")) and step.status != "skipped":
                return step
        return None
