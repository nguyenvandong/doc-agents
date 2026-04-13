import json
from pathlib import Path
import tempfile
import unittest

from doc_agents.activities import configure_activity_dependencies
from temporalio.client import WorkflowHandle
from temporalio.testing import WorkflowEnvironment

from doc_agents.models import ReviewTarget
from doc_agents.temporal_payloads import (
    ArtifactReviewUpdatePayload,
    ReviewSubmission,
    WorkflowStartInput,
)
from doc_agents.temporal_runtime import create_worker
from doc_agents.temporal_workflow import TemporalDocumentWorkflow
from doc_agents.workflow import WorkflowStatus
from tests.test_activity_parser_integration import (
    FakeArtifactRepository,
    build_docx_file,
)


class TemporalIntegrationTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.repository = FakeArtifactRepository()
        configure_activity_dependencies(artifact_repository=self.repository)
        self._temp_dir = tempfile.TemporaryDirectory()
        self._source_path = Path(self._temp_dir.name) / "source.docx"
        build_docx_file(self._source_path)

    def tearDown(self) -> None:
        configure_activity_dependencies(artifact_repository=None)
        self._temp_dir.cleanup()

    async def test_workflow_can_pause_for_reviews_and_complete(self) -> None:
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with create_worker(env.client, task_queue="doc-agents-test"):
                handle: WorkflowHandle = await env.client.start_workflow(
                    TemporalDocumentWorkflow.run,
                    WorkflowStartInput(
                        document_id="doc-integration",
                        source_uri=str(self._source_path),
                    ),
                    id="document-workflow-doc-integration",
                    task_queue="doc-agents-test",
                )

                status = await handle.query(TemporalDocumentWorkflow.current_status)
                for _ in range(10):
                    if status == WorkflowStatus.WAITING_FOR_IR_REVIEW.value:
                        break
                    await env.sleep(1)
                    status = await handle.query(TemporalDocumentWorkflow.current_status)
                self.assertEqual(status, WorkflowStatus.WAITING_FOR_IR_REVIEW.value)

                await handle.signal(
                    TemporalDocumentWorkflow.submit_ir_review,
                    ReviewSubmission(action="approve", comment="ir ok", targets=[]),
                )
                await handle.signal(
                    TemporalDocumentWorkflow.submit_final_review,
                    ReviewSubmission(
                        action="approve",
                        comment="final ok",
                        targets=[ReviewTarget.MARKDOWN_DRAFT.value],
                    ),
                )

                result = await handle.result()
                self.assertEqual(result.status, WorkflowStatus.COMPLETED.value)

    async def test_workflow_snapshot_exposes_version_growth_after_markdown_rerun(self) -> None:
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with create_worker(env.client, task_queue="doc-agents-test"):
                handle: WorkflowHandle = await env.client.start_workflow(
                    TemporalDocumentWorkflow.run,
                    WorkflowStartInput(
                        document_id="doc-rerun",
                        source_uri=str(self._source_path),
                    ),
                    id="document-workflow-doc-rerun",
                    task_queue="doc-agents-test",
                )

                status = await handle.query(TemporalDocumentWorkflow.current_status)
                for _ in range(10):
                    if status == WorkflowStatus.WAITING_FOR_IR_REVIEW.value:
                        break
                    await env.sleep(1)
                    status = await handle.query(TemporalDocumentWorkflow.current_status)
                self.assertEqual(status, WorkflowStatus.WAITING_FOR_IR_REVIEW.value)

                await handle.signal(
                    TemporalDocumentWorkflow.submit_ir_review,
                    ReviewSubmission(action="approve", comment="ir ok", targets=[]),
                )
                await handle.signal(
                    TemporalDocumentWorkflow.submit_final_review,
                    ReviewSubmission(
                        action="reject",
                        comment="rerun markdown",
                        targets=[ReviewTarget.MARKDOWN_DRAFT.value],
                    ),
                )

                await env.sleep(1)
                snapshot = await handle.query(TemporalDocumentWorkflow.snapshot)
                self.assertIn("markdown_draft", snapshot.artifact_versions)
                self.assertGreaterEqual(snapshot.artifact_versions["markdown_draft"], 2)

    async def test_ir_artifact_update_uses_replacement_ref_without_rerunning_extraction(self) -> None:
        async with await WorkflowEnvironment.start_time_skipping() as env:
            async with create_worker(env.client, task_queue="doc-agents-test"):
                handle: WorkflowHandle = await env.client.start_workflow(
                    TemporalDocumentWorkflow.run,
                    WorkflowStartInput(
                        document_id="doc-ir-update",
                        source_uri=str(self._source_path),
                    ),
                    id="document-workflow-doc-ir-update",
                    task_queue="doc-agents-test",
                )

                status = await handle.query(TemporalDocumentWorkflow.current_status)
                for _ in range(10):
                    if status == WorkflowStatus.WAITING_FOR_IR_REVIEW.value:
                        break
                    await env.sleep(1)
                    status = await handle.query(TemporalDocumentWorkflow.current_status)
                self.assertEqual(status, WorkflowStatus.WAITING_FOR_IR_REVIEW.value)

                replacement = self.repository.store_bytes(
                    workflow_id="doc-ir-update",
                    document_id="doc-ir-update",
                    artifact_type="data_schema_json",
                    payload=json.dumps(
                        {
                            "source_chunk_artifact_id": "doc-ir-update-semantic_chunks-v1",
                            "fields": [{"name": "Customer ID", "source_chunk_id": "chunk-0"}],
                            "evidence": ["Customer ID"],
                        }
                    ).encode("utf-8"),
                    content_type="application/json",
                    version=2,
                )

                await handle.signal(
                    TemporalDocumentWorkflow.submit_ir_artifact_update,
                    ArtifactReviewUpdatePayload(
                        target=ReviewTarget.DATA_SCHEMA.value,
                        artifact_id=replacement.artifact_id,
                        artifact_type=replacement.artifact_type,
                        version=replacement.version,
                        uri=replacement.uri,
                    ),
                )

                for _ in range(10):
                    if await handle.query(TemporalDocumentWorkflow.current_status) == WorkflowStatus.WAITING_FOR_FINAL_REVIEW.value:
                        break
                    await env.sleep(1)
                snapshot = await handle.query(TemporalDocumentWorkflow.snapshot)
                self.assertEqual(snapshot.artifact_versions["data_schema_json"], 2)

                await handle.signal(
                    TemporalDocumentWorkflow.submit_final_review,
                    ReviewSubmission(
                        action="approve",
                        comment="replacement accepted",
                        targets=[ReviewTarget.MARKDOWN_DRAFT.value],
                    ),
                )

                result = await handle.result()
                self.assertEqual(result.status, WorkflowStatus.COMPLETED.value)


if __name__ == "__main__":
    unittest.main()
