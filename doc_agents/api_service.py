from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import inspect

from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from .api_models import (
    ArtifactUpdateRequest,
    ReviewRequest,
    ReviewResponse,
    StartWorkflowRequest,
    StartWorkflowResponse,
    WorkflowSnapshotResponse,
    WorkflowStatusResponse,
)
from .api_settings import ApiSettings
from .temporal_payloads import (
    ArtifactReviewUpdatePayload,
    ReviewSubmission,
    WorkflowStartInput,
)
from .temporal_workflow import TemporalDocumentWorkflow


class WorkflowConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkflowNotFoundError(RuntimeError):
    workflow_id: str

    def __str__(self) -> str:
        return f"Workflow {self.workflow_id} not found"


@dataclass(frozen=True)
class TemporalUnavailableError(RuntimeError):
    detail: str = "Temporal service unavailable"

    def __str__(self) -> str:
        return self.detail


class WorkflowApiService:
    def __init__(
        self,
        *,
        client_factory: Callable[[], Awaitable[Client] | Client],
        settings: ApiSettings,
    ) -> None:
        self._client_factory = client_factory
        self._settings = settings

    async def _client(self) -> Client:
        candidate = self._client_factory()
        if inspect.isawaitable(candidate):
            return await candidate
        return candidate

    @staticmethod
    def workflow_id_for(document_id: str) -> str:
        return f"document-workflow-{document_id}"

    @staticmethod
    def _raise_for_rpc_error(exc: RPCError, workflow_id: str) -> None:
        if exc.status == RPCStatusCode.NOT_FOUND:
            raise WorkflowNotFoundError(workflow_id) from exc
        if exc.status == RPCStatusCode.UNAVAILABLE:
            raise TemporalUnavailableError(str(exc)) from exc
        raise exc

    async def start_workflow(self, request: StartWorkflowRequest) -> StartWorkflowResponse:
        client = await self._client()
        workflow_id = self.workflow_id_for(request.document_id)
        task_queue = request.task_queue or self._settings.temporal_task_queue
        try:
            await client.start_workflow(
                TemporalDocumentWorkflow.run,
                WorkflowStartInput(
                    document_id=request.document_id,
                    source_uri=request.source_uri,
                    enable_vision=request.enable_vision,
                ),
                id=workflow_id,
                task_queue=task_queue,
            )
        except WorkflowAlreadyStartedError as exc:
            raise WorkflowConflictError(workflow_id) from exc
        except RPCError as exc:
            self._raise_for_rpc_error(exc, workflow_id)
        return StartWorkflowResponse(
            workflow_id=workflow_id,
            document_id=request.document_id,
            status="started",
        )

    async def _handle(self, document_id: str):
        client = await self._client()
        workflow_id = self.workflow_id_for(document_id)
        return workflow_id, client.get_workflow_handle(workflow_id)

    async def get_status(self, document_id: str) -> WorkflowStatusResponse:
        workflow_id, handle = await self._handle(document_id)
        try:
            status = await handle.query(TemporalDocumentWorkflow.current_status)
        except RPCError as exc:
            self._raise_for_rpc_error(exc, workflow_id)
        return WorkflowStatusResponse(
            document_id=document_id,
            workflow_id=workflow_id,
            status=status,
        )

    async def get_snapshot(self, document_id: str) -> WorkflowSnapshotResponse:
        workflow_id, handle = await self._handle(document_id)
        try:
            snapshot = await handle.query(TemporalDocumentWorkflow.snapshot)
        except RPCError as exc:
            self._raise_for_rpc_error(exc, workflow_id)
        return WorkflowSnapshotResponse(
            document_id=document_id,
            workflow_id=workflow_id,
            status=snapshot.status,
            next_actions=snapshot.next_actions,
            artifact_versions=snapshot.artifact_versions,
        )

    async def submit_ir_review(self, document_id: str, request: ReviewRequest) -> ReviewResponse:
        _, handle = await self._handle(document_id)
        try:
            await handle.signal(
                TemporalDocumentWorkflow.submit_ir_review,
                ReviewSubmission(
                    action=request.action,
                    comment=request.comment,
                    targets=request.targets,
                ),
            )
        except RPCError as exc:
            self._raise_for_rpc_error(exc, self.workflow_id_for(document_id))
        return ReviewResponse(
            document_id=document_id,
            accepted=True,
            signal="ir_review_submitted",
        )

    async def submit_final_review(self, document_id: str, request: ReviewRequest) -> ReviewResponse:
        _, handle = await self._handle(document_id)
        try:
            await handle.signal(
                TemporalDocumentWorkflow.submit_final_review,
                ReviewSubmission(
                    action=request.action,
                    comment=request.comment,
                    targets=request.targets,
                ),
            )
        except RPCError as exc:
            self._raise_for_rpc_error(exc, self.workflow_id_for(document_id))
        return ReviewResponse(
            document_id=document_id,
            accepted=True,
            signal="final_review_submitted",
        )

    async def submit_ir_artifact_update(
        self,
        document_id: str,
        request: ArtifactUpdateRequest,
    ) -> ReviewResponse:
        _, handle = await self._handle(document_id)
        try:
            await handle.signal(
                TemporalDocumentWorkflow.submit_ir_artifact_update,
                ArtifactReviewUpdatePayload(
                    target=request.target,
                    artifact_id=request.artifact_id,
                    artifact_type=request.artifact_type,
                    version=request.version,
                    uri=request.uri,
                ),
            )
        except RPCError as exc:
            self._raise_for_rpc_error(exc, self.workflow_id_for(document_id))
        return ReviewResponse(
            document_id=document_id,
            accepted=True,
            signal="ir_artifact_updated",
        )
