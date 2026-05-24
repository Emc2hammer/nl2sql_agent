"""Build compact, routed context for NL2SQL generation."""

from dataclasses import dataclass

from app.services.routing.difficulty_router import PipelineProfile, PIPELINE_PROFILES
from app.services.retrieval.field_semantic_retriever import FieldRetrievalResult, FieldSemanticRetriever
from app.services.retrieval.join_retriever import JoinPath, JoinRetriever
from app.services.retrieval.column_linker import ColumnLinker, LinkedColumn
from app.services.retrieval.pattern_retriever import PatternRetriever, SQLPattern
from app.services.routing.query_router import DomainRoute, route_question
from app.services.retrieval.rule_retriever import BusinessRule, RuleRetriever
from app.services.retrieval.schema_indexer import SchemaIndex
from app.services.retrieval.schema_retriever import RetrievedTable, SchemaRetriever


@dataclass
class NL2SQLContext:
    """Compact context selected for one user question."""

    route: DomainRoute
    tables: list[RetrievedTable]
    joins: list[JoinPath]
    rules: list[BusinessRule]
    patterns: list[SQLPattern]
    linked_columns: list[LinkedColumn]
    selected_columns: list[str]
    column_scores: list[dict]
    routing_reason: list[str]
    why_alias_table_selected: str = ""
    why_main_table_field_rejected: str = ""

    @property
    def table_names(self) -> list[str]:
        return [table.name for table in self.tables]


class ContextBuilder:
    """Coordinate route, schema, join, and rule retrieval."""

    def __init__(self) -> None:
        schema_index = SchemaIndex()
        self.schema_retriever = SchemaRetriever(schema_index)
        self.join_retriever = JoinRetriever()
        self.rule_retriever = RuleRetriever()
        self.pattern_retriever = PatternRetriever()
        self.column_linker = ColumnLinker()
        self.field_retriever = FieldSemanticRetriever(schema_index)

    def build_context(self, question: str, schema_info: list[dict]) -> NL2SQLContext:
        return self.build_context_for_profile(question, schema_info, PIPELINE_PROFILES["L2"])

    def build_context_for_profile(
        self,
        question: str,
        schema_info: list[dict],
        profile: PipelineProfile,
    ) -> NL2SQLContext:
        route = route_question(question)
        field_result = self.field_retriever.retrieve(
            question=question,
            schema_info=schema_info,
            domain=route.domain,
            top_k=max(12, profile.max_columns_per_table * 2),
        )
        schema_for_table_retrieval = self._schema_for_field_result(schema_info, field_result)
        tables = self.schema_retriever.retrieve(
            question=question,
            domain=route.domain,
            schema_info=schema_for_table_retrieval,
            top_k=min(profile.table_top_k, max(1, len(schema_for_table_retrieval))),
            max_columns_per_table=profile.max_columns_per_table,
            preferred_columns=field_result.selected_columns,
        )
        rules = self.rule_retriever.retrieve(question, max_rules=profile.max_rules)
        table_names = self._ensure_rule_tables(
            [table.name for table in tables],
            rules,
            max_tables=max(profile.table_top_k, 8),
            question=question,
        )
        if table_names != [table.name for table in tables]:
            tables = self.schema_retriever.retrieve(
                question=question,
                domain=route.domain,
                schema_info=[
                    table for table in schema_info
                    if table["table_name"] in set(table_names)
                ],
                top_k=len(table_names),
                max_columns_per_table=profile.max_columns_per_table,
                preferred_columns=field_result.selected_columns,
            )
        joins = self.join_retriever.retrieve(
            [table.name for table in tables],
            max_joins=profile.max_joins,
        )
        patterns = self.pattern_retriever.retrieve(
            question,
            max_patterns=3 if profile.use_planner else 1,
        )
        linked_columns = self.column_linker.link(
            question=question,
            schema_info=schema_info,
            table_names=[table.name for table in tables],
            top_k=max(12, profile.max_columns_per_table * 2),
        )
        return NL2SQLContext(
            route=route,
            tables=tables,
            joins=joins,
            rules=rules,
            patterns=patterns,
            linked_columns=linked_columns,
            selected_columns=field_result.selected_columns,
            column_scores=field_result.column_scores,
            routing_reason=field_result.routing_reason,
            why_alias_table_selected=field_result.why_alias_table_selected,
            why_main_table_field_rejected=field_result.why_main_table_field_rejected,
        )

    def _ensure_rule_tables(
        self,
        table_names: list[str],
        rules: list[BusinessRule],
        max_tables: int,
        question: str = "",
    ) -> list[str]:
        selected = list(table_names)
        for rule in rules:
            for join in rule.required_joins:
                for side in join.split("="):
                    table_name = side.strip().split(".")[0]
                    if not self._allow_special_table(table_name, question):
                        continue
                    if table_name and table_name not in selected:
                        selected.append(table_name)
        return selected[:max_tables]

    def _schema_for_field_result(
        self,
        schema_info: list[dict],
        field_result: FieldRetrievalResult,
    ) -> list[dict]:
        if not field_result.selected_tables:
            return schema_info
        selected = set(field_result.selected_tables)
        return [table for table in schema_info if table["table_name"] in selected]

    def _allow_special_table(self, table_name: str, question: str) -> bool:
        normalized = question.lower()
        if table_name == "dim_material_alias":
            return any(term in normalized for term in ["别名", "多语言", "属性扩展", "自定义属性", "attribute", "alias"])
        if table_name == "eav_material_attr":
            return any(term in normalized for term in ["属性扩展", "自定义属性", "attribute", "扩展属性", "eav"])
        if table_name in {"bridge_bom_component", "dim_bom_hdr"}:
            return any(term.lower() in normalized for term in ["BOM", "bom", "组件", "配方", "父子物料", "用量", "原材料"])
        return True
