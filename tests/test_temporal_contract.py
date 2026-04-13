import unittest

from doc_agents.temporal_contract import (
    ACTIVITY_NAMES,
    REVIEW_SIGNAL_NAMES,
    build_workflow_start_payload,
)


class TemporalContractTest(unittest.TestCase):
    def test_contract_exposes_expected_activity_names(self) -> None:
        self.assertIn("parse_docx_activity", ACTIVITY_NAMES)
        self.assertIn("validate_markdown_against_chunks_activity", ACTIVITY_NAMES)

    def test_review_signal_names_cover_both_review_gates(self) -> None:
        self.assertEqual(
            REVIEW_SIGNAL_NAMES,
            {
                "ir_review_submitted": "ir_review_submitted",
                "ir_artifact_updated": "ir_artifact_updated",
                "final_review_submitted": "final_review_submitted",
            },
        )

    def test_start_payload_keeps_document_identity_small(self) -> None:
        payload = build_workflow_start_payload(
            document_id="doc-1",
            source_uri="memory://source/doc-1",
        )
        self.assertEqual(payload["document_id"], "doc-1")
        self.assertNotIn("raw_document", payload)


if __name__ == "__main__":
    unittest.main()
