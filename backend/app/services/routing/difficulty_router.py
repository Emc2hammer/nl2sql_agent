"""Difficulty-aware routing for NL2SQL pipeline selection."""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


BACKEND_DIR = Path(__file__).resolve().parents[2]
QUESTION_BANK_PATH = BACKEND_DIR / "data" / "nl2sqlpublic" / "public" / "question_bank.json"


@dataclass(frozen=True)
class PipelineProfile:
    """Execution knobs for one difficulty level."""

    level: str
    label: str
    table_top_k: int
    max_columns_per_table: int
    max_joins: int
    max_rules: int
    few_shot_top_k: int
    use_planner: bool
    use_repair: bool


PIPELINE_PROFILES: dict[str, PipelineProfile] = {
    "L1": PipelineProfile("L1", "SIMPLE", 3, 8, 3, 2, 1, False, False),
    "L2": PipelineProfile("L2", "MEDIUM", 6, 12, 8, 5, 2, False, True),
    "L3": PipelineProfile("L3", "HARD", 8, 14, 10, 6, 3, True, True),
    "L4": PipelineProfile("L4", "EXPERT", 8, 16, 12, 8, 3, True, True),
}


@dataclass(frozen=True)
class DifficultyDecision:
    """Difficulty classification result."""

    level: str
    label: str
    reasons: list[str]
    profile: PipelineProfile


class DifficultyRouter:
    """Classify a question into a lightweight or heavyweight NL2SQL pipeline."""

    def __init__(self) -> None:
        self.bank_patterns = self._load_question_bank_patterns()

    def classify(self, question: str) -> DifficultyDecision:
        """Classify question difficulty using heuristics aligned to question_bank features."""
        reasons: list[str] = []
        bank_level = self._match_question_bank_features(question)
        heuristic_level, heuristic_reasons = self._classify_by_rules(question)
        reasons.extend(heuristic_reasons)

        # Feature matching is intentionally only a fallback; exact question text in
        # the public file may be encoding-sensitive, while Chinese keywords from the
        # user input are reliable at runtime.
        if heuristic_level == "L1" and bank_level:
            level = bank_level
            reasons.append(f"question_bank feature fallback: {bank_level}")
        else:
            level = heuristic_level
        profile = PIPELINE_PROFILES[level]
        return DifficultyDecision(
            level=profile.level,
            label=profile.label,
            reasons=reasons or ["default simple lookup"],
            profile=profile,
        )

    def _load_question_bank_patterns(self) -> list[tuple[str, list[str], list[str]]]:
        if not QUESTION_BANK_PATH.exists():
            return []
        try:
            data = json.loads(QUESTION_BANK_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []

        patterns = []
        for item in data:
            patterns.append(
                (
                    item.get("difficulty", ""),
                    item.get("sql_features", []) or [],
                    item.get("intent_tags", []) or [],
                )
            )
        return patterns

    def _match_question_bank_features(self, question: str) -> Optional[str]:
        """Use official feature taxonomy as a weak fallback signal."""
        feature_hits = []
        q_lower = question.lower()

        if any(k in question for k in ["环比", "同比", "增长", "趋势"]):
            feature_hits.extend(["lag", "cte"])
        if any(k in question for k in ["排名", "前3", "前5"]) or "top" in q_lower:
            feature_hits.extend(["ranking", "order_by"])
        if any(k in question for k in ["每个", "每月", "分别"]):
            feature_hits.append("group_by")
        if any(k in question for k in ["拒收率", "平均", "占比"]):
            feature_hits.extend(["computed_metric", "derived_metric"])
        if any(k in question for k in ["最新", "当前", "BOM", "组件", "有效订单", "可用库存"]):
            feature_hits.extend(["business_rule", "join"])
        if "window" in q_lower or "窗口" in question:
            feature_hits.append("window_function")

        if not feature_hits:
            return None

        best_level = None
        best_score = 0
        for difficulty, features, tags in self.bank_patterns:
            searchable = set(features + tags)
            score = sum(1 for hit in feature_hits if hit in searchable)
            if score > best_score:
                best_level = difficulty
                best_score = score
        return best_level

    def _classify_by_rules(self, question: str) -> tuple[str, list[str]]:
        reasons = []
        level = "L1"

        if any(k in question for k in ["环比", "同比", "增长", "趋势", "月环比"]):
            level = "L3"
            reasons.append("time-series comparison")

        if any(k in question for k in ["拒收率", "占比", "平均", "均值"]):
            level = self._max_level([level, "L3"])
            reasons.append("derived metric")

        if any(k in question for k in ["每个", "每月", "各", "分别"]) and any(
            k in question for k in ["最高", "最低", "前3", "前5", "排名"]
        ):
            level = self._max_level([level, "L3"])
            reasons.append("grouped ranking")

        if any(k in question for k in ["每个客户细分中", "每个月有效订单金额最高", "全体平均", "超过当月"]):
            level = self._max_level([level, "L4"])
            reasons.append("nested or top-n-by-group analysis")

        if any(k in question for k in ["库存缺口", "分厂预测量", "可用库存"]) and any(
            k in question for k in ["最大", "最高", "末"]
        ):
            level = self._max_level([level, "L4"])
            reasons.append("inventory gap requires multi-fact aggregation")

        if any(k in question for k in ["缺口", "当前BOM", "BOM", "组件", "最新", "有效订单", "可用库存", "EAV"]):
            level = self._max_level([level, "L2"])
            reasons.append("business rule required")

        if any(k in question for k in ["仍未关闭", "相关子查询", "correlated"]):
            level = self._max_level([level, "L4"])
            reasons.append("correlated or multi-hop reasoning")

        if re.search(r"(count|sum|avg|top|rank)", question, re.IGNORECASE):
            level = self._max_level([level, "L2"])
            reasons.append("explicit SQL analytic keyword")

        return level, reasons

    def _max_level(self, levels: list[Optional[str]]) -> str:
        order = {"L1": 1, "L2": 2, "L3": 3, "L4": 4}
        valid = [level for level in levels if level in order]
        if not valid:
            return "L1"
        return max(valid, key=lambda item: order[item])
