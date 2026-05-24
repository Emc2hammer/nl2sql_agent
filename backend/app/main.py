"""FastAPI application entry point for NL2SQL MVP."""

import json
import logging
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import get_table_schema
from app.core.init_db import init_database
from app.core.tracing import TRACE_DIR, TraceRecorder
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    TableSchemaResponse,
    ValidateSQLRequest,
    ValidateSQLResponse,
)
from app.services.routing.context_builder import ContextBuilder
from app.services.routing.difficulty_router import DifficultyRouter
from app.services.llm.embedding_service import EmbeddingService
from app.services.quality.empty_result_diagnoser import EmptyResultDiagnoser
from app.services.knowledge.example_store import ExampleStore
from app.services.knowledge.failure_case_store import FailureCaseStore
from app.services.quality.insight_service import InsightService
from app.services.knowledge.knowledge_base import (
    BUSINESS_RULES_PATH,
    FEW_SHOTS_PATH,
    SQL_PATTERNS_PATH,
    load_json_list,
)
from app.services.llm.nl2sql_service import NL2SQLService
from app.services.planning.query_planner import LogicalPlanBuilder
from app.services.execution.query_service import QueryService
from app.services.llm.reranker_service import RerankerService
from app.services.quality.reflection_service import ReflectionService
from app.services.quality.result_sanity import ResultSanityChecker
from app.services.execution.sql_guard import SQLGuard
from app.services.execution.sql_semantic_verifier import SQLSemanticVerifier
from app.services.llm.supervisor_llm_service import SupervisorLLMService
from app.services.knowledge.validated_template_service import ValidatedTemplateService
from app.services.qdrant_context_store import QdrantContextStore

logger = logging.getLogger(__name__)

app = FastAPI(
    title="NL2SQL AskData API",
    description="Convert natural language to SQL and query your database",
    version="1.0.0",
)


def build_runtime_context(question: str, schema_info: list[dict] | None = None):
    """Build schema, difficulty decision, and compact context once per question."""
    schema_info = schema_info or get_table_schema()
    difficulty = difficulty_router.classify(question)
    context = context_builder.build_context_for_profile(
        question,
        schema_info,
        difficulty.profile,
    )
    return schema_info, difficulty, context


def build_few_shot_intent_tags(context, difficulty) -> list[str]:
    """Map runtime context into tags used by the curated few-shot store."""
    tags = {context.route.domain, difficulty.label.lower()}
    rule_names = {rule.name for rule in context.rules}
    pattern_names = {pattern.name for pattern in context.patterns}
    linked_names = {column.qualified_name for column in context.linked_columns}

    if rule_names:
        tags.add("business_rule")
    if any("BOM" in name.upper() for name in rule_names) or any("bom" in name.lower() for name in linked_names):
        tags.update(["bom_reasoning", "join_understanding"])
    if any("latest" in name.lower() for name in rule_names | pattern_names) or "fact_price_book.eff_start_dt" in linked_names:
        tags.add("latest_record")
    if any("order" in name.lower() for name in rule_names):
        tags.update(["code_translation", "join_understanding"])
    if any("inventory" in name.lower() for name in rule_names) or "fact_forecast_mth.forecast_qty" in linked_names:
        tags.update(["inventory_reasoning", "derived_metric"])
    if context.route.domain == "quality":
        tags.add("quality_analysis")
    if context.route.domain == "production":
        tags.add("production")
    if difficulty.level in {"L3", "L4"}:
        tags.add("advanced_analytics")
    if any("top" in name.lower() or "rank" in name.lower() for name in pattern_names):
        tags.add("ranking")
    if any("lag" in name.lower() for name in pattern_names):
        tags.add("lag")

    return sorted(tags)


def retrieve_examples_for_context(question: str, context, difficulty) -> list[dict]:
    """Retrieve few-shot examples using the same filters across API endpoints."""
    if difficulty.profile.few_shot_top_k <= 0:
        return []

    return example_store.retrieve(
        question,
        top_k=difficulty.profile.few_shot_top_k,
        use_reranker=bool((settings.reranker_api_key or settings.siliconflow_api_key) and settings.enable_reranker),
        difficulty=difficulty.level,
        intent_tags=build_few_shot_intent_tags(context, difficulty),
        patterns=[pattern.name for pattern in context.patterns],
        table_names=context.table_names,
    )


