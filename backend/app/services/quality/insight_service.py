"""Deterministic insight generation from SQL result rows."""

from __future__ import annotations

from typing import Any


class InsightService:
    """Generate small, domain-aware insights without another LLM call."""

    COMPONENT_NAME_COLUMNS = {"component_material_id", "component_name"}
    COMPONENT_QTY_COLUMNS = {"component_qty_per_unit", "component_qty"}

    def generate(
        self,
        rows: list[dict[str, Any]],
        columns: list[str],
        max_items: int = 3,
        question: str | None = None,
    ) -> list[str]:
        if not rows:
            return ["\u67e5\u8be2\u7ed3\u679c\u4e3a\u7a7a\u3002"]

        if len(rows) == 1 and len(columns) == 1:
            column = columns[0]
            return [f"\u67e5\u8be2\u7ed3\u679c\uff1a{column} = {self._fmt_value(rows[0].get(column))}"]

        if self._is_bom_component_analysis(columns):
            return self._bom_component_insights(rows, columns, max_items)

        if not self._is_ranking_or_comparison_query(question, columns):
            return [f"\u67e5\u8be2\u8fd4\u56de {len(rows)} \u884c\u7ed3\u679c\u3002"]

        return self._ranking_insights(rows, columns, max_items)

    def _is_bom_component_analysis(self, columns: list[str]) -> bool:
        normalized = {column.lower() for column in columns}
        has_component = bool(normalized & self.COMPONENT_NAME_COLUMNS)
        has_quantity = bool(normalized & self.COMPONENT_QTY_COLUMNS)
        return has_component and has_quantity

    def _bom_component_insights(
        self,
        rows: list[dict[str, Any]],
        columns: list[str],
        max_items: int,
    ) -> list[str]:
        name_col = self._preferred_column(columns, ["component_name", "component_material_id"])
        qty_col = self._preferred_column(columns, ["component_qty_per_unit", "component_qty"])
        quantities = [
            row.get(qty_col)
            for row in rows
            if qty_col and isinstance(row.get(qty_col), (int, float))
        ]

        component_count = len(rows)
        total_qty = sum(quantities)
        insights = [
            "\u5f53\u524d BOM \u5171\u5305\u542b "
            f"{component_count} "
            "\u7c7b\u7ec4\u4ef6\uff0c\u6bcf\u751f\u4ea7 1 \u53f0\u9700\u8981\u7ec4\u4ef6\u603b\u7528\u91cf "
            f"{self._fmt(total_qty)} \u4e2a\u3002"
        ]

        if quantities and len(set(quantities)) == 1:
            insights.append(
                "\u5404\u7ec4\u4ef6\u7528\u91cf\u4e00\u81f4\uff0c\u5747\u4e3a "
                f"{self._fmt(quantities[0])} "
                "\u4e2a/\u53f0\u3002"
            )
        elif quantities and name_col:
            max_row = max(
                (row for row in rows if isinstance(row.get(qty_col), (int, float))),
                key=lambda row: row.get(qty_col),
            )
            insights.append(
                "\u6700\u5927\u7528\u91cf\u7ec4\u4ef6\u4e3a "
                f"{max_row.get(name_col)}"
                "\uff0c\u7528\u91cf "
                f"{self._fmt(max_row.get(qty_col))} "
                "\u4e2a/\u53f0\u3002"
            )

        if name_col:
            names = [str(row.get(name_col)) for row in rows if row.get(name_col) not in (None, "")]
            if names:
                insights.append("\u7ec4\u4ef6\u5305\u62ec\uff1a" + "\u3001".join(names) + "\u3002")

        return insights[:max_items]

    def _ranking_insights(self, rows: list[dict[str, Any]], columns: list[str], max_items: int) -> list[str]:
        numeric_columns = [
            column
            for column in columns
            if any(isinstance(row.get(column), (int, float)) for row in rows)
        ]
        if not numeric_columns:
            return [f"\u67e5\u8be2\u8fd4\u56de {len(rows)} \u884c\u7ed3\u679c\u3002"]

        metric = numeric_columns[-1]
        values = [(row, row.get(metric)) for row in rows if isinstance(row.get(metric), (int, float))]
        if not values:
            return [f"\u67e5\u8be2\u8fd4\u56de {len(rows)} \u884c\u7ed3\u679c\u3002"]

        sorted_values = sorted(values, key=lambda item: item[1], reverse=True)
        top_row, top_value = sorted_values[0]
        label = self._row_label(top_row, columns, metric)

        insights = [f"{label} \u5728 {metric} \u4e0a\u6700\u9ad8\uff0c\u4e3a {self._fmt(top_value)}\u3002"]
        if len(sorted_values) > 1:
            second_value = sorted_values[1][1]
            insights.append(f"\u9886\u5148\u7b2c\u4e8c\u540d {self._fmt(top_value - second_value)}\u3002")

        total = sum(value for _, value in values)
        if total > 0:
            share = top_value / total * 100
            insights.append(f"\u6700\u9ad8\u503c\u5360 {metric} \u603b\u91cf\u7684 {share:.1f}%\u3002")

        return insights[:max_items]

    def _is_ranking_or_comparison_query(self, question: str | None, columns: list[str]) -> bool:
        q = (question or "").lower()
        ranking_terms = [
            "top",
            "rank",
            "ranking",
            "highest",
            "lowest",
            "compare",
            "comparison",
            "\u524d",
            "\u6392\u540d",
            "\u6392\u884c",
            "\u6700\u9ad8",
            "\u6700\u4f4e",
            "\u6700\u5927",
            "\u6700\u5c0f",
            "\u5bf9\u6bd4",
            "\u6bd4\u8f83",
        ]
        if any(term in q for term in ranking_terms):
            return True

        normalized_columns = {column.lower() for column in columns}
        return any(
            token in column
            for column in normalized_columns
            for token in ["rank", "ranking", "top_n", "rn"]
        )

    def _first_matching_column(self, columns: list[str], candidates: set[str]) -> str | None:
        for column in columns:
            if column.lower() in candidates:
                return column
        return None

    def _preferred_column(self, columns: list[str], candidates: list[str]) -> str | None:
        normalized = {column.lower(): column for column in columns}
        for candidate in candidates:
            if candidate in normalized:
                return normalized[candidate]
        return None

    def _row_label(self, row: dict[str, Any], columns: list[str], metric: str) -> str:
        for column in columns:
            if column == metric:
                continue
            value = row.get(column)
            if value not in (None, ""):
                return f"{column}={value}"
        return "\u5f53\u524d\u7ed3\u679c"

    def _fmt(self, value: float) -> str:
        if isinstance(value, int) or float(value).is_integer():
            return str(int(value))
        return f"{value:.4f}".rstrip("0").rstrip(".")

    def _fmt_value(self, value: Any) -> str:
        if isinstance(value, (int, float)):
            return self._fmt(value)
        return str(value)
