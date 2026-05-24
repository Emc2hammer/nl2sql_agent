"""Field-level semantic retrieval for schema routing."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from app.services.retrieval.schema_indexer import SchemaIndex


@dataclass(frozen=True)
class FieldScore:
    """One scored field candidate."""

    table_name: str
    column_name: str
    qualified_name: str
    score: int
    priority: str
    semantic_text: str
    reasons: list[str] = field(default_factory=list)


@dataclass
class FieldRetrievalResult:
    """Field-first schema retrieval result."""

    selected_tables: list[str]
    selected_columns: list[str]
    column_scores: list[dict[str, Any]]
    routing_reason: list[str]
    why_alias_table_selected: str = ""
    why_main_table_field_rejected: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FieldSemanticRetriever:
    """Rank columns before selecting tables so specific business fields win."""

    ALIAS_TRIGGERS = {"别名", "多语言", "属性扩展", "自定义属性", "attribute", "alias"}
    ATTRIBUTE_TRIGGERS = {"属性扩展", "自定义属性", "attribute", "扩展属性", "eav"}
    BOM_TRIGGERS = {"bom", "BOM", "组件", "配方", "父子物料", "用量", "原材料"}

    BUSINESS_FIELD_HINTS: dict[str, list[tuple[str, str, int, str]]] = {
        "电压": [
            ("dim_material", "voltage_level", 80, "用户提到电压，主表存在直接业务字段"),
            ("dim_material_alias", "alias_value", 18, "alias 泛化字段可表达电压值，但优先级较低"),
            ("eav_material_attr", "attr_value", 10, "EAV 扩展字段可表达电压值，但优先级最低"),
        ],
        "220v": [
            ("dim_material", "voltage_level", 50, "用户提到 220V，优先匹配电压等级字段"),
            ("dim_material_alias", "alias_value", 15, "alias 泛化值弱匹配 220V"),
        ],
        "颜色": [("dim_material", "color_cd", 80, "用户提到颜色，主表存在颜色编码字段")],
        "红色": [("dim_material", "color_cd", 50, "用户提到红色，匹配颜色编码字段")],
        "编码": [("dim_material", "material_sku", 70, "用户要求返回物料编码")],
        "名称": [("dim_material", "material_nm", 70, "用户要求返回物料名称")],
        "成品": [("dim_material", "material_type_cd", 55, "用户提到成品，匹配物料类型字段")],
        "sku": [("dim_material", "material_sku", 60, "用户提到 SKU/编码")],
    }

    SEMANTIC_TEXT_OVERRIDES: dict[tuple[str, str], str] = {
        ("dim_material", "voltage_level"): "物料电压等级 电压 220V 110V voltage level volt",
        ("dim_material", "color_cd"): "物料颜色 颜色 红色 蓝色 color red blue",
        ("dim_material", "material_sku"): "物料编码 SKU 编码 material code sku",
        ("dim_material", "material_nm"): "物料名称 名称 name material name",
        ("dim_material", "material_type_cd"): "物料类型 成品 FG finished goods material type",
        ("dim_material_alias", "alias_value"): "物料别名值 alias value 多语言 泛化属性",
        ("dim_material_alias", "alias_type_cd"): "物料别名类型 alias type 多语言 泛化属性",
        ("eav_material_attr", "attr_value"): "物料扩展属性值 attribute value 自定义属性",
        ("bridge_bom_component", "component_material_id"): "BOM 组件 子物料 原材料 component",
        ("bridge_bom_component", "component_qty"): "BOM 组件用量 配方 用量 quantity",
    }

    CORE_OUTPUT_COLUMNS = {
        "dim_material.material_id",
        "dim_material.material_sku",
        "dim_material.material_nm",
    }

    def __init__(self, schema_index: SchemaIndex | None = None) -> None:
        self.schema_index = schema_index or SchemaIndex()

    def retrieve(
        self,
        question: str,
        schema_info: list[dict[str, Any]],
        domain: str,
        top_k: int = 16,
    ) -> FieldRetrievalResult:
        alias_allowed = self._has_any(question, self.ALIAS_TRIGGERS)
        attr_allowed = self._has_any(question, self.ATTRIBUTE_TRIGGERS)
        bom_allowed = self._has_any(question, self.BOM_TRIGGERS)
        schema_by_name = {table["table_name"]: table for table in schema_info}
        candidate_tables = [
            table_name for table_name in self.schema_index.candidate_tables(domain)
            if table_name in schema_by_name
        ] or list(schema_by_name)

        scored: dict[tuple[str, str], FieldScore] = {}
        for table_name in candidate_tables:
            if table_name == "dim_material_alias" and not alias_allowed:
                continue
            if table_name == "eav_material_attr" and not attr_allowed:
                continue
            if table_name in {"bridge_bom_component", "dim_bom_hdr"} and not bom_allowed:
                continue
            for column in schema_by_name[table_name].get("columns", []):
                field_score = self._score_field(question, schema_by_name[table_name], column)
                if field_score.score > 0:
                    scored[(table_name, column["name"])] = field_score

        for field_score in self._hint_scores(question, schema_by_name, alias_allowed, attr_allowed, bom_allowed):
            key = (field_score.table_name, field_score.column_name)
            existing = scored.get(key)
            if existing:
                scored[key] = FieldScore(
                    table_name=existing.table_name,
                    column_name=existing.column_name,
                    qualified_name=existing.qualified_name,
                    score=existing.score + field_score.score,
                    priority=existing.priority,
                    semantic_text=existing.semantic_text,
                    reasons=existing.reasons + field_score.reasons,
                )
            else:
                scored[key] = field_score

        ranked = sorted(scored.values(), key=lambda item: (item.score, self._priority_rank(item), item.qualified_name), reverse=True)
        selected = self._select_columns(question, ranked, top_k)
        selected_tables = self._select_tables(selected)
        reasons = self._routing_reasons(question, selected, alias_allowed, attr_allowed, bom_allowed)

        alias_reason = ""
        if "dim_material_alias" in selected_tables:
            alias_reason = "alias/property trigger appeared in question, so alias table was allowed."
        elif "dim_material_alias" in candidate_tables:
            alias_reason = "dim_material_alias suppressed: no alias/multilingual/custom-attribute trigger and direct material fields matched."

        return FieldRetrievalResult(
            selected_tables=selected_tables,
            selected_columns=[item.qualified_name for item in selected],
            column_scores=[asdict(item) for item in ranked[:top_k]],
            routing_reason=reasons,
            why_alias_table_selected=alias_reason,
            why_main_table_field_rejected="",
        )

    def _score_field(self, question: str, table: dict[str, Any], column: dict[str, Any]) -> FieldScore:
        table_name = table["table_name"]
        column_name = column["name"]
        semantic_text = self._semantic_text(table_name, column_name, column, table.get("sample_rows", []))
        score = 0
        reasons: list[str] = []
        q = question.lower()

        for term in re.findall(r"[A-Za-z0-9_]+", q):
            if len(term) > 1 and term in semantic_text.lower():
                score += 6
                reasons.append(f"lexical:{term}")
        for token in self._chinese_tokens(question):
            if token in semantic_text:
                score += 12
                reasons.append(f"semantic:{token}")

        priority = self._priority(table_name, column_name)
        if score > 0:
            score += self._priority_bonus(priority)
        return FieldScore(table_name, column_name, f"{table_name}.{column_name}", score, priority, semantic_text, reasons)

    def _hint_scores(
        self,
        question: str,
        schema_by_name: dict[str, dict[str, Any]],
        alias_allowed: bool,
        attr_allowed: bool,
        bom_allowed: bool,
    ) -> list[FieldScore]:
        q = question.lower()
        results: list[FieldScore] = []
        for token, targets in self.BUSINESS_FIELD_HINTS.items():
            if token.lower() not in q:
                continue
            for table_name, column_name, score, reason in targets:
                if table_name == "dim_material_alias" and not alias_allowed:
                    continue
                if table_name == "eav_material_attr" and not attr_allowed:
                    continue
                if table_name.startswith("bridge_bom") and not bom_allowed:
                    continue
                table = schema_by_name.get(table_name)
                column = self._find_column(table, column_name) if table else None
                if not column:
                    continue
                priority = self._priority(table_name, column_name)
                results.append(
                    FieldScore(
                        table_name=table_name,
                        column_name=column_name,
                        qualified_name=f"{table_name}.{column_name}",
                        score=score + self._priority_bonus(priority),
                        priority=priority,
                        semantic_text=self._semantic_text(table_name, column_name, column, table.get("sample_rows", [])),
                        reasons=[reason],
                    )
                )
        return results

    def _select_columns(self, question: str, ranked: list[FieldScore], top_k: int) -> list[FieldScore]:
        selected = [item for item in ranked if item.score >= 20][:top_k]
        if self._is_direct_material_attribute_lookup(question, selected):
            selected = [item for item in selected if item.table_name == "dim_material"]
        selected_names = {item.qualified_name for item in selected}
        by_name = {item.qualified_name: item for item in ranked}
        if any(name.startswith("dim_material.") for name in selected_names):
            for qualified_name in self.CORE_OUTPUT_COLUMNS:
                if qualified_name in by_name and qualified_name not in selected_names:
                    selected.append(by_name[qualified_name])
                    selected_names.add(qualified_name)
        return selected[:top_k]

    def _is_direct_material_attribute_lookup(self, question: str, selected: list[FieldScore]) -> bool:
        if self._has_any(question, self.ALIAS_TRIGGERS | self.ATTRIBUTE_TRIGGERS | self.BOM_TRIGGERS):
            return False
        selected_names = {item.qualified_name for item in selected}
        direct_filters = {
            "dim_material.voltage_level",
            "dim_material.color_cd",
        }
        direct_outputs = {
            "dim_material.material_sku",
            "dim_material.material_nm",
        }
        return bool(selected_names & direct_filters) and bool(selected_names & direct_outputs)

    def _select_tables(self, selected: list[FieldScore]) -> list[str]:
        tables: list[str] = []
        for item in selected:
            if item.table_name not in tables:
                tables.append(item.table_name)
        return tables

    def _routing_reasons(
        self,
        question: str,
        selected: list[FieldScore],
        alias_allowed: bool,
        attr_allowed: bool,
        bom_allowed: bool,
    ) -> list[str]:
        reasons = [f"{item.qualified_name}: {', '.join(item.reasons) or item.priority}" for item in selected[:10]]
        if not alias_allowed:
            reasons.append("alias/property table suppressed because no alias/multilingual/custom attribute trigger was present.")
        if not attr_allowed:
            reasons.append("EAV extension table suppressed because no custom attribute trigger was present.")
        if not bom_allowed:
            reasons.append("BOM bridge suppressed because no BOM/component/formula/raw-material trigger was present.")
        return reasons

    def _semantic_text(
        self,
        table_name: str,
        column_name: str,
        column: dict[str, Any],
        sample_rows: list[dict[str, Any]],
    ) -> str:
        table_doc = self.schema_index.tables.get(table_name)
        comment = ""
        if table_doc and column_name in table_doc.columns:
            comment = table_doc.columns[column_name].description
        samples = [
            str(row.get(column_name))
            for row in sample_rows[:5]
            if row.get(column_name) not in {None, ""}
        ]
        override = self.SEMANTIC_TEXT_OVERRIDES.get((table_name, column_name), "")
        return " ".join([table_name, column_name, str(column.get("description", "")), comment, override, *samples]).strip()

    def _priority(self, table_name: str, column_name: str) -> str:
        if (table_name, column_name) in {
            ("dim_material", "voltage_level"),
            ("dim_material", "color_cd"),
            ("dim_material", "material_sku"),
            ("dim_material", "material_nm"),
            ("dim_material", "material_type_cd"),
        }:
            return "direct_business"
        if table_name == "eav_material_attr":
            return "eav_extension"
        if table_name == "dim_material_alias" or "alias" in column_name:
            return "alias_property"
        if table_name.startswith("dim_"):
            return "dimension_standard"
        return "direct_business"

    def _priority_bonus(self, priority: str) -> int:
        return {
            "direct_business": 35,
            "dimension_standard": 30,
            "alias_property": 5,
            "eav_extension": 0,
        }.get(priority, 0)

    def _priority_rank(self, item: FieldScore) -> int:
        return {
            "direct_business": 4,
            "dimension_standard": 3,
            "alias_property": 2,
            "eav_extension": 1,
        }.get(item.priority, 0)

    def _find_column(self, table: dict[str, Any] | None, column_name: str) -> dict[str, Any] | None:
        if not table:
            return None
        for column in table.get("columns", []):
            if column.get("name") == column_name:
                return column
        return None

    def _has_any(self, question: str, triggers: set[str]) -> bool:
        q = question.lower()
        return any(trigger.lower() in q for trigger in triggers)

    def _chinese_tokens(self, question: str) -> list[str]:
        return [token for token in ["电压", "颜色", "红色", "编码", "名称", "成品", "物料"] if token in question]
