"""Regression tests for field-first schema retrieval."""

import unittest

from app.services.routing.context_builder import ContextBuilder
from app.services.routing.difficulty_router import PIPELINE_PROFILES


SCHEMA_INFO = [
    {
        "table_name": "dim_material",
        "columns": [
            {"name": "material_id", "type": "TEXT", "primary_key": True},
            {"name": "material_sku", "type": "TEXT"},
            {"name": "material_nm", "type": "TEXT"},
            {"name": "material_type_cd", "type": "TEXT"},
            {"name": "voltage_level", "type": "TEXT"},
            {"name": "color_cd", "type": "TEXT"},
        ],
        "sample_rows": [
            {
                "material_id": "M1",
                "material_sku": "SKU-001",
                "material_nm": "红色 220V 成品",
                "material_type_cd": "FG",
                "voltage_level": "220V",
                "color_cd": "RED",
            }
        ],
    },
    {
        "table_name": "dim_material_alias",
        "columns": [
            {"name": "alias_id", "type": "INTEGER"},
            {"name": "material_id", "type": "TEXT"},
            {"name": "alias_value", "type": "TEXT"},
            {"name": "alias_type_cd", "type": "TEXT"},
        ],
        "sample_rows": [{"alias_value": "220VAC", "alias_type_cd": "VOLTAGE"}],
    },
    {
        "table_name": "bridge_bom_component",
        "columns": [
            {"name": "bom_comp_id", "type": "INTEGER"},
            {"name": "bom_id", "type": "TEXT"},
            {"name": "component_material_id", "type": "TEXT"},
            {"name": "component_qty", "type": "REAL"},
        ],
        "sample_rows": [],
    },
]


class FieldSemanticRetrievalTest(unittest.TestCase):
    def test_material_color_voltage_prefers_main_table_fields(self) -> None:
        context = ContextBuilder().build_context_for_profile(
            "颜色为红色且电压为220V的成品有哪些？请返回物料编码和名称。",
            SCHEMA_INFO,
            PIPELINE_PROFILES["L2"],
        )

        self.assertEqual(context.table_names, ["dim_material"])
        self.assertIn("dim_material.voltage_level", context.selected_columns)
        self.assertIn("dim_material.color_cd", context.selected_columns)
        self.assertIn("dim_material.material_sku", context.selected_columns)
        self.assertIn("dim_material.material_nm", context.selected_columns)
        self.assertNotIn("dim_material_alias", context.table_names)
        self.assertNotIn("bridge_bom_component", context.table_names)
        self.assertIn("dim_material_alias suppressed", context.why_alias_table_selected)


if __name__ == "__main__":
    unittest.main()