def retrieve_qdrant_context_for_context(question: str, context, difficulty) -> dict:
    """Retrieve semantic context from Qdrant, falling back cleanly on any failure."""
    base_trace = {
        "enabled": bool(settings.enable_qdrant_retrieval),
        "top_k": settings.qdrant_top_k,
        "hit_count": 0,
        "used_types": [],
        "fallback": False,
    }
    if not settings.enable_qdrant_retrieval:
        return {**base_trace, "fallback": True, "reason": "disabled_by_config", "items": []}
    if not qdrant_retrieval_available or qdrant_context_store is None:
        return {**base_trace, "fallback": True, "reason": "qdrant_unavailable", "items": []}
    if embedding_service is None:
        return {**base_trace, "fallback": True, "reason": "embedding_unavailable", "items": []}

    try:
        query_vector = embedding_service.embed_query(question)
        hits = qdrant_context_store.search(
            query_vector=query_vector,
            top_k=settings.qdrant_top_k,
            filters=None,
            score_threshold=settings.qdrant_score_threshold,
        )
    except Exception as exc:
        logger.warning("Qdrant retrieval failed, falling back to local retrieval: %s", exc)
        return {**base_trace, "fallback": True, "reason": str(exc), "items": []}

    if hits and reranker_service and settings.enable_reranker:
        hits = reranker_service.rerank(question, hits, top_k=settings.qdrant_top_k)

    items = [_qdrant_hit_to_context_item(hit) for hit in hits]
    used_types = sorted({item.get("context_type", "unknown") for item in items})
    return {
        **base_trace,
        "hit_count": len(items),
        "used_types": used_types,
        "fallback": len(items) == 0,
        "items": items,
    }


def _qdrant_hit_to_context_item(hit: dict) -> dict:
    payload = hit.get("payload") or {}
    item_type = payload.get("type", "unknown")
    question = payload.get("question") or payload.get("content") or ""
    sql = payload.get("sql") or ""
    return {
        "id": payload.get("source_id") or hit.get("id", "qdrant"),
        "question": question,
        "sql": sql,
        "text": payload.get("content", hit.get("text", "")),
        "score": hit.get("score", 0.0),
        "context_type": item_type,
        "domain": payload.get("domain", "common"),
        "difficulty": payload.get("difficulty", "unknown"),
        "intent_tags": payload.get("intent_tags", []) or [],
        "tables": payload.get("table_names", []) or [],
        "approved": bool(payload.get("approved", False)),
        "source": "qdrant",
    }


def merge_qdrant_and_local_examples(qdrant_items: list[dict], local_examples: list[dict]) -> list[dict]:
    """Merge Qdrant semantic hits with local few-shot examples while preserving fallback behavior."""
    merged = []
    seen = set()
    for item in [*qdrant_items, *local_examples]:
        key = (item.get("source", "local"), item.get("id"), item.get("question"), item.get("sql"))
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def retrieve_failure_cases_for_context(question: str, context) -> list[dict]:
    """Retrieve similar historical failures to use as negative examples."""
    return failure_case_store.retrieve(
        question=question,
        tables=context.table_names,
        patterns=[pattern.name for pattern in context.patterns],
        top_k=3,
    )


def build_query_plan(question: str, context) -> str:
    """Build a query plan, optionally adding the extra LLM planner call."""
    deterministic_plan = "Deterministic Plan:\n" + logical_plan_builder.build(question, context)
    if not settings.enable_model_planner:
        return deterministic_plan
    return (
        deterministic_plan
        + "\n\nModel Plan:\n"
        + nl2sql_service.generate_plan(question, context)
    )


def context_column_names(context) -> list[str]:
    """Return qualified column names present in the compact context."""
    columns = []
    for table in context.tables:
        for column in table.columns:
            columns.append(f"{table.name}.{column.name}")
    return columns


def save_failure_case(
    *,
    question: str,
    generated_sql: str,
    error_type: str,
    error_message: str,
    corrected_sql: str,
    lesson: str,
    context,
    difficulty,
) -> dict:
    """Persist one failure case for later negative-example retrieval."""
    return failure_case_store.append(
        question=question,
        generated_sql=generated_sql,
        error_type=error_type,
        error_message=error_message,
        corrected_sql=corrected_sql,
        lesson=lesson,
        tables=context.table_names,
        columns=context_column_names(context),
        difficulty=difficulty.level,
        domain=context.route.domain,
    )


def build_generation_explanation(
    context,
    difficulty,
    query_plan,
    examples,
    semantic_issues=None,
    sanity_warnings=None,
) -> str:
    """Build a concise trace of the routing and SQL-generation decisions."""
    parts = [
        f"Difficulty: {difficulty.level} / {difficulty.label}. Reasons: {'; '.join(difficulty.reasons)}.",
        f"Domain: {context.route.domain}. Matched keywords: {', '.join(context.route.matched_keywords) or 'none'}.",
        f"Retrieved tables: {', '.join(context.table_names)}.",
    ]

    if context.linked_columns:
        parts.append(
            "Column links: "
            + "; ".join(f"{column.qualified_name}({column.reason})" for column in context.linked_columns[:8])
            + "."
        )
    if context.selected_columns:
        parts.append("Field retrieval: " + ", ".join(context.selected_columns[:12]) + ".")

    if context.rules:
        parts.append(
            "Business rules: "
            + "; ".join(f"{rule.name} => {rule.condition}" for rule in context.rules)
            + "."
        )
    else:
        parts.append("Business rules: no special rule matched.")

    if context.joins:
        parts.append("Join paths: " + "; ".join(join.as_sql_hint() for join in context.joins[:6]) + ".")

    if context.patterns:
        parts.append("SQL patterns: " + "; ".join(pattern.name for pattern in context.patterns) + ".")

    if examples:
        parts.append(
            "Few-shot: "
            + "; ".join(
                f"{example.get('id', 'unknown')}({example.get('difficulty', '-')}/{example.get('pattern', '-')})"
                for example in examples
            )
            + "."
        )

    if query_plan:
        parts.append(f"Query Plan: {query_plan}")

    if semantic_issues:
        parts.append(
            "Semantic verification: "
            + "; ".join(f"{issue.severity}:{issue.code} - {issue.message}" for issue in semantic_issues)
            + "."
        )

    if sanity_warnings:
        parts.append(
            "Result sanity warnings: "
            + "; ".join(f"{warning.code} - {warning.message}" for warning in sanity_warnings)
            + "."
        )

    return "\n".join(parts)


# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
nl2sql_service = NL2SQLService()
sql_guard = SQLGuard()
query_service = QueryService()
empty_result_diagnoser = EmptyResultDiagnoser(query_service, settings.database_url)
embedding_service = EmbeddingService() if (settings.enable_embedding_retrieval or settings.enable_qdrant_retrieval) and (settings.embedding_api_key or settings.siliconflow_api_key) else None
reranker_service = RerankerService() if settings.enable_reranker and (settings.reranker_api_key or settings.siliconflow_api_key) else None
example_store = ExampleStore(
    embedding_service=embedding_service,
    reranker_service=reranker_service,
)
context_builder = ContextBuilder()
difficulty_router = DifficultyRouter()
logical_plan_builder = LogicalPlanBuilder()
semantic_verifier = SQLSemanticVerifier()
result_sanity_checker = ResultSanityChecker()
insight_service = InsightService()
supervisor_llm_service = SupervisorLLMService()
reflection_service = ReflectionService(supervisor_llm_service)
failure_case_store = FailureCaseStore()
validated_template_service = ValidatedTemplateService()
qdrant_context_store = None
qdrant_retrieval_available = False


# Load examples & init database on startup
@app.on_event("startup")
async def startup():
    global qdrant_context_store, qdrant_retrieval_available
    example_store.load()
    if settings.enable_qdrant_retrieval:
        try:
            qdrant_context_store = QdrantContextStore()
            qdrant_context_store.ping()
            if not qdrant_context_store.collection_exists():
                qdrant_retrieval_available = False
                logger.warning(
                    "Qdrant connected but collection %s does not exist; Qdrant retrieval disabled.",
                    settings.qdrant_collection,
                )
            else:
                qdrant_retrieval_available = True
                logger.info("Qdrant connected: %s", settings.qdrant_url)
                logger.info("Qdrant collection: %s", settings.qdrant_collection)
                logger.info("Qdrant retrieval enabled")
        except Exception as exc:
            qdrant_context_store = None
            qdrant_retrieval_available = False
            logger.warning("Qdrant unavailable, falling back to local retrieval: %s", exc)
    init_database()


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "nl2sql-askdata",
        "version": "1.0.0",
        "models": {
            "llm": {
                "provider": "siliconflow",
                "model": settings.llm_model_name,
                "connected": bool(settings.siliconflow_api_key),
                "retry_attempts": settings.llm_retry_attempts,
                "model_planner_enabled": settings.enable_model_planner,
            },
            "embedding": {
                "provider": "siliconflow",
                "model": settings.embedding_model_name,
                "connected": bool(embedding_service),
                "enabled": settings.enable_embedding_retrieval,
            },
            "reranker": {
                "provider": "siliconflow",
                "model": settings.reranker_model_name,
                "connected": bool((settings.reranker_api_key or settings.siliconflow_api_key) and settings.enable_reranker),
                "enabled": settings.enable_reranker,
                "loaded": bool(reranker_service and reranker_service.is_loaded),
            },
            "qdrant": {
                "url": settings.qdrant_url,
                "collection": settings.qdrant_collection,
                "enabled": settings.enable_qdrant_retrieval,
                "connected": qdrant_retrieval_available,
                "top_k": settings.qdrant_top_k,
                "score_threshold": settings.qdrant_score_threshold,
            },
        },
        "examples": {"total": len(example_store.examples)},
    }


@app.get("/api/schema", response_model=TableSchemaResponse, tags=["Schema"])
async def get_schema():
    """Get database schema information."""
    try:
        schema = get_table_schema()
        return TableSchemaResponse(tables=schema)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch schema: {str(e)}")


