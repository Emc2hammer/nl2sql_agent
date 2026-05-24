"""Rule-based domain router for competition NL2SQL questions."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DomainRoute:
    """Routing result for a user question."""

    domain: str
    score: int
    matched_keywords: list[str]


ROUTE_RULES: dict[str, list[str]] = {
    "sales": ["订单", "客户", "销售", "金额", "有效订单", "客户细分", "履约", "交付", "取消", "置信度"],
    "product": ["物料", "成品", "sku", "bom", "组件", "颜色", "电压", "售价", "价格"],
    "production": ["产量", "生产线", "oee", "工单", "车间", "停机", "能耗"],
    "quality": ["检验", "拒收", "不良", "ppm", "缺陷", "质检"],
    "inventory": ["库存", "可用库存", "缺口", "预测量", "在手", "已分配", "库位", "仓库"],
    "supplier": ["供应商", "采购", "来料", "评分", "po"],
    "after_sales": ["售后", "索赔", "关闭", "案例", "满意度"],
}


def route_question(question: str) -> DomainRoute:
    """Route a question into the most likely business domain."""
    normalized = question.lower()
    best_domain = "general"
    best_matches: list[str] = []

    for domain, keywords in ROUTE_RULES.items():
        matches = [kw for kw in keywords if kw.lower() in normalized]
        if len(matches) > len(best_matches):
            best_domain = domain
            best_matches = matches

    return DomainRoute(
        domain=best_domain,
        score=len(best_matches),
        matched_keywords=best_matches,
    )
