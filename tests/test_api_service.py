import unittest

from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from doc_agents.api_models import ArtifactUpdateRequest, StartWorkflowRequest
from doc_agents.api_service import (
    TemporalUnavailableError,
    WorkflowApiService,
    WorkflowConflictError,
    WorkflowNotFoundError,
)
from doc_agents.api_settings import ApiSettings
from doc_agents.temporal_payloads import WorkflowSnapshot


class FakeHandle:
    def __init__(self, *, mode: str = "ok") -> None:
        self.mode = mode
        self.queries: list[object] = []
        self.signals: list[tuple[object, object]] = []

    async def query(self, query_name: object):
        self.queries.append(query_name)
        if self.mode == "not-found":
            raise RPCError("missing workflow", RPCStatusCode.NOT_FOUND, b"")
        if self.mode == "unavailable":
            raise RPCError("temporal unavailable", RPCStatusCode.UNAVAILABLE, b"")
        if getattr(query_name, "__name__", "") == "current_status":
            return "waiting_for_ir_review"
        return WorkflowSnapshot(
            document_id="doc-123",
            status="waiting_for_ir_review",
            next_actions=[],
            artifact_versions={"semantic_chunks": 1},
        )

    async def signal(self, signal_name: object, payload: object) -> None:
        if self.mode == "not-found":
            raise RPCError("missing workflow", RPCStatusCode.NOT_FOUND, b"")
        if self.mode == "unavailable":
            raise RPCError("temporal unavailable", RPCStatusCode.UNAVAILABLE, b"")
        self.signals.append((signal_name, payload))


class FakeClient:
    def __init__(self, *, mode: str = "ok") -> None:
        self.handle = FakeHandle(mode=mode)
        self.started: dict[str, object] | None = None
        self.workflow_id: str | None = None

    async def start_workflow(self, workflow_run, payload, *, id: str, task_queue: str):
        self.started = {
            "workflow_run": workflow_run,
            "payload": payload,
            "id": id,
            "task_queue": task_queue,
        }
        return self.handle

    def get_workflow_handle(self, workflow_id: str) -> FakeHandle:
        self.workflow_id = workflow_id
        return self.handle


class ConflictClient(FakeClient):
    async def start_workflow(self, workflow_run, payload, *, id: str, task_queue: str):
        raise WorkflowAlreadyStartedError(id, "TemporalDocumentWorkflow")


class UnavailableStartClient(FakeClient):
    async def start_workflow(self, workflow_run, payload, *, id: str, task_queue: str):
        raise RPCError("temporal unavailable", RPCStatusCode.UNAVAILABLE, b"")


class WorkflowApiServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_start_workflow_uses_document_id_to_build_temporal_workflow_id(self) -> None:
        client = FakeClient()
        service = WorkflowApiService(client_factory=lambda: client, settings=ApiSettings())

        response = await service.start_workflow(
            StartWorkflowRequest(
                document_id="doc-123",
                source_uri="file:///tmp/source.docx",
            )
        )

        self.assertEqual(response.workflow_id, "document-workflow-doc-123")
        self.assertEqual(client.started["task_queue"], "doc-agents")

    async def test_get_snapshot_queries_temporal_snapshot(self) -> None:
        client = FakeClient()
        service = WorkflowApiService(client_factory=lambda: client, settings=ApiSettings())

        response = await service.get_snapshot("doc-123")

        self.assertEqual(response.workflow_id, "document-workflow-doc-123")
        self.assertEqual(response.artifact_versions, {"semantic_chunks": 1})

    async def test_submit_ir_artifact_update_signals_workflow(self) -> None:
        client = FakeClient()
        service = WorkflowApiService(client_factory=lambda: client, settings=ApiSettings())

        response = await service.submit_ir_artifact_update(
            "doc-123",
            ArtifactUpdateRequest(
                target="data_schema",
                artifact_id="doc-123-data_schema_json-v2",
                artifact_type="data_schema_json",
                version=2,
                uri="s3://doc-artifacts/doc-123/data_schema_json/v2/doc-123-data_schema_json-v2.bin",
            ),
        )

        self.assertEqual(response.signal, "ir_artifact_updated")
        self.assertEqual(len(client.handle.signals), 1)

    async def test_start_workflow_maps_temporal_conflict_to_service_conflict(self) -> None:
        service = WorkflowApiService(client_factory=lambda: ConflictClient(), settings=ApiSettings())

        with self.assertRaises(WorkflowConflictError):
            await service.start_workflow(
                StartWorkflowRequest(
                    document_id="doc-123",
                    source_uri="file:///tmp/source.docx",
                )
            )

    async def test_get_status_maps_not_found_rpc_error(self) -> None:
        client = FakeClient(mode="not-found")
        service = WorkflowApiService(client_factory=lambda: client, settings=ApiSettings())

        with self.assertRaises(WorkflowNotFoundError):
            await service.get_status("doc-123")

    async def test_start_workflow_maps_unavailable_rpc_error(self) -> None:
        service = WorkflowApiService(
            client_factory=lambda: UnavailableStartClient(),
            settings=ApiSettings(),
        )

        with self.assertRaises(TemporalUnavailableError):
            await service.start_workflow(
                StartWorkflowRequest(
                    document_id="doc-123",
                    source_uri="file:///tmp/source.docx",
                )
            )


if __name__ == "__main__":
    unittest.main()
