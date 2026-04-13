import unittest

from doc_agents.models import ArtifactRef, ReviewDecision, ReviewTarget
from doc_agents.workflow import DocumentWorkflowState, WorkflowStatus


def artifact(name: str, version: int = 1) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=f"{name}-{version}",
        artifact_type=name,
        version=version,
        uri=f"memory://artifacts/{name}-{version}",
    )


class DocumentWorkflowStateTest(unittest.TestCase):
    def test_extraction_outputs_move_workflow_to_ir_review(self) -> None:
        state = DocumentWorkflowState.start(
            document_id="doc-1",
            source_uri="memory://source/doc-1",
        )
        state.record_chunk_set(artifact("semantic_chunks"))
        state.record_extraction_outputs(
            data_schema=artifact("data_schema_json"),
            business_rules=artifact("business_rules_json"),
            workflows=artifact("workflows_json"),
        )
        self.assertEqual(state.status, WorkflowStatus.WAITING_FOR_IR_REVIEW)

    def test_approve_ir_moves_to_synthesis_ready(self) -> None:
        state = DocumentWorkflowState.ready_for_ir_review(document_id="doc-1")
        state.apply_ir_review(ReviewDecision.approve(comment="ok"))
        self.assertEqual(state.status, WorkflowStatus.SYNTHESIS_READY)

    def test_markdown_comment_routes_only_synthesis(self) -> None:
        state = DocumentWorkflowState.ready_for_final_review(document_id="doc-1")
        state.apply_final_review(
            ReviewDecision.reject(
                comment="fix formatting",
                targets=[ReviewTarget.MARKDOWN_DRAFT],
            )
        )
        self.assertEqual(state.next_actions, ["rerun:synthesis"])

    def test_artifact_versions_returns_latest_versions_by_artifact_key(self) -> None:
        state = DocumentWorkflowState.ready_for_final_review(document_id="doc-1")
        state.artifacts["data_schema_json"] = artifact("data_schema_json", version=2)
        state.artifacts["markdown_draft"] = artifact("markdown_draft", version=3)

        self.assertEqual(
            state.artifact_versions,
            {
                "data_schema_json": 2,
                "markdown_draft": 3,
            },
        )


if __name__ == "__main__":
    unittest.main()
