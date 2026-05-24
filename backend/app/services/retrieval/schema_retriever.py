"""Retrieve a compact set of relevant tables and fields for a question."""

import re
from dataclasses import dataclass
from typing import Optional

from app.services.retrieval.schema_indexer import SchemaIndex


@dataclass
class RetrievedColumn:
    """A relevant column selected for prompt context."""

    name: str
    type: str
    description: str
    primary_key: bool = False
    nullable: bool = True


@dataclass
class RetrievedTable:
    """A relevant table selected for prompt context."""

    name: str
    description: str
    score: int
    columns: list[RetrievedColumn]
    sample_rows: list[dict]


CORE_COLUMNS: dict[str, list[str]] = {
    "fact_sales_order_hdr": ["sales_order_id", "customer_id", "sales_order_status_cd", "order_date_key"],
    "fact_sales_order_line": ["sales_order_line_id", "sales_order_id", "material_id", "order_qty", "net_amt"],
    "wide_order_fulfillment_dly": [
        "sales_order_id",
        "sales_order_line_id",
        "order_date_key",
        "customer_id",
        "customer_segment_cd",
        "order_qty",
        "net_amt",
        "order_status_cd",
        "delivery_risk_cd",
    ],
    "dim_customer": ["customer_id", "customer_nm", "cust_segment_cd", "region_cd"],
    "dim_material": [
        "material_id",
        "material_sku",
        "material_nm",
        "prod_family_cd",
        "material_type_cd",
        "voltage_level",
        "color_cd",
    ],
    "code_sales_order_status": ["sales_order_status_cd", "sales_order_status_nm", "is_valid_order"],
}


class SchemaRetriever:
    """Lexical table and field retriever with domain narrowing."""

    def __init__(self, schema_index: Optional[SchemaIndex] = None) -> None:
        self.schema_index = schema_index or SchemaIndex()

    def retrieve(
        self,
        question: str,
        domain: str,
        schema_info: list[dict],
        top_k: int = 6,
        max_columns_per_table: int = 12,
        preferred_columns: Optional[list[str]] = None,
    ) -> list[RetrievedTable]:
        schema_by_name = {table["table_name"]: table for table in schema_info}
        candidate_names = [
            name for name in self.schema_index.candidate_tables(domain)
            if name in schema_by_name
        ]
        if not candidate_names:
            candidate_names = list(schema_by_name)

        scored = []
        for table_name in candidate_names:
            table_doc = self.schema_index.tables.get(table_name)
            score = self._score_table(question, table_name)
            if table_doc:
                score += self._score_text(question, table_doc.search_text)
            scored.append((score, table_name))

        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        selected_names = [name for _, name in scored[:top_k]]

        return [
            self._build_table(question, schema_by_name[name], max_columns_per_table, preferred_columns or [])
            for name in selected_names
        ]

    def _build_table(
        self,
        question: str,
        table_info: dict,
        max_columns_per_table: int,
        preferred_columns: list[str],
    ) -> RetrievedTable:
        table_name = table_info["table_name"]
        table_doc = self.schema_index.tables.get(table_name)
        descriptions = table_doc.columns if table_doc else {}
        selected_columns = self._select_columns(
            question,
            table_name,
            table_info["columns"],
            descriptions,
            max_columns=max_columns_per_table,
            preferred_columns=preferred_columns,
        )
        selected_names = {col.name for col in selected_columns}

        return RetrievedTable(
            name=table_name,
            description=table_doc.description if table_doc else "",
            score=self._score_table(question, table_name),
            columns=selected_columns,
            sample_rows=[
                {key: value for key, value in row.items() if key in selected_names}
                for row in table_info.get("sample_rows", [])[:2]
            ],
        )

    def _select_columns(
        self,
        question: str,
        table_name: str,
        columns: list[dict],
        descriptions: dict,
        max_columns: int = 12,
        preferred_columns: Optional[list[str]] = None,
    ) -> list[RetrievedColumn]:
        core = set(CORE_COLUMNS.get(table_name, []))
        preferred = set(preferred_columns or [])
        scored = []
        for col in columns:
            col_name = col["name"]
            desc = descriptions.get(col_name).description if col_name in descriptions else ""
            score = self._score_text(question, f"{col_name} {desc}")
            if f"{table_name}.{col_name}" in preferred:
                score += 50
            if col.get("primary_key"):
                score += 3
            if col_name in core:
                score += 6
            if col_name.endswith("_id") or col_name.endswith("_cd") or col_name.endswith("_key"):
                score += 1
            scored.append((score, col, desc))

        scored.sort(key=lambda item: (item[0], item[1]["name"]), reverse=True)
        selected = scored[:max_columns]

        return [
            RetrievedColumn(
                name=col["name"],
                type=col["type"],
                description=desc,
                primary_key=bool(col.get("primary_key")),
                nullable=bool(col.get("nullable", True)),
            )
            for _, col, desc in selected
        ]

    def _score_table(self, question: str, table_name: str) -> int:
        score = 0
        q = question.lower()
        if "订单" in question and "order" in table_name:
            score += 5
        if "客户" in question and "customer" in table_name:
            score += 5
        if "物料" in question or "成品" in question:
            if "material" in table_name or "bom" in table_name:
                score += 5
        if "库存" in question and ("inv" in table_name or "forecast" in table_name):
            score += 5
        if "生产" in question or "产量" in question or "oee" in q:
            if "prod" in table_name or "work_order" in table_name:
                score += 5
        if "供应商" in question or "采购" in question:
            if "supplier" in table_name or "po_" in table_name:
                score += 5
        if "售后" in question and "after_sale" in table_name:
            score += 8
        if table_name.startswith("wide_"):
            score += 2
        return score

    def _score_text(self, question: str, text: str) -> int:
        score = 0
        q_terms = set(re.findall(r"[A-Za-z0-9_]+", question.lower()))
        for term in q_terms:
            if len(term) > 1 and term in text:
                score += 2
        for token in self._chinese_terms(question):
            if token and token in text:
                score += 3
        return score

    def _chinese_terms(self, question: str) -> list[str]:
        terms = []
        for term in [
            "有效订单",
            "客户细分",
            "订单",
            "客户",
            "销售",
            "金额",
            "物料",
            "成品",
            "组件",
            "库存",
            "生产线",
            "产量",
            "供应商",
            "检验",
            "不良",
            "售后",
            "风险",
            "交付",
        ]:
            if term in question:
                terms.append(term)
        return terms
