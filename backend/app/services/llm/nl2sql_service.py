"""NL2SQL service using compact routed context."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import time
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.prompts.nl2sql_prompt import PLAN_PROMPT_TEMPLATE, REPAIR_PROMPT_TEMPLATE, SYSTEM_PROMPT_TEMPLATE
from app.services.routing.context_builder import NL2SQLContext


class NL2SQLService:
    """Convert natural language questions to SQL via SiliconFlow API."""

    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.llm_model_name,
            openai_api_key=settings.siliconflow_api_key,
            openai_api_base=settings.siliconflow_base_url,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            request_timeout=settings.llm_request_timeout,
        )

    def generate_sql(
        self,
        question: str,
        context: NL2SQLContext,
        examples: Optional[list[dict]] = None,
        negative_examples: Optional[list[dict]] = None,
        query_plan: Optional[str] = None,
    ) -> str:
        """Convert a natural language question to a SQL query."""
        system_msg = SYSTEM_PROMPT_TEMPLATE.format(
            question=question,
            domain=context.route.domain,
            route_keywords=", ".join(context.route.matched_keywords) or "none",
            business_rules=self._format_rules(context),
            column_links=self._format_column_links(context),
            schema_info=self._format_tables(context),
            join_paths=self._format_joins(context),
            sql_patterns=self._format_patterns(context),
            query_plan=self._format_plan(query_plan),
            examples=self._format_examples(examples),
            negative_examples=self._format_negative_examples(negative_examples),
        )

        response = self._invoke_llm(
            [
                SystemMessage(content=system_msg),
                HumanMessage(content=question),
            ]
        )
        return self._clean_sql(response.content)

    def generate_plan(self, question: str, context: NL2SQLContext) -> str:
        """Generate a short query plan for hard questions."""
        system_msg = PLAN_PROMPT_TEMPLATE.format(
            question=question,
            domain=context.route.domain,
            business_rules=self._format_rules(context),
            column_links=self._format_column_links(context),
            schema_info=self._format_tables(context),
            join_paths=self._format_joins(context),
            sql_patterns=self._format_patterns(context),
        )
        response = self._invoke_llm([SystemMessage(content=system_msg)])
        return response.content.strip()

    def repair_sql(
        self,
        question: str,
        context: NL2SQLContext,
        failed_sql: str,
        error: str,
    ) -> str:
        """Ask the LLM to repair a SQL query using the same compact context."""
        system_msg = REPAIR_PROMPT_TEMPLATE.format(
            question=question,
            domain=context.route.domain,
            business_rules=self._format_rules(context),
            column_links=self._format_column_links(context),
            schema_info=self._format_tables(context),
            join_paths=self._format_joins(context),
            sql_patterns=self._format_patterns(context),
            failed_sql=failed_sql,
            error=error,
        )
        response = self._invoke_llm([SystemMessage(content=system_msg)])
        return self._clean_sql(response.content)

    def _invoke_llm(self, messages):
        """Invoke the LLM with a hard in-process timeout and transient retries."""
        attempts = max(1, settings.llm_retry_attempts)
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return self._invoke_llm_once(messages)
            except Exception as exc:
                last_error = exc
                if attempt >= attempts or not self._is_transient_llm_error(exc):
                    raise
                time.sleep(settings.llm_retry_backoff_seconds * attempt)
        raise last_error or RuntimeError("NL2SQL LLM invocation failed.")

    def _invoke_llm_once(self, messages):
        """Invoke the LLM once with a hard in-process timeout."""
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nl2sql-llm")
        future = executor.submit(self.llm.invoke, messages)
        try:
            return future.result(timeout=settings.llm_request_timeout)
        except FutureTimeoutError as exc:
            future.cancel()
            raise TimeoutError(
                f"NL2SQL LLM request exceeded {settings.llm_request_timeout}s timeout."
            ) from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _is_transient_llm_error(self, exc: Exception) -> bool:
        text = str(exc).lower()
        transient_markers = [
            "503",
            "502",
            "504",
            "500",
            "429",
            "system is really busy",
            "rate limit",
            "timeout",
            "temporarily",
            "try again later",
        ]
        return any(marker in text for marker in transient_markers)

    def _format_tables(self, context: NL2SQLContext) -> str:
        lines = []
        for table in context.tables:
            lines.append(f"Table: {table.name}")
            if table.description:
                lines.append(f"Description: {table.description}")
            lines.append("Columns:")
            for col in table.columns:
                pk = " PK" if col.primary_key else ""
                nullable = "" if col.nullable else " NOT NULL"
                desc = f" - {col.description}" if col.description else ""
                lines.append(f"  - {col.name} ({col.type}{pk}{nullable}){desc}")
            if table.sample_rows:
                lines.append(f"Sample rows: {table.sample_rows[:2]}")
            lines.append("")
        return "\n".join(lines).strip()

    def _format_joins(self, context: NL2SQLContext) -> str:
        if not context.joins:
            return "No explicit join paths were retrieved."
        return "\n".join(f"- {join.as_sql_hint()}" for join in context.joins)

    def _format_column_links(self, context: NL2SQLContext) -> str:
        if not context.linked_columns:
            return "- No explicit column links matched."
        lines = []
        for column in context.linked_columns[:24]:
            desc = f" - {column.description}" if column.description else ""
            lines.append(f"- {column.qualified_name} ({column.column_type}): {column.reason}{desc}")
        return "\n".join(lines)

    def _format_rules(self, context: NL2SQLContext) -> str:
        if not context.rules:
            return "- No special business rules matched. Still use date keys and code tables carefully."

        lines = []
        for rule in context.rules:
            lines.append(f"- {rule.name}: {rule.condition}")
            if rule.required_joins:
                lines.append(f"  Required joins: {'; '.join(rule.required_joins)}")
            if rule.note:
                lines.append(f"  Note: {rule.note}")
        return "\n".join(lines)

    def _format_patterns(self, context: NL2SQLContext) -> str:
        if not context.patterns:
            return "- No special SQL pattern matched."

        lines = []
        for pattern in context.patterns:
            lines.append(f"- {pattern.name}: {pattern.description}")
            if pattern.template_hint:
                lines.append(f"  Hint: {pattern.template_hint}")
        return "\n".join(lines)

    def _format_examples(self, examples: Optional[list[dict]]) -> str:
        if not examples:
            return ""
        lines = ["## Relevant Examples And Semantic Context"]
        for i, ex in enumerate(examples, 1):
            context_type = ex.get("context_type") or ex.get("type") or "few_shot"
            lines.append(f"Item {i} ({context_type}):")
            if ex.get("question"):
                lines.append(f"Question: {ex.get('question', '')}")
            if ex.get("sql"):
                lines.append(f"SQL: {ex.get('sql', '')}")
            elif ex.get("text") or ex.get("content"):
                lines.append(f"Context: {ex.get('text') or ex.get('content') or ''}")
        return "\n".join(lines)

    def _format_negative_examples(self, examples: Optional[list[dict]]) -> str:
        if not examples:
            return ""
        lines = [
            "## Negative Examples",
            "The following historical failures are similar to the current request. Do not repeat these mistakes.",
        ]
        for i, ex in enumerate(examples, 1):
            lines.append(f"Failure {i}:")
            lines.append(f"Question: {ex.get('question', '')}")
            lines.append(f"Bad SQL: {ex.get('generated_sql', '')}")
            lines.append(f"Error Type: {ex.get('error_type', 'UNKNOWN')}")
            lines.append(f"Lesson: {ex.get('lesson', '')}")
            corrected_sql = ex.get("corrected_sql")
            if corrected_sql:
                lines.append(f"Corrected SQL: {corrected_sql}")
        return "\n".join(lines)

    def _format_plan(self, query_plan: Optional[str]) -> str:
        if not query_plan:
            return ""
        return f"## Query Plan\n{query_plan}"

    def _clean_sql(self, content: str) -> str:
        sql = content.strip()
        if sql.startswith("```sql"):
            sql = sql[6:]
        elif sql.startswith("```"):
            sql = sql[3:]
        if sql.endswith("```"):
            sql = sql[:-3]
        return sql.strip()
