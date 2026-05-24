"""Mock tests for supervisor reflection JSON parsing and fallback."""

import unittest

from app.core.tracing import RequestTrace, TraceStep
from app.services.quality.reflection_service import ReflectionService


class FakeSupervisor:
    model = "qwen3.5-35b-a3b"
    is_configured = True

    def __init__(self, raw_output: str) -> None:
        self.raw_output = raw_output
        self.calls = 0

    def reflect(self, system_prompt: str, user_payload: str) -> str:
        self.calls += 1
        return self.raw_output


def make_trace() -> RequestTrace:
    return RequestTrace(
        trace_id="test-trace",
        request_path="/api/chat",
        question="count sales orders",
        started_at="2026-05-12T00:00:00+00:00",
        steps=[
            TraceStep(
                name="context_builder",
                output={
                    "route": {"domain": "sales"},
                    "tables": [
                        {
                            "name": "fact_sales_order_hdr",
                            "description": "sales order header",
                            "columns": [{"name": "sales_order_id"}],
                        }
                    ],
                    "rules": [],
                    "joins": [],
                    "patterns": [],
                    "linked_columns": [],
                },
            ),
            TraceStep(name="nl2sql_service", output="SELECT missing_col FROM fact_sales_order_hdr"),
            TraceStep(
                name="query_service",
                input={"sql": "SELECT missing_col FROM fact_sales_order_hdr"},
                output={"rows": [], "columns": [], "error": "no such column: missing_col"},
            ),
        ],
    )


class ReflectionSupervisorMockTest(unittest.TestCase):
    def test_supervisor_valid_json_overrides_rule_result(self) -> None:
        supervisor = FakeSupervisor(
            """
            {
              "error_type": "WRONG_JOIN",
              "root_cause_step": "query_service",
              "reason": "The SQL used the wrong grain.",
              "repair_suggestion": "Use the retrieved join path and aggregate first.",
              "should_retry": true
            }
            """
        )
        trace = make_trace()
        result = ReflectionService(supervisor).reflect(trace)

        self.assertEqual(result.error_type, "WRONG_JOIN")
        self.assertEqual(result.root_cause_step, "query_service")
        self.assertTrue(result.should_retry)
        self.assertEqual(supervisor.calls, 1)
        supervisor_steps = [step for step in trace.steps if step.name == "supervisor_llm_service"]
        self.assertEqual(len(supervisor_steps), 1)
        self.assertEqual(supervisor_steps[0].status, "success")
        self.assertEqual(supervisor_steps[0].output["supervisor_model"], "qwen3.5-35b-a3b")

    def test_supervisor_invalid_json_falls_back_to_rules(self) -> None:
        supervisor = FakeSupervisor("not json")
        trace = make_trace()
        result = ReflectionService(supervisor).reflect(trace)

        self.assertEqual(result.error_type, "SCHEMA_FIELD_ERROR")
        self.assertEqual(result.root_cause_step, "query_service")
        self.assertTrue(result.should_retry)
        self.assertEqual(supervisor.calls, 1)
        supervisor_steps = [step for step in trace.steps if step.name == "supervisor_llm_service"]
        self.assertEqual(len(supervisor_steps), 1)
        self.assertEqual(supervisor_steps[0].status, "error")
        self.assertIn("supervisor_raw_output_preview", supervisor_steps[0].output)
        self.assertIn("supervisor_raw_output_len", supervisor_steps[0].output)


if __name__ == "__main__":
    unittest.main()