@app.get("/api/context", tags=["Schema"])
async def inspect_context(question: str):
    """Inspect the compact context that will be used for NL2SQL generation."""
    try:
        _, difficulty, context = build_runtime_context(question)
        return {
            "question": question,
            "difficulty": {
                "level": difficulty.level,
                "label": difficulty.label,
                "reasons": difficulty.reasons,
                "pipeline": {
                    "table_top_k": difficulty.profile.table_top_k,
                    "max_columns_per_table": difficulty.profile.max_columns_per_table,
                    "max_joins": difficulty.profile.max_joins,
                    "max_rules": difficulty.profile.max_rules,
                    "few_shot_top_k": difficulty.profile.few_shot_top_k,
                    "use_planner": difficulty.profile.use_planner,
                    "use_repair": difficulty.profile.use_repair,
                },
            },
            "domain": context.route.domain,
            "matched_keywords": context.route.matched_keywords,
            "rules": [
                {
                    "name": rule.name,
                    "condition": rule.condition,
                    "required_joins": rule.required_joins,
                    "note": rule.note,
                }
                for rule in context.rules
            ],
            "patterns": [
                {
                    "name": pattern.name,
                    "description": pattern.description,
                    "template_hint": pattern.template_hint,
                }
                for pattern in context.patterns
            ],
            "linked_columns": [
                {
                    "table_name": column.table_name,
                    "column_name": column.column_name,
                    "qualified_name": column.qualified_name,
                    "type": column.column_type,
                    "description": column.description,
                    "score": column.score,
                    "reason": column.reason,
                }
                for column in context.linked_columns
            ],
            "tables": [
                {
                    "table_name": table.name,
                    "description": table.description,
                    "columns": [
                        {
                            "name": col.name,
                            "type": col.type,
                            "description": col.description,
                            "primary_key": col.primary_key,
                        }
                        for col in table.columns
                    ],
                }
                for table in context.tables
            ],
            "joins": [join.as_sql_hint() for join in context.joins],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build context: {str(e)}")


@app.get("/api/knowledge", tags=["Schema"])
async def inspect_knowledge(question: str = ""):
    """Inspect local RAG-style NL2SQL knowledge sources."""
    try:
        schema_info = get_table_schema()
        difficulty = None
        context = None
        examples = []

        if question:
            schema_info, difficulty, context = build_runtime_context(question, schema_info)
            examples = retrieve_examples_for_context(question, context, difficulty)

        return {
            "sources": {
                "schema": {
                    "tables": len(schema_info),
                    "source": "SQLite inspection + table_dictionary.csv",
                },
                "joins": {
                    "source": "relationship_map.csv",
                },
                "business_rules": {
                    "path": str(BUSINESS_RULES_PATH),
                    "count": len(load_json_list(BUSINESS_RULES_PATH)),
                },
                "sql_patterns": {
                    "path": str(SQL_PATTERNS_PATH),
                    "count": len(load_json_list(SQL_PATTERNS_PATH)),
                },
                "few_shots": {
                    "path": str(FEW_SHOTS_PATH),
                    "count": len(example_store.examples),
                },
            },
            "question": question,
            "difficulty": None
            if not difficulty
            else {
                "level": difficulty.level,
                "label": difficulty.label,
                "reasons": difficulty.reasons,
            },
            "retrieved": None
            if not context
            else {
                "tables": context.table_names,
                "rules": [rule.name for rule in context.rules],
                "patterns": [pattern.name for pattern in context.patterns],
                "linked_columns": [column.qualified_name for column in context.linked_columns],
                "joins": [join.as_sql_hint() for join in context.joins],
                "few_shots": [
                    {
                        "question": example.get("question"),
                        "score": example.get("score"),
                    }
                    for example in examples
                ],
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to inspect knowledge: {str(e)}")


def _load_trace_file(trace_id: str, filename: str) -> dict:
    if not trace_id.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid trace_id")
    path = TRACE_DIR / trace_id / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Trace {filename} not found")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read trace file: {str(e)}")


@app.get("/api/traces/{trace_id}/summary", tags=["Trace"])
async def get_trace_summary(trace_id: str):
    """Read compact trace summary only."""
    return _load_trace_file(trace_id, "summary.json")


@app.get("/api/traces/{trace_id}/debug", tags=["Trace"])
async def get_trace_debug(trace_id: str):
    """Read debug trace details when TRACE_LEVEL=debug."""
    return _load_trace_file(trace_id, "debug.json")


@app.post("/api/chat", response_model=ChatResponse, tags=["Chat"])
def chat(request: ChatRequest):
    """
    Process a natural language question and return SQL query results.

    Pipeline:
    1. Fetch database schema.
    2. Build compact routed context.
    3. Retrieve filtered few-shot examples.
    4. Generate and validate SQL.
    5. Execute SQL against the database.
    6. Return results, explanation, and lightweight insights.
    """
    start_time = time.time()
    trace = TraceRecorder(question=request.question)
    trace_status = "success"
    trace_error = None

    try:
        schema_info = trace.run(
            "schema",
            {"question": request.question},
            get_table_schema,
        )
        difficulty = trace.run(
            "difficulty_router",
            {"question": request.question},
            lambda: difficulty_router.classify(request.question),
        )
        context = trace.run(
            "context_builder",
            {
                "question": request.question,
                "schema_tables": len(schema_info),
                "difficulty": difficulty.level,
            },
            lambda: context_builder.build_context_for_profile(
                request.question,
                schema_info,
                difficulty.profile,
            ),
        )
        trace.record_step(
            "query_router",
            input={"question": request.question},
            output={
                "domain": context.route.domain,
                "matched_keywords": context.route.matched_keywords,
                "selected_tables": context.table_names,
                "selected_columns": context.selected_columns,
                "column_similarity_scores": context.column_scores,
                "routing_reason": context.routing_reason,
                "why_alias_table_selected": context.why_alias_table_selected,
                "why_main_table_field_rejected": context.why_main_table_field_rejected,
            },
            status="success",
            latency_ms=0.0,
        )
        qdrant_retrieval = trace.run(
            "qdrant_retrieval",
            {
                "question": request.question,
                "top_k": settings.qdrant_top_k,
                "score_threshold": settings.qdrant_score_threshold,
                "domain": context.route.domain,
                "difficulty": difficulty.level,
                "tables": context.table_names,
            },
            lambda: retrieve_qdrant_context_for_context(request.question, context, difficulty),
        )
        local_examples = trace.run(
            "example_store",
            {
                "question": request.question,
                "top_k": difficulty.profile.few_shot_top_k,
                "tables": context.table_names,
            },
            lambda: retrieve_examples_for_context(request.question, context, difficulty),
        )
        similar_examples = merge_qdrant_and_local_examples(
            qdrant_retrieval.get("items", []),
            local_examples,
        )
        negative_examples = trace.run(
            "failure_case_store",
            {
                "question": request.question,
                "tables": context.table_names,
                "patterns": [pattern.name for pattern in context.patterns],
            },
            lambda: retrieve_failure_cases_for_context(request.question, context),
        )

        query_plan = None
        if difficulty.profile.use_planner:
            query_plan = trace.run(
                "planner",
                {
                    "question": request.question,
                    "tables": context.table_names,
                    "model_planner_enabled": settings.enable_model_planner,
                },
                lambda: build_query_plan(request.question, context),
            )
        else:
            trace.record_step(
                "planner",
                input={"question": request.question, "difficulty": difficulty.level},
                output={"enabled": False},
                status="skipped",
                latency_ms=0.0,
            )

        template_decision = trace.run(
            "validated_template_service",
            {
                "question": request.question,
                "tables": context.table_names,
                "patterns": [pattern.name for pattern in context.patterns],
            },
            lambda: validated_template_service.decide(request.question, context),
        )

        if template_decision.template_reuse_hit and not template_decision.template_reuse_allowed:
            if template_decision.retrieved_example:
                similar_examples = [template_decision.retrieved_example] + similar_examples

        if template_decision.template_reuse_allowed and template_decision.sql:
            sql = template_decision.sql
            trace.record_step(
                "nl2sql_service",
                input={
                    "question": request.question,
                    "tables": context.table_names,
                    "template_id": template_decision.template_id,
                },
                output={
                    "enabled": False,
                    "reason": "validated_template_reused",
                    "template_id": template_decision.template_id,
                    "template_score": template_decision.template_score,
                },
                status="skipped",
                latency_ms=0.0,
            )
        else:
            sql = trace.run(
                "nl2sql_service",
                {
                    "question": request.question,
                    "tables": context.table_names,
                    "examples": [example.get("id") for example in similar_examples],
                    "negative_examples": [example.get("error_type") for example in negative_examples],
                    "has_query_plan": bool(query_plan),
                },
                lambda: nl2sql_service.generate_sql(
                    request.question,
                    context,
                    examples=similar_examples,
                    negative_examples=negative_examples,
                    query_plan=query_plan,
                ),
            )

        is_valid, message, _ = trace.run(
            "sql_guard",
            {"sql": sql},
            lambda: sql_guard.validate(sql),
        )
        if not is_valid:
            trace_status = "validation_failed"
            trace.run(
                "failure_case_store.append",
                {"error_type": "SQL_SYNTAX_ERROR", "sql": sql},
                lambda: save_failure_case(
                    question=request.question,
                    generated_sql=sql,
                    error_type="SQL_SYNTAX_ERROR",
                    error_message=message,
                    corrected_sql="",
                    lesson="SQL guard rejected this query. Avoid unsafe or invalid SQL and return read-only SQLite SELECT only.",
                    context=context,
                    difficulty=difficulty,
                ),
            )
            response = ChatResponse(
                trace_id=trace.trace_id,
                question=request.question,
                sql=sql,
                result=[],
                error=f"SQL validation failed: {message}",
                execution_time=round(time.time() - start_time, 3),
                generated_sql=sql,
                explanation=build_generation_explanation(context, difficulty, query_plan, similar_examples),
                insights=[],
            )
            trace.record_step(
                "sql_semantic_verifier",
                input={"sql": sql},
                output={"enabled": False, "reason": "sql_guard_failed"},
                status="skipped",
                latency_ms=0.0,
            )
            trace.record_step(
                "query_service",
                input={"sql": sql},
                output={"enabled": False, "reason": "sql_guard_failed"},
                status="skipped",
                latency_ms=0.0,
            )
            trace.record_step(
                "repair.semantic",
                input={"sql": sql},
                output={"enabled": False, "reason": "sql_guard_failed"},
                status="skipped",
                latency_ms=0.0,
            )
            trace.record_step(
                "repair.execution",
                input={"sql": sql},
                output={"enabled": False, "reason": "sql_guard_failed"},
                status="skipped",
                latency_ms=0.0,
            )
            trace.record_step(
                "result_sanity",
                input={"rows": 0, "columns": []},
                output={"enabled": False, "reason": "sql_guard_failed"},
                status="skipped",
                latency_ms=0.0,
            )
            trace.record_step(
                "insight_service",
                input={"rows": 0, "columns": []},
                output={"enabled": False, "reason": "sql_guard_failed"},
                status="skipped",
                latency_ms=0.0,
            )
            return response

        semantic_issues = trace.run(
            "sql_semantic_verifier",
            {"question": request.question, "sql": sql},
            lambda: semantic_verifier.verify(request.question, sql, schema_info),
        )
        if semantic_verifier.has_blocking_issue(semantic_issues) and difficulty.profile.use_repair:
            repaired_sql = trace.run(
                "repair.semantic",
                {
                    "question": request.question,
                    "failed_sql": sql,
                    "issues": semantic_issues,
                },
                lambda: nl2sql_service.repair_sql(
                    question=request.question,
                    context=context,
                    failed_sql=sql,
                    error="Semantic verification failed:\n" + semantic_verifier.format_issues(semantic_issues),
                ),
            )
            is_valid, _, _ = trace.run(
                "repair.sql_guard",
                {"sql": repaired_sql},
                lambda: sql_guard.validate(repaired_sql),
            )
            if is_valid and repaired_sql != sql:
                repaired_issues = trace.run(
                    "repair.sql_semantic_verifier",
                    {"question": request.question, "sql": repaired_sql},
                    lambda: semantic_verifier.verify(request.question, repaired_sql, schema_info),
                )
                if not semantic_verifier.has_blocking_issue(repaired_issues):
                    sql = repaired_sql
                    semantic_issues = repaired_issues
        else:
            trace.record_step(
                "repair.semantic",
                input={"sql": sql, "difficulty": difficulty.level},
                output={"enabled": False},
                status="skipped",
                latency_ms=0.0,
            )

        query_result = trace.run(
            "query_service",
            {"sql": sql},
            lambda: query_service.execute_query(sql),
        )

        if query_result["error"] and difficulty.profile.use_repair:
            repaired_sql = trace.run(
                "repair.execution",
                {
                    "question": request.question,
                    "failed_sql": sql,
                    "error": query_result["error"],
                },
                lambda: nl2sql_service.repair_sql(
                    question=request.question,
                    context=context,
                    failed_sql=sql,
                    error=query_result["error"],
                ),
            )
            is_valid, _, _ = trace.run(
                "repair.execution_sql_guard",
                {"sql": repaired_sql},
                lambda: sql_guard.validate(repaired_sql),
            )
            if is_valid and repaired_sql != sql:
                repaired_result = trace.run(
                    "repair.execution_query_service",
                    {"sql": repaired_sql},
                    lambda: query_service.execute_query(repaired_sql),
                )
                if not repaired_result["error"]:
                    sql = repaired_sql
                    query_result = repaired_result
                    semantic_issues = trace.run(
                        "repair.execution_sql_semantic_verifier",
                        {"question": request.question, "sql": sql},
                        lambda: semantic_verifier.verify(request.question, sql, schema_info),
                    )
        else:
            trace.record_step(
                "repair.execution",
                input={"sql": sql, "query_error": query_result["error"]},
                output={"enabled": False},
                status="skipped",
                latency_ms=0.0,
            )

        result_rows = query_result["rows"] if not query_result["error"] else []
        if query_result["error"]:
            sanity_warnings = []
            trace.record_step(
                "result_sanity",
                input={"rows": 0, "columns": query_result["columns"]},
                output={"enabled": False, "reason": "query_error"},
                status="skipped",
                latency_ms=0.0,
            )
        else:
            sanity_warnings = trace.run(
                "result_sanity",
                {"rows": len(result_rows), "columns": query_result["columns"]},
                lambda: result_sanity_checker.check(result_rows, query_result["columns"]),
            )

        for retry_index in range(1, 3):
            if not query_result["error"] and not sanity_warnings:
                break

            reflection = trace.run(
                f"reflection.{retry_index}",
                {
                    "trace_id": trace.trace_id,
                    "query_error": query_result["error"],
                    "sanity_warnings": sanity_warnings,
                },
                lambda: reflection_service.reflect(trace.trace),
            )
            if not reflection.should_retry:
                trace.run(
                    f"failure_case_store.append.{retry_index}",
                    {"error_type": reflection.error_type, "sql": sql},
                    lambda: save_failure_case(
                        question=request.question,
                        generated_sql=sql,
                        error_type=reflection.error_type,
                        error_message=reflection.reason,
                        corrected_sql="",
                        lesson=reflection.repair_suggestion,
                        context=context,
                        difficulty=difficulty,
                    ),
                )
                break

            empty_result_diagnosis = None
            if reflection.error_type == ReflectionService.EMPTY_RESULT:
                if settings.enable_empty_result_diagnosis:
                    empty_result_diagnosis = trace.run(
                        "empty_result_diagnoser",
                        {
                            "question": request.question,
                            "sql": sql,
                            "tables": context.table_names,
                            "retry_index": retry_index,
                        },
                        lambda: empty_result_diagnoser.diagnose(
                            question=request.question,
                            generated_sql=sql,
                            selected_tables=context.table_names,
                            schema_info=schema_info,
                            context=context,
                            enable_value_resolver=settings.enable_value_resolver,
                        ),
                    )
                    trace.record_step(
                        "condition_probe",
                        input={"sql": sql, "retry_index": retry_index},
                        output={
                            "where_conditions": empty_result_diagnosis.get("where_conditions", []),
                            "condition_probe_results": empty_result_diagnosis.get("condition_probe_results", []),
                            "suspect_conditions": empty_result_diagnosis.get("suspect_conditions", []),
                        },
                        status="success",
                        latency_ms=0.0,
                    )
                    trace.record_step(
                        "value_resolver",
                        input={"question": request.question, "retry_index": retry_index},
                        output={
                            "enabled": settings.enable_value_resolver,
                            "value_probe_results": empty_result_diagnosis.get("value_probe_results", []),
                            "retry_advice": empty_result_diagnosis.get("retry_advice", ""),
                            "allow_retry": empty_result_diagnosis.get("allow_retry", True),
                        },
                        status="success" if settings.enable_value_resolver else "skipped",
                        latency_ms=0.0,
                    )
                    if not empty_result_diagnosis.get("allow_retry", True):
                        trace.run(
                            f"failure_case_store.append.{retry_index}",
                            {"error_type": reflection.error_type, "sql": sql},
                            lambda: save_failure_case(
                                question=request.question,
                                generated_sql=sql,
                                error_type=reflection.error_type,
                                error_message=empty_result_diagnosis.get("diagnosis_reason", reflection.reason),
                                corrected_sql="",
                                lesson=empty_result_diagnosis.get("retry_advice", reflection.repair_suggestion),
                                context=context,
                                difficulty=difficulty,
                            ),
                        )
                        trace.record_step(
                            f"reflection_retry.{retry_index}.stop",
                            input={"error_type": reflection.error_type, "allow_retry": False},
                            output={
                                "reason": "empty_result_diagnosis_disallowed_retry",
                                "diagnosis_reason": empty_result_diagnosis.get("diagnosis_reason", ""),
                                "retry_advice": empty_result_diagnosis.get("retry_advice", ""),
                            },
                            status="skipped",
                            latency_ms=0.0,
                        )
                        break
                else:
                    trace.record_step(
                        "empty_result_diagnoser",
                        input={"sql": sql, "retry_index": retry_index},
                        output={"enabled": False, "reason": "disabled_by_config", "allow_retry": True},
                        status="skipped",
                        latency_ms=0.0,
                    )

            failed_sql_for_memory = sql
            diagnosis_prompt = ""
            if empty_result_diagnosis:
                diagnosis_prompt = (
                    "\n\nEMPTY_RESULT condition attribution diagnosis:\n"
                    f"{json.dumps(empty_result_diagnosis, ensure_ascii=False, indent=2)}\n"
                    "Mandatory EMPTY_RESULT repair constraints:\n"
                    "- Do not change the SELECT target fields.\n"
                    "- Do not rewrite JOINs into IN subqueries without a semantic reason.\n"
                    "- Prefer fixing only the WHERE condition(s) identified as causing empty results.\n"
                    "- Use only enum/candidate values that were observed in the database probes.\n"
                    "- If the candidates do not confirm a valid repair, do not guess; return diagnostic information instead.\n"
                )
            repaired_sql = trace.run(
                f"reflection_retry.{retry_index}.nl2sql_service",
                {
                    "failed_sql": sql,
                    "error_type": reflection.error_type,
                    "root_cause_step": reflection.root_cause_step,
                    "repair_suggestion": reflection.repair_suggestion,
                },
                lambda: nl2sql_service.repair_sql(
                    question=request.question,
                    context=context,
                    failed_sql=sql,
                    error=(
                        f"Reflection error_type: {reflection.error_type}\n"
                        f"Root cause step: {reflection.root_cause_step}\n"
                        f"Reason: {reflection.reason}\n"
                        f"Repair suggestion: {reflection.repair_suggestion}"
                        f"{diagnosis_prompt}"
                    ),
                ),
            )
            is_valid, _, _ = trace.run(
                f"reflection_retry.{retry_index}.sql_guard",
                {"sql": repaired_sql},
                lambda: sql_guard.validate(repaired_sql),
            )
            if not is_valid or repaired_sql == sql:
                trace.run(
                    f"failure_case_store.append.{retry_index}",
                    {"error_type": reflection.error_type, "sql": failed_sql_for_memory},
                    lambda: save_failure_case(
                        question=request.question,
                        generated_sql=failed_sql_for_memory,
                        error_type=reflection.error_type,
                        error_message=reflection.reason,
                        corrected_sql=repaired_sql if repaired_sql != failed_sql_for_memory else "",
                        lesson=reflection.repair_suggestion,
                        context=context,
                        difficulty=difficulty,
                    ),
                )
                trace.record_step(
                    f"reflection_retry.{retry_index}.stop",
                    input={"sql_changed": repaired_sql != sql, "is_valid": is_valid},
                    output={"reason": "invalid_or_unchanged_retry_sql"},
                    status="skipped",
                    latency_ms=0.0,
                )
                break

            repaired_issues = trace.run(
                f"reflection_retry.{retry_index}.sql_semantic_verifier",
                {"question": request.question, "sql": repaired_sql},
                lambda: semantic_verifier.verify(request.question, repaired_sql, schema_info),
            )
            if semantic_verifier.has_blocking_issue(repaired_issues):
                trace.run(
                    f"failure_case_store.append.{retry_index}",
                    {"error_type": reflection.error_type, "sql": failed_sql_for_memory},
                    lambda: save_failure_case(
                        question=request.question,
                        generated_sql=failed_sql_for_memory,
                        error_type=reflection.error_type,
                        error_message=reflection.reason,
                        corrected_sql=repaired_sql,
                        lesson=reflection.repair_suggestion,
                        context=context,
                        difficulty=difficulty,
                    ),
                )
                trace.record_step(
                    f"reflection_retry.{retry_index}.stop",
                    input={"semantic_issues": repaired_issues},
                    output={"reason": "blocking_semantic_issue"},
                    status="skipped",
                    latency_ms=0.0,
                )
                break

            sql = repaired_sql
            semantic_issues = repaired_issues
            query_result = trace.run(
                f"reflection_retry.{retry_index}.query_service",
                {"sql": sql},
                lambda: query_service.execute_query(sql),
            )
            result_rows = query_result["rows"] if not query_result["error"] else []
            if query_result["error"]:
                sanity_warnings = []
                trace.record_step(
                    f"reflection_retry.{retry_index}.result_sanity",
                    input={"rows": 0, "columns": query_result["columns"]},
                    output={"enabled": False, "reason": "query_error"},
                    status="skipped",
                    latency_ms=0.0,
                )
            else:
                sanity_warnings = trace.run(
                    f"reflection_retry.{retry_index}.result_sanity",
                    {"rows": len(result_rows), "columns": query_result["columns"]},
                    lambda: result_sanity_checker.check(result_rows, query_result["columns"]),
                )
            trace.run(
                f"failure_case_store.append.{retry_index}",
                {"error_type": reflection.error_type, "sql": failed_sql_for_memory},
                lambda: save_failure_case(
                    question=request.question,
                    generated_sql=failed_sql_for_memory,
                    error_type=reflection.error_type,
                    error_message=reflection.reason,
                    corrected_sql=sql if not query_result["error"] and not sanity_warnings else "",
                    lesson=reflection.repair_suggestion,
                    context=context,
                    difficulty=difficulty,
                ),
            )

        if query_result["error"]:
            trace.record_step(
                "insight_service",
                input={"rows": 0, "columns": query_result["columns"]},
                output={"enabled": False, "reason": "query_error"},
                status="skipped",
                latency_ms=0.0,
            )
            insights = []
        else:
            insights = trace.run(
                "insight_service",
                {"rows": len(result_rows), "columns": query_result["columns"]},
                lambda: insight_service.generate(
                    result_rows,
                    query_result["columns"],
                    question=request.question,
                ),
            )

        execution_time = round(time.time() - start_time, 3)

        return ChatResponse(
            trace_id=trace.trace_id,
            question=request.question,
            sql=sql,
            result=result_rows,
            columns=query_result["columns"],
            execution_time=execution_time,
            error=query_result["error"],
            generated_sql=sql,
            explanation=build_generation_explanation(
                context,
                difficulty,
                query_plan,
                similar_examples,
                semantic_issues=semantic_issues,
                sanity_warnings=sanity_warnings,
            ),
            insights=insights,
        )

    except Exception as e:
        trace_status = "error"
        trace_error = str(e)
        return ChatResponse(
            trace_id=trace.trace_id,
            question=request.question,
            sql="",
            result=[],
            error=f"Service error: {str(e)}",
            execution_time=round(time.time() - start_time, 3),
            generated_sql="",
            explanation="The service failed before SQL generation or execution completed.",
            insights=[],
        )
    finally:
        trace.save(status=trace_status, error=trace_error)


@app.post("/api/validate-sql", response_model=ValidateSQLResponse, tags=["Validation"])
async def validate_sql(request: ValidateSQLRequest):
    """Validate a SQL query for safety."""
    is_valid, message, risk_level = sql_guard.validate(request.sql)
    return ValidateSQLResponse(
        valid=is_valid,
        message=message,
        risk_level=risk_level,
    )
