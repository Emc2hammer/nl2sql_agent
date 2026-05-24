"""Deterministic logical plans used before SQL generation."""

from app.services.routing.context_builder import NL2SQLContext


class LogicalPlanBuilder:
    """Build a compact, business-aware plan without another model call."""

    def build(self, question: str, context: NL2SQLContext) -> str:
        if self._is_inventory_gap(question):
            return self._inventory_gap_plan()
        if "BOM" in question.upper() or "组件" in question:
            return self._bom_plan()
        if "最新" in question and "价格" in question:
            return self._latest_price_plan()
        if any(k in question for k in ["环比", "同比", "增长", "下降"]):
            return self._time_comparison_plan()
        if any(k in question for k in ["每个", "各", "分别"]) and any(k in question for k in ["最高", "最大", "前"]):
            return self._group_topn_plan()
        return self._generic_plan(context)

    def _is_inventory_gap(self, question: str) -> bool:
        return "库存缺口" in question or ("可用库存" in question and "预测" in question)

    def _inventory_gap_plan(self) -> str:
        return "\n".join(
            [
                "- Target metric: inventory_gap = forecast_qty - available_qty.",
                "- available_qty = on_hand_qty - alloc_qty from fact_inv_balance_snap.",
                "- Forecast grain is material_id + plant_id + month_key in fact_forecast_mth.",
                "- Inventory snapshot grain is material_id + wh_id + snap_dt_key; join dim_wh to map wh_id to plant_id.",
                "- Aggregate forecast and inventory separately at material_id + plant_id before joining facts.",
                "- Filter finished goods with dim_material.material_type_cd = 'FG' when the question asks for finished goods.",
                "- For month-end March 2025 use month_key = '202503' and snap_dt_key = '20250331'.",
                "- Rank by inventory_gap DESC and keep the top row when asking for the largest gap.",
            ]
        )

    def _bom_plan(self) -> str:
        return "\n".join(
            [
                "- Find the finished-good material in dim_material.",
                "- Join dim_bom_hdr by parent_material_id and require is_current_ver = 1 for current BOM.",
                "- Join bridge_bom_component by bom_id to get component_material_id and component_qty.",
                "- Join dim_material again with a separate alias for component names.",
            ]
        )

    def _latest_price_plan(self) -> str:
        return "\n".join(
            [
                "- Use fact_price_book as the price fact.",
                "- Filter eff_start_dt <= target date if a target date is present.",
                "- Select the latest valid row with MAX(eff_start_dt) or ROW_NUMBER ordered by eff_start_dt DESC.",
                "- Return unit_price_amt and related material/customer attributes requested by the question.",
            ]
        )

    def _time_comparison_plan(self) -> str:
        return "\n".join(
            [
                "- Aggregate the target metric by the requested time grain first.",
                "- Use LAG over the ordered time key for previous-period comparison.",
                "- Compute growth as current - previous and rate as division by previous with zero protection.",
            ]
        )

    def _group_topn_plan(self) -> str:
        return "\n".join(
            [
                "- Aggregate at the exact group grain requested by the question.",
                "- Use ROW_NUMBER() OVER (PARTITION BY group_key ORDER BY metric DESC) for top per group.",
                "- Do not use a global LIMIT as a substitute for per-group ranking.",
            ]
        )

    def _generic_plan(self, context: NL2SQLContext) -> str:
        table_hint = ", ".join(context.table_names[:4]) or "retrieved tables"
        return "\n".join(
            [
                f"- Use the retrieved tables: {table_hint}.",
                "- Apply matched business rules before aggregation.",
                "- Join only through retrieved join paths.",
                "- Keep the result grain aligned with the question.",
            ]
        )
