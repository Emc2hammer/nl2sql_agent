"""Semantic checks for executable but business-wrong SQL."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticIssue:
    severity: str
    code: str
    message: str


class SQLSemanticVerifier:
    """Catch common NL2SQL semantic failures before execution."""

    def verify(self, question: str, sql: str, schema_info: list[dict]) -> list[SemanticIssue]:
        issues: list[SemanticIssue] = []
        lowered_sql = sql.lower()
        aliases = self._extract_aliases(sql)

        issues.extend(self._check_schema_references(sql, schema_info, aliases))

        if "有效订单" in question and "is_valid_order" not in lowered_sql:
            issues.append(SemanticIssue("error", "missing_valid_order_rule", "问题要求有效订单，但 SQL 未使用 is_valid_order 规则。"))

        if ("当前bom" in question.lower() or "当前 BOM".lower() in question.lower()) and "is_current_ver" not in lowered_sql:
            issues.append(SemanticIssue("error", "missing_current_bom_rule", "问题要求当前 BOM，但 SQL 未过滤 is_current_ver = 1。"))

        if ("可用库存" in question or "库存缺口" in question) and not ("on_hand_qty" in lowered_sql and "alloc_qty" in lowered_sql):
            issues.append(SemanticIssue("error", "missing_available_inventory_formula", "问题涉及可用库存，但 SQL 未使用 on_hand_qty - alloc_qty。"))

        if "库存缺口" in question and self._has_direct_inventory_fact_join(lowered_sql):
            issues.append(
                SemanticIssue(
                    "error",
                    "inventory_grain_mismatch",
                    "库存缺口需要按 material_id + plant_id 对预测和库存分别聚合；当前 SQL 可能直接按 material_id 连接两个事实表，存在粒度错误。",
                )
            )

        if "最新" in question and "价格" in question and "eff_start_dt" not in lowered_sql:
            issues.append(SemanticIssue("warning", "missing_latest_price_date", "最新价格通常需要使用 eff_start_dt 选择目标日期前最近记录。"))

        if any(k in question for k in ["每个", "各", "分别"]) and any(k in question for k in ["最高", "最大", "前"]):
            if "limit" in lowered_sql and "partition by" not in lowered_sql:
                issues.append(SemanticIssue("warning", "global_limit_for_group_topn", "问题像是每组 TopN，但 SQL 使用了全局 LIMIT，可能不是每组排名。"))

        return issues

    def has_blocking_issue(self, issues: list[SemanticIssue]) -> bool:
        return any(issue.severity == "error" for issue in issues)

    def format_issues(self, issues: list[SemanticIssue]) -> str:
        if not issues:
            return "No semantic issues."
        return "\n".join(f"- {issue.severity.upper()} {issue.code}: {issue.message}" for issue in issues)

    def _extract_aliases(self, sql: str) -> dict[str, str]:
        aliases: dict[str, str] = {}
        pattern = re.compile(r"\b(?:from|join)\s+([A-Za-z_][\w]*)\s*(?:as\s+)?([A-Za-z_][\w]*)?", re.IGNORECASE)
        for table_name, alias in pattern.findall(sql):
            aliases[table_name] = table_name
            if alias and alias.lower() not in {"on", "where", "join", "left", "inner", "right", "full", "cross"}:
                aliases[alias] = table_name
        return aliases

    def _check_schema_references(self, sql: str, schema_info: list[dict], aliases: dict[str, str]) -> list[SemanticIssue]:
        schema = {
            table["table_name"].lower(): {column["name"].lower() for column in table.get("columns", [])}
            for table in schema_info
        }
        issues: list[SemanticIssue] = []
        for alias, column in re.findall(r"\b([A-Za-z_][\w]*)\.([A-Za-z_][\w]*)\b", sql):
            table_name = aliases.get(alias, alias)
            table_key = table_name.lower()
            if table_key not in schema:
                continue
            if column.lower() not in schema[table_key]:
                issues.append(SemanticIssue("error", "unknown_column", f"{table_name}.{column} 不存在。"))
        return issues

    def _has_direct_inventory_fact_join(self, lowered_sql: str) -> bool:
        has_forecast = "fact_forecast_mth" in lowered_sql
        has_inventory = "fact_inv_balance_snap" in lowered_sql
        if not (has_forecast and has_inventory):
            return False
        has_plant_alignment = "dim_wh" in lowered_sql or "plant_id" in lowered_sql
        has_pre_aggregation = "with" in lowered_sql or "group by" in lowered_sql
        return not (has_plant_alignment and has_pre_aggregation)
