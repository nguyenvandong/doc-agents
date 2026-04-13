import unittest

from doc_agents.models import ReviewTarget
from doc_agents.temporal_payloads import (
    ArtifactReviewUpdatePayload,
    ReviewSubmission,
    WorkflowStartInput,
)


class TemporalPayloadsTest(unittest.TestCase):
    def test_review_submission_maps_to_core_decision(self) -> None:
        submission = ReviewSubmission(
            action="reject",
            comment="missing rules",
            targets=[ReviewTarget.BUSINESS_RULES.value],
        )
        decision = submission.to_core_decision()
        self.assertEqual(decision.action, "reject")
        self.assertEqual(decision.comment, "missing rules")
        self.assertEqual(decision.targets, [ReviewTarget.BUSINESS_RULES])

    def test_workflow_start_input_exposes_workflow_id(self) -> None:
        payload = WorkflowStartInput(
            document_id="doc-42",
            source_uri="memory://source/doc-42",
        )
        self.assertEqual(payload.workflow_id, "document-workflow-doc-42")

    def test_artifact_review_update_payload_maps_to_artifact_ref(self) -> None:
        payload = ArtifactReviewUpdatePayload(
            target=ReviewTarget.DATA_SCHEMA.value,
            artifact_id="doc-42-data_schema_json-v2",
            artifact_type="data_schema_json",
            version=2,
            uri="s3://doc-artifacts/doc-42/data_schema_json/v2/doc-42-data_schema_json-v2.bin",
        )

        self.assertEqual(payload.target_enum(), ReviewTarget.DATA_SCHEMA)
        self.assertEqual(payload.to_artifact_ref().version, 2)


if __name__ == "__main__":
    unittest.main()
