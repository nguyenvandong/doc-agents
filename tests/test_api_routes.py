import unittest

from fastapi.testclient import TestClient

from doc_agents.api import app, get_workflow_api_service
from doc_agents.api_models import (
    ReviewResponse,
    StartWorkflowResponse,
    WorkflowSnapshotResponse,
    WorkflowStatusResponse,
)


class FakeWorkflowApiService:
    def __init__(self, mode: str = "ok") -> None:
        self.mode = mode

    async def start_workflow(self, request):
        if self.mode == "conflict":
            from doc_agents.api_service import WorkflowConflictError

            raise WorkflowConflictError("document-workflow-doc-123")
        return StartWorkflowResponse(
            workflow_id="document-workflow-doc-123",
            document_id="doc-123",
            status="started",
        )

    async def get_status(self, document_id: str):
        if self.mode == "not-found":
            from doc_agents.api_service import WorkflowNotFoundError

            raise WorkflowNotFoundError("document-workflow-doc-123")
        return WorkflowStatusResponse(
            workflow_id="document-workflow-doc-123",
            document_id=document_id,
            status="waiting_for_ir_review",
        )

    async def get_snapshot(self, document_id: str):
        if self.mode == "unavailable":
            from doc_agents.api_service import TemporalUnavailableError

            raise TemporalUnavailableError()
        return WorkflowSnapshotResponse(
            workflow_id="document-workflow-doc-123",
            document_id=document_id,
            status="waiting_for_ir_review",
            next_actions=[],
            artifact_versions={"semantic_chunks": 1},
        )

    async def submit_ir_review(self, document_id: str, request):
        return ReviewResponse(document_id=document_id, accepted=True, signal="ir_review_submitted")

    async def submit_final_review(self, document_id: str, request):
        return ReviewResponse(document_id=document_id, accepted=True, signal="final_review_submitted")

    async def submit_ir_artifact_update(self, document_id: str, request):
        return ReviewResponse(document_id=document_id, accepted=True, signal="ir_artifact_updated")


class ApiRoutesTest(unittest.TestCase):
    def setUp(self) -> None:
        app.dependency_overrides[get_workflow_api_service] = lambda: FakeWorkflowApiService()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_post_workflows_start_returns_started_payload(self) -> None:
        response = self.client.post(
            "/workflows/start",
            json={
                "document_id": "doc-123",
                "source_uri": "file:///tmp/source.docx",
            },
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["workflow_id"], "document-workflow-doc-123")

    def test_get_snapshot_returns_artifact_versions(self) -> None:
        response = self.client.get("/workflows/doc-123/snapshot")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["artifact_versions"], {"semantic_chunks": 1})

    def test_post_ir_artifact_update_returns_signal_name(self) -> None:
        response = self.client.post(
            "/workflows/doc-123/artifacts/ir-update",
            json={
                "target": "data_schema",
                "artifact_id": "doc-123-data_schema_json-v2",
                "artifact_type": "data_schema_json",
                "version": 2,
                "uri": "s3://doc-artifacts/doc-123/data_schema_json/v2/doc-123-data_schema_json-v2.bin",
            },
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["signal"], "ir_artifact_updated")

    def test_post_workflows_start_returns_409_on_conflict(self) -> None:
        app.dependency_overrides[get_workflow_api_service] = lambda: FakeWorkflowApiService(mode="conflict")
        response = self.client.post(
            "/workflows/start",
            json={
                "document_id": "doc-123",
                "source_uri": "file:///tmp/source.docx",
            },
        )
        self.assertEqual(response.status_code, 409)

    def test_get_status_returns_404_when_workflow_is_missing(self) -> None:
        app.dependency_overrides[get_workflow_api_service] = lambda: FakeWorkflowApiService(mode="not-found")
        response = self.client.get("/workflows/doc-123/status")
        self.assertEqual(response.status_code, 404)

    def test_get_snapshot_returns_503_when_temporal_is_unavailable(self) -> None:
        app.dependency_overrides[get_workflow_api_service] = lambda: FakeWorkflowApiService(mode="unavailable")
        response = self.client.get("/workflows/doc-123/snapshot")
        self.assertEqual(response.status_code, 503)

    def test_post_ir_artifact_update_returns_400_for_business_rule_validation(self) -> None:
        response = self.client.post(
            "/workflows/doc-123/artifacts/ir-update",
            json={
                "target": "data_schema",
                "artifact_id": "doc-123-business_rules_json-v2",
                "artifact_type": "business_rules_json",
                "version": 2,
                "uri": "s3://doc-artifacts/doc-123/business_rules_json/v2/doc-123-business_rules_json-v2.bin",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_main_exports_fastapi_app(self) -> None:
        from main import app as main_app

        self.assertIs(main_app, app)


if __name__ == "__main__":
    unittest.main()
