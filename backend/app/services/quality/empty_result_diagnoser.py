"""Diagnose successful SQL queries that returned no rows."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

try:  # sqlglot is optional; the conservative regex path remains the fallback.
    import sqlglot
    from sqlglot import exp
except Exception:  # pragma: no cover - exercised when sqlglot is not installed.
    sqlglot = None
    exp = None


@dataclass
class FilterCondition:
    """A simple WHERE predicate that can be probed independently."""

    expression: str
    table: str
    column: str
    operator: str
    value: str
    alias: str = ""

    @property
    def qualified_column(self) -> str:
        return f"{self.table}.{self.column}"


@dataclass
class ProbeResult:
    """COUNT probe for one decomposed predicate."""

    condition: str
    table: str
    column: str
    probe_sql: str
    count: Optional[int] = None
    error: str = ""


@dataclass
class ValueProbeResult:
    """Candidate values found for one enum-like or value-like column."""

    table: str
    column: str
    probe_sql: str
    candidates: list[Any] = field(default_factory=list)
    search_terms: list[str] = field(default_factory=list)
    error: str = ""


@dataclass
class EmptyResultDiagnosis:
    """Structured diagnosis attached to EMPTY_RESULT reflection retries."""

    empty_result: bool = True
    suspect_conditions: list[dict[str, Any]] = field(default_factory=list)
    condition_probe_results: list[dict[str, Any]] = field(default_factory=list)
    value_probe_results: list[dict[str, Any]] = field(default_factory=list)
    diagnosis_reason: str = ""
    retry_advice: str = ""
    allow_retry: bool = True
    where_conditions: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EmptyResultDiagnoser:
    """Probe WHERE predicates before asking the LLM to repair an empty result."""

    VALUE_RESOLVER_COLUMNS = {
        "dim_material": ["color_cd", "material_type_cd"],
        "dim_material_alias": ["alias_type_cd", "alias_value"],
    }

    BUSINESS_TERM_HINTS = {
        "红色": ["红", "red"],
        "成品": ["成品", "fg", "finished"],
        "220V": ["220", "220v", "220 v"],
        "电压": ["voltage", "volt", "电压"],
    }

    def __init__(self, query_service, database_url: str = "sqlite") -> None:
        self.query_service = query_service
        self.is_sqlite = database_url.startswith("sqlite")

    def diagnose(
        self,
        *,
        question: str,
        generated_sql: str,
        selected_tables: list[str],
        schema_info: list[dict[str, Any]],
        context: Any = None,
        enable_value_resolver: bool = True,
    ) -> dict[str, Any]:
        """Return condition-level and value-level probes for an EMPTY_RESULT SQL."""
        try:
            return self._diagnose_impl(
                question=question,
                generated_sql=generated_sql,
                selected_tables=selected_tables,
                schema_info=schema_info,
                context=context,
                enable_value_resolver=enable_value_resolver,
            )
        except Exception as exc:
            return EmptyResultDiagnosis(
                diagnosis_reason="EMPTY_RESULT 诊断执行失败，回退到原 reflection 修复策略。",
                retry_advice="诊断模块异常，按原策略检查过滤条件、连接和业务规则。",
                allow_retry=True,
                errors=[str(exc)],
            ).to_dict()

    def _diagnose_impl(
        self,
        *,
        question: str,
        generated_sql: str,
        selected_tables: list[str],
        schema_info: list[dict[str, Any]],
        context: Any = None,
        enable_value_resolver: bool = True,
    ) -> dict[str, Any]:
        """Return condition-level and value-level probes for an EMPTY_RESULT SQL."""
        diagnosis = EmptyResultDiagnosis()
        schema_columns = self._schema_columns(schema_info, selected_tables)
        conditions = self.extract_conditions(generated_sql, selected_tables, schema_columns)
        diagnosis.where_conditions = [asdict(condition) for condition in conditions]

        if not conditions:
            diagnosis.diagnosis_reason = "未能安全拆解 WHERE 条件，回退到原 EMPTY_RESULT reflection 链路。"
            diagnosis.retry_advice = "无法定位具体空结果条件；按原策略检查过滤条件、连接和业务规则。"
            return diagnosis.to_dict()

        probe_results = [self._probe_condition(condition) for condition in conditions]
        diagnosis.condition_probe_results = [asdict(result) for result in probe_results]
        diagnosis.suspect_conditions = [
            asdict(conditions[index])
            for index, result in enumerate(probe_results)
            if result.count == 0 and not result.error
        ]

        if enable_value_resolver:
            value_results = self._resolve_values(question, selected_tables, schema_columns, diagnosis.suspect_conditions)
            diagnosis.value_probe_results = [asdict(result) for result in value_results]

        diagnosis.diagnosis_reason = self._build_reason(diagnosis)
        diagnosis.retry_advice = self._build_retry_advice(diagnosis)
        diagnosis.allow_retry = self._allow_retry(diagnosis)
        return diagnosis.to_dict()

    def extract_conditions(
        self,
        sql: str,
        selected_tables: list[str],
        schema_columns: dict[str, set[str]],
    ) -> list[FilterCondition]:
        """Extract simple comparison predicates from WHERE clauses."""
        alias_to_table = self._extract_aliases(sql, selected_tables)
        conditions = self._extract_conditions_with_sqlglot(sql, alias_to_table, schema_columns)
        if conditions:
            return conditions
        return self._extract_conditions_with_regex(sql, alias_to_table, schema_columns)

    def _extract_conditions_with_sqlglot(
        self,
        sql: str,
        alias_to_table: dict[str, str],
        schema_columns: dict[str, set[str]],
    ) -> list[FilterCondition]:
        if not sqlglot or not exp:
            return []
        try:
            tree = sqlglot.parse_one(sql, read="sqlite")
        except Exception:
            return []

        conditions: list[FilterCondition] = []
        operators = {
            exp.EQ: "=",
            exp.NEQ: "!=",
            exp.GT: ">",
            exp.GTE: ">=",
            exp.LT: "<",
            exp.LTE: "<=",
            exp.Like: "LIKE",
        }
        for node in tree.find_all(tuple(operators.keys())):
            left = node.left
            right = node.right
            if not isinstance(left, exp.Column):
                continue
            table_alias = left.table or ""
            table = alias_to_table.get(table_alias, table_alias)
            column = left.name
            if table not in schema_columns or column not in schema_columns[table]:
                table = self._find_table_for_column(column, schema_columns)
            if not table:
                continue
            value = right.sql(dialect="sqlite") if right is not None else ""
            conditions.append(
                FilterCondition(
                    expression=node.sql(dialect="sqlite"),
                    table=table,
                    column=column,
                    operator=operators[type(node)],
                    value=value,
                    alias=table_alias,
                )
            )
        return self._dedupe_conditions(conditions)

    def _extract_conditions_with_regex(
        self,
        sql: str,
        alias_to_table: dict[str, str],
        schema_columns: dict[str, set[str]],
    ) -> list[FilterCondition]:
        pattern = re.compile(
            r"(?P<left>(?:[A-Za-z_][\w]*\.)?[A-Za-z_][\w]*)\s*"
            r"(?P<op>=|!=|<>|<=|>=|<|>|LIKE)\s*"
            r"(?P<right>'[^']*'|\"[^\"]*\"|\d+(?:\.\d+)?)",
            re.IGNORECASE,
        )
        conditions: list[FilterCondition] = []
        for match in pattern.finditer(sql):
            left = match.group("left")
            if "." in left:
                alias, column = left.split(".", 1)
            else:
                alias, column = "", left
            table = alias_to_table.get(alias, alias)
            if table not in schema_columns or column not in schema_columns[table]:
                table = self._find_table_for_column(column, schema_columns)
            if not table:
                continue
            conditions.append(
                FilterCondition(
                    expression=match.group(0),
                    table=table,
                    column=column,
                    operator=match.group("op").upper().replace("<>", "!="),
                    value=match.group("right"),
                    alias=alias,
                )
            )
        return self._dedupe_conditions(conditions)

    def _probe_condition(self, condition: FilterCondition) -> ProbeResult:
        sql = (
            f"SELECT COUNT(*) AS probe_count FROM {self._quote_identifier(condition.table)} "
            f"WHERE {self._quote_identifier(condition.column)} {condition.operator} {condition.value}"
        )
        result = ProbeResult(
            condition=condition.expression,
            table=condition.table,
            column=condition.column,
            probe_sql=sql,
        )
        try:
            query_result = self.query_service.execute_query(sql)
        except Exception as exc:
            result.error = str(exc)
            return result
        if query_result.get("error"):
            result.error = str(query_result["error"])
            return result
        rows = query_result.get("rows") or []
        if rows:
            result.count = int(next(iter(rows[0].values())) or 0)
        else:
            result.count = 0
        return result

    def _resolve_values(
        self,
        question: str,
        selected_tables: list[str],
        schema_columns: dict[str, set[str]],
        suspect_conditions: list[dict[str, Any]],
    ) -> list[ValueProbeResult]:
        target_columns = self._target_value_columns(selected_tables, schema_columns, suspect_conditions)
        terms = self._extract_search_terms(question, suspect_conditions)
        results: list[ValueProbeResult] = []
        for table, column in target_columns:
            if column == "alias_value" and terms:
                for term in terms:
                    results.append(self._probe_like_values(table, column, term))
            else:
                results.append(self._probe_distinct_values(table, column))
        return results

    def _probe_distinct_values(self, table: str, column: str) -> ValueProbeResult:
        sql = (
            f"SELECT DISTINCT {self._quote_identifier(column)} AS candidate "
            f"FROM {self._quote_identifier(table)} "
            f"WHERE {self._quote_identifier(column)} IS NOT NULL "
            f"LIMIT 100"
        )
        return self._run_value_probe(table, column, sql, [])

    def _probe_like_values(self, table: str, column: str, term: str) -> ValueProbeResult:
        escaped = self._escape_like(term)
        if self.is_sqlite:
            predicate = (
                f"LOWER({self._quote_identifier(column)}) "
                f"LIKE LOWER('%{escaped}%') ESCAPE '\\'"
            )
        else:
            predicate = f"{self._quote_identifier(column)} ILIKE '%{escaped}%'"
        sql = (
            f"SELECT DISTINCT {self._quote_identifier(column)} AS candidate "
            f"FROM {self._quote_identifier(table)} WHERE {predicate} LIMIT 50"
        )
        return self._run_value_probe(table, column, sql, [term])

    def _run_value_probe(
        self,
        table: str,
        column: str,
        sql: str,
        search_terms: list[str],
    ) -> ValueProbeResult:
        result = ValueProbeResult(table=table, column=column, probe_sql=sql, search_terms=search_terms)
        try:
            query_result = self.query_service.execute_query(sql)
        except Exception as exc:
            result.error = str(exc)
            return result
        if query_result.get("error"):
            result.error = str(query_result["error"])
            return result
        result.candidates = [row.get("candidate") for row in query_result.get("rows", []) if row.get("candidate") is not None]
        return result

    def _target_value_columns(
        self,
        selected_tables: list[str],
        schema_columns: dict[str, set[str]],
        suspect_conditions: list[dict[str, Any]],
    ) -> list[tuple[str, str]]:
        targets: list[tuple[str, str]] = []
        for table in selected_tables:
            for column in self.VALUE_RESOLVER_COLUMNS.get(table, []):
                if column in schema_columns.get(table, set()):
                    targets.append((table, column))
        for condition in suspect_conditions:
            pair = (str(condition.get("table")), str(condition.get("column")))
            if pair[0] in schema_columns and pair[1] in schema_columns[pair[0]] and pair not in targets:
                targets.append(pair)
        return targets

    def _extract_search_terms(self, question: str, suspect_conditions: list[dict[str, Any]]) -> list[str]:
        terms: list[str] = []
        normalized_question = question.lower()
        for business_word, hints in self.BUSINESS_TERM_HINTS.items():
            if business_word.lower() in normalized_question:
                terms.extend(hints)
        for condition in suspect_conditions:
            value = str(condition.get("value", "")).strip("'\"")
            if value:
                terms.append(value)
                digit_runs = re.findall(r"\d+", value)
                terms.extend(digit_runs)
        return list(dict.fromkeys(term for term in terms if term))

    def _build_reason(self, diagnosis: EmptyResultDiagnosis) -> str:
        if diagnosis.suspect_conditions:
            conditions = ", ".join(
                f"{item['table']}.{item['column']} {item['operator']} {item['value']}"
                for item in diagnosis.suspect_conditions
            )
            return f"单条件 COUNT 为 0，疑似字段值不匹配或数据不存在：{conditions}。"
        if any(result.get("error") for result in diagnosis.condition_probe_results):
            return "部分条件探测 SQL 执行失败，保留诊断结果并回退到原 reflection 修复策略。"
        return "所有单条件 COUNT 均大于 0，空结果更可能来自条件组合、JOIN 约束或业务范围过窄。"

    def _build_retry_advice(self, diagnosis: EmptyResultDiagnosis) -> str:
        base = [
            "EMPTY_RESULT 修复时不要改变 SELECT 目标字段。",
            "不要无意义地把 JOIN 改成 IN。",
            "优先修复导致空结果的 WHERE 条件。",
            "必须使用探测到的数据库真实枚举值/候选值。",
        ]
        candidate_pairs = [
            f"{item['table']}.{item['column']}={item['candidates'][:10]}"
            for item in diagnosis.value_probe_results
            if item.get("candidates")
        ]
        if candidate_pairs:
            base.append("可用候选值：" + "; ".join(candidate_pairs))
        else:
            base.append("如果候选值无法确认，返回诊断信息而不是继续猜测。")
        return "\n".join(base)

    def _allow_retry(self, diagnosis: EmptyResultDiagnosis) -> bool:
        if not diagnosis.suspect_conditions:
            return True
        if any(item.get("candidates") for item in diagnosis.value_probe_results):
            return True
        return any(result.get("error") for result in diagnosis.condition_probe_results)

    def _extract_aliases(self, sql: str, selected_tables: list[str]) -> dict[str, str]:
        aliases = {table: table for table in selected_tables}
        table_pattern = re.compile(
            r"\b(?:FROM|JOIN)\s+([A-Za-z_][\w]*)\s*(?:AS\s+)?([A-Za-z_][\w]*)?",
            re.IGNORECASE,
        )
        for table, alias in table_pattern.findall(sql):
            if table in selected_tables:
                aliases[table] = table
                if alias and alias.upper() not in {"ON", "WHERE", "JOIN", "LEFT", "RIGHT", "INNER", "LIMIT"}:
                    aliases[alias] = table
        return aliases

    def _schema_columns(self, schema_info: list[dict[str, Any]], selected_tables: list[str]) -> dict[str, set[str]]:
        selected = set(selected_tables)
        columns: dict[str, set[str]] = {}
        for table in schema_info:
            table_name = str(table.get("table_name") or table.get("name") or "")
            if selected and table_name not in selected:
                continue
            columns[table_name] = {
                str(column.get("name"))
                for column in table.get("columns", [])
                if isinstance(column, dict) and column.get("name")
            }
        return columns

    def _find_table_for_column(self, column: str, schema_columns: dict[str, set[str]]) -> str:
        matches = [table for table, columns in schema_columns.items() if column in columns]
        return matches[0] if len(matches) == 1 else ""

    def _dedupe_conditions(self, conditions: list[FilterCondition]) -> list[FilterCondition]:
        deduped: list[FilterCondition] = []
        seen = set()
        for condition in conditions:
            key = (condition.table, condition.column, condition.operator, condition.value)
            if key not in seen:
                seen.add(key)
                deduped.append(condition)
        return deduped

    def _quote_identifier(self, identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    def _escape_like(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_").replace("'", "''")
