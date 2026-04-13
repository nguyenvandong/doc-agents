import unittest

from doc_agents.models import IssueCategory, ReviewDecision, ReviewTarget
from doc_agents.workflow import DocumentWorkflowState


class SelectiveRerunRoutingTest(unittest.TestCase):
    def test_business_rule_comment_reruns_extraction_and_synthesis(self) -> None:
        state = DocumentWorkflowState.ready_for_final_review(document_id="doc-1")
        state.apply_final_review(
            ReviewDecision.reject(
                comment="business rule is missing",
                targets=[ReviewTarget.BUSINESS_RULES],
            )
        )
        self.assertEqual(
            state.next_actions,
            ["rerun:extract_business_rules", "rerun:synthesis"],
        )

    def test_issue_category_maps_to_expected_rerun_action(self) -> None:
        self.assertEqual(
            DocumentWorkflowState.action_for_issue(IssueCategory.PARSE_SOURCE_LOSS),
            "rerun:parse",
        )

    def test_review_event_log_keeps_history(self) -> None:
        state = DocumentWorkflowState.ready_for_ir_review(document_id="doc-1")
        state.apply_ir_review(
            ReviewDecision.reject(
                comment="schema incomplete",
                targets=[ReviewTarget.DATA_SCHEMA],
            )
        )
        self.assertEqual(state.review_history[-1].comment, "schema incomplete")


if __name__ == "__main__":
    unittest.main()
