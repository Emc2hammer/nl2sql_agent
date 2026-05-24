"""Lightweight result sanity checks after SQL execution."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ResultWarning:
    code: str
    message: str


class ResultSanityChecker:
    """Detect suspicious but not necessarily fatal query results."""

    def check(self, rows: list[dict[str, Any]], columns: list[str]) -> list[ResultWarning]:
        warnings: list[ResultWarning] = []
        if not rows:
            return [ResultWarning("empty_result", "SQL 执行成功但结果为空，需要检查过滤条件或数据范围。")]

        for column in columns:
            values = [row.get(column) for row in rows if isinstance(row.get(column), (int, float))]
            if not values:
                continue
            lowered = column.lower()
            if "rate" in lowered or "率" in column:
                out_of_range = [value for value in values if value < 0 or value > 1]
                if out_of_range:
                    warnings.append(ResultWarning("rate_out_of_range", f"{column} 出现不在 0 到 1 之间的值，需确认是否是百分比口径。"))
            if "ppm" in lowered and any(value < 0 for value in values):
                warnings.append(ResultWarning("negative_ppm", f"{column} 出现负值，PPM 指标通常不应为负。"))
            if max(values) > 0 and min(values) < 0 and ("qty" in lowered or "数量" in column):
                warnings.append(ResultWarning("mixed_sign_quantity", f"{column} 同时存在正负值，需确认是否包含退货/冲销场景。"))

        return warnings

    def format_warnings(self, warnings: list[ResultWarning]) -> str:
        if not warnings:
            return "No result sanity warnings."
        return "\n".join(f"- {warning.code}: {warning.message}" for warning in warnings)
