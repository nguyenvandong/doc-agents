import unittest

from doc_agents.models import ArtifactRef, ReviewTarget
from doc_agents.workflow import DocumentWorkflowState, WorkflowStatus


class ReviewArtifactUpdatesTest(unittest.TestCase):
    def test_ir_review_can_replace_data_schema_artifact_ref(self) -> None:
        state = DocumentWorkflowState.ready_for_ir_review(document_id="doc-1")
        state.artifacts["data_schema_json"] = ArtifactRef(
            artifact_id="doc-1-data_schema_json-v1",
            artifact_type="data_schema_json",
            version=1,
            uri="s3://doc-artifacts/doc-1/data_schema_json/v1/doc-1-data_schema_json-v1.bin",
        )
        replacement = ArtifactRef(
            artifact_id="doc-1-data_schema_json-v2",
            artifact_type="data_schema_json",
            version=2,
            uri="s3://doc-artifacts/doc-1/data_schema_json/v2/doc-1-data_schema_json-v2.bin",
        )

        state.apply_ir_artifact_update(ReviewTarget.DATA_SCHEMA, replacement)

        self.assertEqual(state.artifacts["data_schema_json"].version, 2)
        self.assertEqual(state.next_actions, ["rerun:synthesis"])
        self.assertEqual(state.status, WorkflowStatus.SYNTHESIS_READY)


if __name__ == "__main__":
    unittest.main()
