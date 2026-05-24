import unittest
from types import SimpleNamespace

from app.services.knowledge.validated_template_service import ValidatedTemplateService


def make_context():
    return SimpleNamespace(table_names=["dim_item"], patterns=[])


def make_template(**overrides):
    template = {
        "id": "T001",
        "question": "Show item ABC-100 in month 202503",
        "pattern": "lookup_by_identifier_and_month",
        "tables": ["dim_item"],
        "sql": "SELECT item_code FROM dim_item WHERE item_code = 'ABC-100' AND month_key = '202503';",
        "source": "approved_template",
        "approved": True,
    }
    template.update(overrides)
    return template


class ValidatedTemplateServiceTest(unittest.TestCase):
    def test_default_disabled_hit_must_not_skip_llm(self) -> None:
        service = ValidatedTemplateService(templates=[make_template()])

        decision = service.decide(
            "Show item XYZ-200 in month 202504",
            make_context(),
            enable_reuse=False,
            threshold=0.95,
        )

        self.assertTrue(decision.template_reuse_checked)
        self.assertTrue(decision.template_reuse_hit)
        self.assertFalse(decision.template_reuse_allowed)
        self.assertEqual(decision.template_reuse_reason, "template_reuse_disabled")
        self.assertIsNotNone(decision.retrieved_example)
        self.assertIn("item_code = 'XYZ-200'", decision.sql)

    def test_question_bank_source_never_skips_llm(self) -> None:
        service = ValidatedTemplateService(
            templates=[make_template(source="question_bank", approved=True)]
        )

        decision = service.decide(
            "Show item XYZ-200 in month 202504",
            make_context(),
            enable_reuse=True,
            threshold=0.1,
        )

        self.assertTrue(decision.template_reuse_hit)
        self.assertFalse(decision.template_reuse_allowed)
        self.assertEqual(decision.template_reuse_reason, "source_not_allowed:question_bank")

    def test_approved_template_above_threshold_can_skip_llm(self) -> None:
        service = ValidatedTemplateService(templates=[make_template()])

        decision = service.decide(
            "Show item ABC-100 in month 202503",
            make_context(),
            enable_reuse=True,
            threshold=0.95,
        )

        self.assertTrue(decision.template_reuse_hit)
        self.assertTrue(decision.template_reuse_allowed)
        self.assertEqual(decision.template_reuse_reason, "approved_template_reused")
        self.assertEqual(decision.template_id, "T001")
        self.assertGreaterEqual(decision.template_score, 0.95)

    def test_low_similarity_question_has_no_hit(self) -> None:
        service = ValidatedTemplateService(templates=[make_template()])

        decision = service.decide(
            "Compare supplier quality score by quarter",
            make_context(),
            enable_reuse=True,
            threshold=0.95,
        )

        self.assertFalse(decision.template_reuse_hit)
        self.assertFalse(decision.template_reuse_allowed)
        self.assertEqual(decision.template_reuse_reason, "no_template_candidate")


if __name__ == "__main__":
    unittest.main()
