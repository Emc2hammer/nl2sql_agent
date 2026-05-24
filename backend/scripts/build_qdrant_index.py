"""Build the offline Qdrant semantic context index for NL2SQL."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from pathlib import Path
from typing import Any, Iterable


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings  # noqa: E402
from app.services.llm.embedding_service import EmbeddingService  # noqa: E402
from app.services.qdrant_context_store import ContextItem, QdrantContextStore  # noqa: E402


DATA_DIR = BACKEND_DIR / "data"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
PUBLIC_DIR = DATA_DIR / "nl2sqlpublic" / "public"

logger = logging.getLogger("build_qdrant_index")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Qdrant index for NL2SQL semantic context.")
    parser.add_argument("--recreate", action="store_true", help="Delete and recreate the Qdrant collection.")
    parser.add_argument("--batch-size", type=int, default=32, help="Embedding/upsert batch size.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    items = build_context_items()
    if not items:
        raise SystemExit("No context items were found to index.")

    logger.info("Loaded %s context items.", len(items))
    embedding_service = EmbeddingService()
    store = QdrantContextStore()

    total = 0
    vector_size = None
    for batch in _chunks(items, args.batch_size):
        texts = [item.content for item in batch]
        try:
            vectors = embedding_service.embed_documents(texts)
        except Exception as exc:
            raise SystemExit(f"Embedding API failed while building Qdrant index: {exc}") from exc

        if not vectors:
            continue
        if vector_size is None:
            vector_size = len(vectors[0])
            store.ensure_collection(vector_size=vector_size, recreate=args.recreate)
            args.recreate = False

        upsert_items = []
        for item, vector in zip(batch, vectors):
            metadata = dict(item.metadata)
            metadata["vector"] = vector
            upsert_items.append(ContextItem(id=item.id, content=item.content, metadata=metadata))
        total += store.upsert_contexts(upsert_items)

    logger.info("Qdrant collection: %s", settings.qdrant_collection)
    logger.info("Successfully upserted %s context items.", total)


def build_context_items() -> list[ContextItem]:
    items: list[ContextItem] = []
    items.extend(load_few_shots())
    items.extend(load_validated_templates())
    items.extend(load_business_rules())
    items.extend(load_join_paths())
    items.extend(load_metric_definitions())
    items.extend(load_schema_descriptions())
    return items


def load_few_shots() -> list[ContextItem]:
    paths = [
        KNOWLEDGE_DIR / "few_shots.json",
        KNOWLEDGE_DIR / "few_shot_examples.json",
        KNOWLEDGE_DIR / "few_shot_examples.jsonl",
    ]
    items = []
    for path in paths:
        for record in _load_records(path):
            question = record.get("question", "")
            sql = record.get("sql", "")
            content = "\n".join(
                part for part in [
                    f"Few-shot question: {question}",
                    f"Pattern: {record.get('pattern', '')}",
                    f"SQL: {sql}",
                ]
                if part.strip()
            )
            if not content.strip():
                continue
            source_id = record.get("id") or f"few_shot:{len(items) + 1}"
            items.append(
                ContextItem(
                    id=f"few_shot:{source_id}",
                    content=content,
                    metadata={
                        "type": "few_shot",
                        "domain": _infer_domain(record.get("tables", []), record.get("intent_tags", [])),
                        "difficulty": record.get("difficulty", "unknown"),
                        "table_names": record.get("tables", []) or [],
                        "intent_tags": record.get("intent_tags", []) or [],
                        "approved": True,
                        "source_id": str(source_id),
                        "question": question,
                        "sql": sql,
                        "pattern": record.get("pattern", ""),
                    },
                )
            )
    return items


def load_validated_templates() -> list[ContextItem]:
    items = []
    for record in _load_records(KNOWLEDGE_DIR / "validated_templates.jsonl"):
        sql = record.get("sql") or record.get("template_sql", "")
        question = record.get("question", "")
        content = "\n".join(
            part for part in [
                f"Validated template question: {question}",
                f"Pattern: {record.get('pattern', '')}",
                f"Description: {record.get('description', '')}",
                f"SQL template: {sql}",
            ]
            if part.strip()
        )
        if not content.strip():
            continue
        source_id = record.get("id") or record.get("template_id") or f"validated_template:{len(items) + 1}"
        tables = record.get("tables", []) or []
        items.append(
            ContextItem(
                id=f"validated_template:{source_id}",
                content=content,
                metadata={
                    "type": "validated_template",
                    "domain": _infer_domain(tables, record.get("intent_tags", [])),
                    "difficulty": record.get("difficulty", "unknown"),
                    "table_names": tables,
                    "intent_tags": record.get("intent_tags", []) or [],
                    "approved": bool(record.get("approved", False)),
                    "source_id": str(source_id),
                    "question": question,
                    "sql": sql,
                    "pattern": record.get("pattern", ""),
                },
            )
        )
    return items


def load_business_rules() -> list[ContextItem]:
    items = []
    for record in _load_records(KNOWLEDGE_DIR / "business_rules.json"):
        joins = record.get("required_joins", []) or []
        tables = _tables_from_join_strings(joins)
        content = "\n".join(
            part for part in [
                f"Business rule: {record.get('name', '')}",
                f"Condition: {record.get('condition', '')}",
                f"Required joins: {'; '.join(joins)}",
                f"Note: {record.get('note', '')}",
            ]
            if part.strip()
        )
        if not content.strip():
            continue
        source_id = record.get("id") or record.get("name") or f"business_rule:{len(items) + 1}"
        items.append(
            ContextItem(
                id=f"business_rule:{source_id}",
                content=content,
                metadata={
                    "type": "business_rule",
                    "domain": _infer_domain(tables, record.get("keywords", [])),
                    "difficulty": record.get("difficulty", "unknown"),
                    "table_names": tables,
                    "intent_tags": record.get("keywords", []) or [],
                    "approved": True,
                    "source_id": str(source_id),
                },
            )
        )
    return items


def load_join_paths() -> list[ContextItem]:
    path = PUBLIC_DIR / "relationship_map.csv"
    if not path.exists():
        return []
    items = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for index, row in enumerate(csv.DictReader(f), 1):
            from_column = row.get("from_column", "")
            to_column = row.get("to_column", "")
            cardinality = row.get("cardinality", "")
            tables = _tables_from_join_strings([f"{from_column} = {to_column}"])
            content = f"JOIN path: {from_column} = {to_column} ({cardinality})"
            items.append(
                ContextItem(
                    id=f"join_path:{index}",
                    content=content,
                    metadata={
                        "type": "join_path",
                        "domain": _infer_domain(tables, []),
                        "difficulty": "unknown",
                        "table_names": tables,
                        "intent_tags": ["join"],
                        "approved": True,
                        "source_id": f"relationship_map:{index}",
                    },
                )
            )
    return items


def load_metric_definitions() -> list[ContextItem]:
    paths = [
        KNOWLEDGE_DIR / "metric_definitions.json",
        KNOWLEDGE_DIR / "metric_definitions.jsonl",
        *KNOWLEDGE_DIR.glob("metrics*.json"),
        *KNOWLEDGE_DIR.glob("metrics*.jsonl"),
    ]
    items = []
    seen = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        for record in _load_records(path):
            tables = record.get("tables", []) or record.get("table_names", []) or []
            content = "\n".join(
                part for part in [
                    f"Metric: {record.get('name', '') or record.get('metric', '')}",
                    f"Definition: {record.get('definition', '') or record.get('description', '')}",
                    f"Expression: {record.get('expression', '') or record.get('sql', '')}",
                ]
                if part.strip()
            )
            if not content.strip():
                continue
            source_id = record.get("id") or record.get("name") or f"metric_definition:{len(items) + 1}"
            items.append(
                ContextItem(
                    id=f"metric_definition:{source_id}",
                    content=content,
                    metadata={
                        "type": "metric_definition",
                        "domain": _infer_domain(tables, record.get("intent_tags", [])),
                        "difficulty": record.get("difficulty", "unknown"),
                        "table_names": tables,
                        "intent_tags": record.get("intent_tags", []) or [],
                        "approved": bool(record.get("approved", True)),
                        "source_id": str(source_id),
                        "sql": record.get("sql", "") or record.get("expression", ""),
                    },
                )
            )
    return items


def load_schema_descriptions() -> list[ContextItem]:
    path = PUBLIC_DIR / "table_dictionary.csv"
    if not path.exists():
        return []

    by_table: dict[str, list[dict[str, str]]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            table_name = row.get("table_name", "")
            if not table_name:
                continue
            by_table.setdefault(table_name, []).append(row)

    items = []
    for table_name, rows in by_table.items():
        table_content = f"Table schema description: {table_name}\nFields: " + "; ".join(
            f"{row.get('column_name', '')}: {row.get('column_description', '')}"
            for row in rows[:40]
        )
        items.append(
            ContextItem(
                id=f"schema:{table_name}",
                content=table_content,
                metadata={
                    "type": "schema",
                    "domain": _infer_domain([table_name], []),
                    "difficulty": "unknown",
                    "table_names": [table_name],
                    "intent_tags": ["schema"],
                    "approved": True,
                    "source_id": table_name,
                },
            )
        )
        for row in rows:
            column_name = row.get("column_name", "")
            description = row.get("column_description", "")
            if not column_name or not description:
                continue
            items.append(
                ContextItem(
                    id=f"field:{table_name}.{column_name}",
                    content=f"Field description: {table_name}.{column_name} - {description}",
                    metadata={
                        "type": "field",
                        "domain": _infer_domain([table_name], []),
                        "difficulty": "unknown",
                        "table_names": [table_name],
                        "intent_tags": ["field"],
                        "approved": True,
                        "source_id": f"{table_name}.{column_name}",
                    },
                )
            )
    return items


def _load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.suffix.lower() == ".jsonl":
        records = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            records.append(json.loads(line))
        return records

    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        if isinstance(data.get("examples"), list):
            return data["examples"]
        if isinstance(data.get("items"), list):
            return data["items"]
        if isinstance(data.get("metrics"), list):
            return data["metrics"]
        return []
    return data if isinstance(data, list) else []


def _tables_from_join_strings(joins: Iterable[str]) -> list[str]:
    tables = []
    for join in joins:
        for side in str(join).replace("=", " ").split():
            if "." not in side:
                continue
            table = side.split(".", 1)[0].strip()
            if table and table not in tables:
                tables.append(table)
    return tables


def _infer_domain(tables: Iterable[str], tags: Iterable[str]) -> str:
    haystack = " ".join([*tables, *tags]).lower()
    if any(token in haystack for token in ["sales", "order", "shipment", "customer", "price"]):
        return "sales"
    if any(token in haystack for token in ["prod", "work_order", "bom", "machine", "energy"]):
        return "production"
    if any(token in haystack for token in ["qa", "quality", "defect", "inspection"]):
        return "quality"
    if any(token in haystack for token in ["inv", "inventory", "wh", "bin", "forecast"]):
        return "inventory"
    return "common"


def _chunks(items: list[ContextItem], size: int):
    for index in range(0, len(items), size):
        yield items[index:index + size]


if __name__ == "__main__":
    main()
