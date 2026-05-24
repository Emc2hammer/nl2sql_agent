"""Regression tests for EMPTY_RESULT condition attribution."""

import sqlite3
import unittest

from app.services.quality.empty_result_diagnoser import EmptyResultDiagnoser


class SqliteProbeService:
    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE dim_material (
                material_id INTEGER PRIMARY KEY,
                material_sku TEXT,
                material_nm TEXT,
                color_cd TEXT,
                material_type_cd TEXT,
                is_active_fg INTEGER
            );
            CREATE TABLE dim_material_alias (
                alias_id INTEGER PRIMARY KEY,
                material_id INTEGER,
                alias_value TEXT,
                alias_type_cd TEXT
            );
            INSERT INTO dim_material VALUES
                (1, 'M-001', 'Red finished motor', 'RED', 'FG', 1),
                (2, 'M-002', 'Blue finished motor', 'BLUE', 'FG', 1);
            INSERT INTO dim_material_alias VALUES
                (1, 1, '220VAC', 'RATED_VOLTAGE'),
                (2, 1, 'AC220V', 'RATED_VOLTAGE'),
                (3, 2, '110VAC', 'RATED_VOLTAGE');
            """
        )

    def execute_query(self, sql: str) -> dict:
        try:
            cursor = self.conn.execute(sql)
            rows = [dict(row) for row in cursor.fetchmany(200)]
            return {"rows": rows, "columns": [item[0] for item in cursor.description or []], "error": None}
        except Exception as exc:
            return {"rows": [], "columns": [], "error": str(exc)}


SCHEMA_INFO = [
    {
        "table_name": "dim_material",
        "columns": [
            {"name": "material_id"},
            {"name": "material_sku"},
            {"name": "material_nm"},
            {"name": "color_cd"},
            {"name": "material_type_cd"},
            {"name": "is_active_fg"},
        ],
    },
    {
        "table_name": "dim_material_alias",
        "columns": [
            {"name": "alias_id"},
            {"name": "material_id"},
            {"name": "alias_value"},
            {"name": "alias_type_cd"},
        ],
    },
]


class EmptyResultDiagnoserTest(unittest.TestCase):
    def test_diagnoses_zero_count_conditions_and_resolves_voltage_candidates(self) -> None:
        sql = """
        SELECT DISTINCT m.material_sku, m.material_nm
        FROM dim_material m
        JOIN dim_material_alias a ON m.material_id = a.material_id
        WHERE m.color_cd = 'RED'
          AND m.material_type_cd = 'FG'
          AND m.is_active_fg = 1
          AND a.alias_value = '220V'
          AND a.alias_type_cd = 'VOLTAGE'
        LIMIT 200;
        """
        diagnoser = EmptyResultDiagnoser(SqliteProbeService())
        diagnosis = diagnoser.diagnose(
            question="颜色为红色且电压为220V的成品有哪些？请返回物料编码和名称。",
            generated_sql=sql,
            selected_tables=["dim_material", "dim_material_alias"],
            schema_info=SCHEMA_INFO,
            enable_value_resolver=True,
        )

        suspect_columns = {
            f"{item['table']}.{item['column']}" for item in diagnosis["suspect_conditions"]
        }
        self.assertIn("dim_material_alias.alias_value", suspect_columns)
        self.assertIn("dim_material_alias.alias_type_cd", suspect_columns)
        self.assertNotIn("dim_material.color_cd", suspect_columns)

        candidate_values = []
        for result in diagnosis["value_probe_results"]:
            if result["table"] == "dim_material_alias" and result["column"] == "alias_value":
                candidate_values.extend(result["candidates"])
        self.assertIn("220VAC", candidate_values)
        self.assertIn("AC220V", candidate_values)
        self.assertIn("不要改变 SELECT 目标字段", diagnosis["retry_advice"])
        self.assertTrue(diagnosis["allow_retry"])


if __name__ == "__main__":
    unittest.main()
