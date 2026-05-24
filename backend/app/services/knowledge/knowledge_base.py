"""Local NL2SQL knowledge base loaders and lexical retrieval helpers."""

import json
import re
from pathlib import Path
from typing import Any, Optional


BACKEND_DIR = Path(__file__).resolve().parents[2]
KNOWLEDGE_DIR = BACKEND_DIR / "data" / "knowledge"
BUSINESS_RULES_PATH = KNOWLEDGE_DIR / "business_rules.json"
SQL_PATTERNS_PATH = KNOWLEDGE_DIR / "sql_patterns.json"
FEW_SHOTS_PATH = KNOWLEDGE_DIR / "few_shots.json"


def load_json_list(path: Path) -> list[dict[str, Any]]:
    """Load a JSON list from disk. Return an empty list on missing/invalid data."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def lexical_score(question: str, document: str, keywords: Optional[list[str]] = None) -> int:
    """Simple mixed Chinese/identifier lexical score."""
    score = 0
    normalized_doc = document.lower()
    normalized_question = question.lower()

    for keyword in keywords or []:
        if keyword and keyword.lower() in normalized_question:
            score += 8

    for term in re.findall(r"[A-Za-z0-9_]+", normalized_question):
        if len(term) > 1 and term in normalized_doc:
            score += 2

    for token in _known_chinese_terms(question):
        if token in document:
            score += 3

    return score


def _known_chinese_terms(question: str) -> list[str]:
    return [
        term
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
            "BOM",
            "最新",
            "当前",
            "环比",
            "增长",
            "排名",
            "前3",
            "每个",
        ]
        if term in question
    ]
