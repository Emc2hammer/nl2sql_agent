"""Column-level schema linking for NL2SQL questions."""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LinkedColumn:
    """A column that is semantically important for the current question."""

    table_name: str
    column_name: str
    column_type: str
    description: str
    score: int
    reason: str

    @property
    def qualified_name(self) -> str:
        return f"{self.table_name}.{self.column_name}"


COLUMN_SYNONYMS: dict[str, list[tuple[str, str, str]]] = {
    "有效订单": [
        ("code_sales_order_status", "is_valid_order", "valid order flag"),
        ("fact_sales_order_hdr", "sales_order_status_cd", "order status code"),
    ],
    "订单金额": [
        ("fact_sales_order_line", "net_amt", "order net amount"),
        ("wide_order_fulfillment_dly", "net_amt", "order net amount"),
    ],
    "销售额": [
        ("fact_sales_order_line", "net_amt", "sales amount"),
        ("wide_order_fulfillment_dly", "net_amt", "sales amount"),
    ],
    "客户细分": [
        ("dim_customer", "cust_segment_cd", "customer segment"),
        ("wide_order_fulfillment_dly", "customer_segment_cd", "customer segment"),
    ],
    "可用库存": [
        ("fact_inv_balance_snap", "on_hand_qty", "available inventory formula"),
        ("fact_inv_balance_snap", "alloc_qty", "available inventory formula"),
    ],
    "库存缺口": [
        ("fact_forecast_mth", "forecast_qty", "inventory gap formula"),
        ("fact_forecast_mth", "plant_id", "forecast grain"),
        ("fact_inv_balance_snap", "on_hand_qty", "inventory gap formula"),
        ("fact_inv_balance_snap", "alloc_qty", "inventory gap formula"),
        ("fact_inv_balance_snap", "wh_id", "inventory grain"),
        ("dim_wh", "plant_id", "align inventory to plant grain"),
    ],
    "预测量": [("fact_forecast_mth", "forecast_qty", "forecast quantity")],
    "在手": [("fact_inv_balance_snap", "on_hand_qty", "on-hand quantity")],
    "已分配": [("fact_inv_balance_snap", "alloc_qty", "allocated quantity")],
    "当前BOM": [
        ("dim_bom_hdr", "is_current_ver", "current BOM version"),
        ("dim_bom_hdr", "parent_material_id", "finished good material"),
        ("bridge_bom_component", "component_material_id", "component material"),
        ("bridge_bom_component", "component_qty", "component quantity"),
    ],
    "组件": [
        ("bridge_bom_component", "component_material_id", "component material"),
        ("bridge_bom_component", "component_qty", "component quantity"),
    ],
    "最新价格": [
        ("fact_price_book", "eff_start_dt", "latest effective date"),
        ("fact_price_book", "unit_price_amt", "unit price"),
        ("fact_price_book", "price_type_cd", "price type"),
    ],
    "产量": [
        ("fact_prod_output_dly", "good_qty", "good quantity"),
        ("fact_prod_output_dly", "scrap_qty", "scrap quantity"),
        ("wide_prod_line_hourly_board", "good_qty", "good quantity"),
    ],
    "不良": [
        ("fact_qa_inspection", "reject_qty", "rejected quantity"),
        ("fact_qa_inspection", "inspected_qty", "inspected quantity"),
        ("fact_qa_defect", "defect_qty", "defect quantity"),
    ],
    "PPM": [("fact_supplier_score_mth", "ppm_defect", "defect ppm")],
}


class ColumnLinker:
    """Rank individual columns instead of relying only on table retrieval."""

    def link(
        self,
        question: str,
        schema_info: list[dict],
        table_names: list[str],
        top_k: int = 24,
    ) -> list[LinkedColumn]:
        schema_by_name = {table["table_name"]: table for table in schema_info}
        allowed_tables = set(table_names)
        scored: dict[tuple[str, str], LinkedColumn] = {}

        for phrase, targets in COLUMN_SYNONYMS.items():
            if phrase.lower() not in question.lower():
                continue
            for table_name, column_name, reason in targets:
                if allowed_tables and table_name not in allowed_tables:
                    continue
                column = self._find_column(schema_by_name, table_name, column_name)
                if column:
                    self._add(scored, table_name, column, 30, f"{phrase} -> {reason}")

        for table_name in table_names:
            table = schema_by_name.get(table_name)
            if not table:
                continue
            for column in table.get("columns", []):
                score = self._lexical_score(question, table_name, column)
                if score:
                    self._add(scored, table_name, column, score, "lexical column match")

        return sorted(scored.values(), key=lambda item: (item.score, item.qualified_name), reverse=True)[:top_k]

    def _add(
        self,
        scored: dict[tuple[str, str], LinkedColumn],
        table_name: str,
        column: dict,
        score: int,
        reason: str,
    ) -> None:
        key = (table_name, column["name"])
        existing = scored.get(key)
        description = column.get("description", "") or ""
        item = LinkedColumn(
            table_name=table_name,
            column_name=column["name"],
            column_type=column.get("type", ""),
            description=description,
            score=(existing.score if existing else 0) + score,
            reason=reason if not existing else f"{existing.reason}; {reason}",
        )
        scored[key] = item

    def _find_column(self, schema_by_name: dict[str, dict], table_name: str, column_name: str) -> Optional[dict]:
        table = schema_by_name.get(table_name)
        if not table:
            return None
        for column in table.get("columns", []):
            if column.get("name") == column_name:
                return column
        return None

    def _lexical_score(self, question: str, table_name: str, column: dict) -> int:
        text = f"{table_name} {column.get('name', '')} {column.get('description', '')}".lower()
        score = 0
        for term in re.findall(r"[A-Za-z0-9_]+", question.lower()):
            if len(term) > 1 and term in text:
                score += 4
        for token in ["订单", "客户", "物料", "库存", "预测", "价格", "生产", "检验", "供应商", "售后", "日期", "数量", "金额"]:
            if token in question and token in text:
                score += 3
        column_name = column.get("name", "")
        if column_name.endswith(("_id", "_cd", "_key")) and any(k in question for k in ["哪个", "哪些", "列出", "显示", "按"]):
            score += 1
        return score
