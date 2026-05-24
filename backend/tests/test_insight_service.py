import unittest

from app.services.quality.insight_service import InsightService


class InsightServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = InsightService()

    def test_bom_component_analysis_uses_domain_insights(self) -> None:
        rows = [
            {
                "component_material_id": "MAT_RM_2001",
                "component_name": "控制板组件",
                "component_qty_per_unit": 1,
            },
            {
                "component_material_id": "MAT_RM_2002",
                "component_name": "控制器外壳",
                "component_qty_per_unit": 1,
            },
            {
                "component_material_id": "MAT_RM_2003",
                "component_name": "线束组件",
                "component_qty_per_unit": 1,
            },
            {
                "component_material_id": "MAT_RM_2005",
                "component_name": "包装箱",
                "component_qty_per_unit": 1,
            },
        ]

        insights = self.service.generate(
            rows,
            ["component_material_id", "component_name", "component_qty_per_unit"],
        )
        joined = "\n".join(insights)

        self.assertIn("当前 BOM 共包含 4 类组件，每生产 1 台需要组件总用量 4 个。", insights)
        self.assertIn("各组件用量一致，均为 1 个/台。", insights)
        self.assertIn("组件包括：控制板组件、控制器外壳、线束组件、包装箱。", insights)
        self.assertNotIn("领先第二名", joined)
        self.assertNotIn("最高值占", joined)

    def test_single_row_single_column_uses_simple_result_text(self) -> None:
        insights = self.service.generate(
            [{"sales_order_count": 12864}],
            ["sales_order_count"],
        )

        self.assertEqual(insights, ["查询结果：sales_order_count = 12864"])

    def test_topn_query_uses_ranking_insights(self) -> None:
        rows = [
            {"customer_name": "A", "net_amt": 100},
            {"customer_name": "B", "net_amt": 70},
        ]

        insights = self.service.generate(
            rows,
            ["customer_name", "net_amt"],
            question="Top 2 customers by net amount",
        )
        joined = "\n".join(insights)

        self.assertIn("最高", joined)
        self.assertIn("领先第二名", joined)
        self.assertIn("最高值占", joined)


if __name__ == "__main__":
    unittest.main()
