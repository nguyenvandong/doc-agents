# Workflow API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a minimal FastAPI surface for starting, querying, and reviewing `DocumentWorkflow` executions over Temporal.

**Architecture:** Add a thin HTTP layer that delegates all Temporal interactions to a small service object. Keep workflow state and API responses metadata-only by reusing existing Temporal payload contracts and exposing only workflow id, status, next actions, and artifact version summaries.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, Uvicorn, Temporal Python SDK, `unittest`

---

## File Structure

**Create**

- `E:/workspace/doc-agents/doc_agents/api.py` — FastAPI app, dependency wiring, 6 route handlers, HTTP error mapping
- `E:/workspace/doc-agents/doc_agents/api_models.py` — Pydantic request/response models and payload validation helpers
- `E:/workspace/doc-agents/doc_agents/api_service.py` — `WorkflowApiService`, Temporal handle lookup, start/query/signal methods, service exceptions
- `E:/workspace/doc-agents/doc_agents/api_settings.py` — API/Temporal environment-backed settings
- `E:/workspace/doc-agents/tests/test_api_models.py` — schema and business-rule validation tests
- `E:/workspace/doc-agents/tests/test_api_service.py` — service behavior tests with fake Temporal client/handle
- `E:/workspace/doc-agents/tests/test_api_routes.py` — FastAPI route tests with dependency override

**Modify**

- `E:/workspace/doc-agents/requirements.txt` — add FastAPI/Uvicorn/Pydantic dependencies
- `E:/workspace/doc-agents/main.py` — replace demo print entrypoint with API app export

---

### Task 1: Add Dependencies, Settings, and API Models

**Files:**
- Modify: `E:/workspace/doc-agents/requirements.txt`
- Create: `E:/workspace/doc-agents/doc_agents/api_settings.py`
- Create: `E:/workspace/doc-agents/doc_agents/api_models.py`
- Create: `E:/workspace/doc-agents/tests/test_api_models.py`

- [ ] **Step 1: Write the failing model/settings tests**

```python
import unittest

from doc_agents.api_models import (
    ArtifactUpdateRequest,
    ReviewRequest,
    StartWorkflowRequest,
)
from doc_agents.api_settings import ApiSettings


class ApiModelsTest(unittest.TestCase):
    def test_start_workflow_request_allows_optional_task_queue(self) -> None:
        request = StartWorkflowRequest(
            document_id="doc-123",
            source_uri="file:///tmp/source.docx",
        )
        self.assertIsNone(request.task_queue)
        self.assertFalse(request.enable_vision)

    def test_artifact_update_request_rejects_mismatched_target_and_artifact_type(self) -> None:
        with self.assertRaises(ValueError):
            ArtifactUpdateRequest(
                target="data_schema",
                artifact_id="doc-123-business_rules_json-v2",
                artifact_type="business_rules_json",
                version=2,
                uri="s3://doc-artifacts/doc-123/business_rules_json/v2/doc-123-business_rules_json-v2.bin",
            )

    def test_review_request_accepts_known_actions(self) -> None:
        request = ReviewRequest(
            action="reject",
            comment="missing rules",
            targets=["business_rules"],
        )
        self.assertEqual(request.action, "reject")
        self.assertEqual(request.targets, ["business_rules"])


class ApiSettingsTest(unittest.TestCase):
    def test_from_env_uses_defaults_when_temporal_env_not_set(self) -> None:
        settings = ApiSettings.from_env({})
        self.assertEqual(settings.temporal_address, "localhost:7233")
        self.assertEqual(settings.temporal_namespace, "default")
        self.assertEqual(settings.temporal_task_queue, "doc-agents")
```

- [ ] **Step 2: Run the targeted model/settings tests to verify they fail**

Run: `E:\workspace\doc-agents\.venv\Scripts\python.exe -m unittest tests.test_api_models -v`

Expected: FAIL because `api_models.py` and `api_settings.py` do not exist yet

- [ ] **Step 3: Add FastAPI dependencies**

Update `E:/workspace/doc-agents/requirements.txt` to:

```text
temporalio==1.25.0
psycopg[binary]==3.3.3
minio==7.2.20
python-docx==1.2.0
mammoth==1.12.0
fastapi==0.115.0
uvicorn==0.30.6
pydantic==2.9.2
```

- [ ] **Step 4: Implement minimal API settings**

Create `E:/workspace/doc-agents/doc_agents/api_settings.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
import os


@dataclass(frozen=True)
class ApiSettings:
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "doc-agents"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "ApiSettings":
        env = environ if environ is not None else os.environ
        return cls(
            temporal_address=env.get("DOC_AGENTS_TEMPORAL_ADDRESS", "localhost:7233"),
            temporal_namespace=env.get("DOC_AGENTS_TEMPORAL_NAMESPACE", "default"),
            temporal_task_queue=env.get("DOC_AGENTS_TEMPORAL_TASK_QUEUE", "doc-agents"),
        )
```

- [ ] **Step 5: Implement request/response models with target validation**

Create `E:/workspace/doc-agents/doc_agents/api_models.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


_IR_TARGET_TO_ARTIFACT_TYPE = {
    "data_schema": "data_schema_json",
    "business_rules": "business_rules_json",
    "workflows": "workflows_json",
}


class StartWorkflowRequest(BaseModel):
    document_id: str
    source_uri: str
    enable_vision: bool = False
    task_queue: str | None = None


class StartWorkflowResponse(BaseModel):
    workflow_id: str
    document_id: str
    status: str


class WorkflowStatusResponse(BaseModel):
    document_id: str
    workflow_id: str
    status: str


class WorkflowSnapshotResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_id: str
    workflow_id: str
    status: str
    next_actions: list[str]
    artifact_versions: dict[str, int]


class ReviewRequest(BaseModel):
    action: str
    comment: str = ""
    targets: list[str] = []

    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str:
        allowed = {"approve", "reject", "comment"}
        if value not in allowed:
            raise ValueError(f"action must be one of {sorted(allowed)}")
        return value


class ReviewResponse(BaseModel):
    document_id: str
    accepted: bool
    signal: str


class ArtifactUpdateRequest(BaseModel):
    target: str
    artifact_id: str
    artifact_type: str
    version: int
    uri: str

    @model_validator(mode="after")
    def validate_target_and_type(self) -> "ArtifactUpdateRequest":
        expected = _IR_TARGET_TO_ARTIFACT_TYPE.get(self.target)
        if expected is None:
            raise ValueError("target must be one of data_schema, business_rules, workflows")
        if self.artifact_type != expected:
            raise ValueError("artifact_type does not match target")
        return self
```

- [ ] **Step 6: Run the targeted model/settings tests to verify they pass**

Run: `E:\workspace\doc-agents\.venv\Scripts\python.exe -m unittest tests.test_api_models -v`

Expected: PASS

---

### Task 2: Add the Temporal-Facing Service Layer

**Files:**
- Create: `E:/workspace/doc-agents/doc_agents/api_service.py`
- Create: `E:/workspace/doc-agents/tests/test_api_service.py`

- [ ] **Step 1: Write the failing service tests**

```python
import unittest

from doc_agents.api_models import ArtifactUpdateRequest, StartWorkflowRequest
from doc_agents.api_service import WorkflowApiService, WorkflowConflictError
from doc_agents.api_settings import ApiSettings
from doc_agents.temporal_payloads import WorkflowSnapshot


class FakeHandle:
    def __init__(self) -> None:
        self.queries: list[object] = []
        self.signals: list[tuple[object, object]] = []

    async def query(self, query_name: object):
        self.queries.append(query_name)
        if getattr(query_name, "__name__", "") == "current_status":
            return "waiting_for_ir_review"
        return WorkflowSnapshot(
            document_id="doc-123",
            status="waiting_for_ir_review",
            next_actions=[],
            artifact_versions={"semantic_chunks": 1},
        )

    async def signal(self, signal_name: object, payload: object) -> None:
        self.signals.append((signal_name, payload))


class FakeClient:
    def __init__(self) -> None:
        self.handle = FakeHandle()
        self.started: dict[str, object] | None = None

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
        from temporalio.client import WorkflowAlreadyStartedError

        raise WorkflowAlreadyStartedError("already-started")


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
```

- [ ] **Step 2: Run the targeted service tests to verify they fail**

Run: `E:\workspace\doc-agents\.venv\Scripts\python.exe -m unittest tests.test_api_service -v`

Expected: FAIL because `api_service.py` does not exist yet

- [ ] **Step 3: Implement the minimal Temporal service**

Create `E:/workspace/doc-agents/doc_agents/api_service.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from temporalio.client import Client, WorkflowAlreadyStartedError

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
from .temporal_payloads import ArtifactReviewUpdatePayload, ReviewSubmission, WorkflowStartInput
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
        client_factory: Callable[[], Awaitable[Client]] | Callable[[], Client],
        settings: ApiSettings,
    ) -> None:
        self._client_factory = client_factory
        self._settings = settings

    async def _client(self) -> Client:
        candidate = self._client_factory()
        if hasattr(candidate, "__await__"):
            return await candidate  # type: ignore[return-value]
        return candidate  # type: ignore[return-value]

    @staticmethod
    def workflow_id_for(document_id: str) -> str:
        return f"document-workflow-{document_id}"

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
        status = await handle.query(TemporalDocumentWorkflow.current_status)
        return WorkflowStatusResponse(
            document_id=document_id,
            workflow_id=workflow_id,
            status=status,
        )

    async def get_snapshot(self, document_id: str) -> WorkflowSnapshotResponse:
        workflow_id, handle = await self._handle(document_id)
        snapshot = await handle.query(TemporalDocumentWorkflow.snapshot)
        return WorkflowSnapshotResponse(
            document_id=snapshot.document_id,
            workflow_id=workflow_id,
            status=snapshot.status,
            next_actions=snapshot.next_actions,
            artifact_versions=snapshot.artifact_versions,
        )

    async def submit_ir_review(self, document_id: str, request: ReviewRequest) -> ReviewResponse:
        _, handle = await self._handle(document_id)
        await handle.signal(
            TemporalDocumentWorkflow.submit_ir_review,
            ReviewSubmission(action=request.action, comment=request.comment, targets=request.targets),
        )
        return ReviewResponse(document_id=document_id, accepted=True, signal="ir_review_submitted")

    async def submit_final_review(self, document_id: str, request: ReviewRequest) -> ReviewResponse:
        _, handle = await self._handle(document_id)
        await handle.signal(
            TemporalDocumentWorkflow.submit_final_review,
            ReviewSubmission(action=request.action, comment=request.comment, targets=request.targets),
        )
        return ReviewResponse(document_id=document_id, accepted=True, signal="final_review_submitted")

    async def submit_ir_artifact_update(
        self,
        document_id: str,
        request: ArtifactUpdateRequest,
    ) -> ReviewResponse:
        _, handle = await self._handle(document_id)
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
        return ReviewResponse(document_id=document_id, accepted=True, signal="ir_artifact_updated")
```

- [ ] **Step 4: Run the targeted service tests to verify they pass**

Run: `E:\workspace\doc-agents\.venv\Scripts\python.exe -m unittest tests.test_api_service -v`

Expected: PASS

---

### Task 3: Add the FastAPI App and Route Handlers

**Files:**
- Create: `E:/workspace/doc-agents/doc_agents/api.py`
- Create: `E:/workspace/doc-agents/tests/test_api_routes.py`

- [ ] **Step 1: Write the failing route tests**

```python
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
```

- [ ] **Step 2: Run the targeted route tests to verify they fail**

Run: `E:\workspace\doc-agents\.venv\Scripts\python.exe -m unittest tests.test_api_routes -v`

Expected: FAIL because `api.py` does not exist yet

- [ ] **Step 3: Implement the FastAPI app**

Create `E:/workspace/doc-agents/doc_agents/api.py`:

```python
from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException, status

from .api_models import (
    ArtifactUpdateRequest,
    ReviewRequest,
    ReviewResponse,
    StartWorkflowRequest,
    StartWorkflowResponse,
    WorkflowSnapshotResponse,
    WorkflowStatusResponse,
)
from .api_service import (
    TemporalUnavailableError,
    WorkflowApiService,
    WorkflowConflictError,
    WorkflowNotFoundError,
)
from .api_settings import ApiSettings
from .temporal_runtime import connect_client


app = FastAPI(title="Document Workflow API")


@lru_cache(maxsize=1)
def get_api_settings() -> ApiSettings:
    return ApiSettings.from_env()


def get_workflow_api_service() -> WorkflowApiService:
    settings = get_api_settings()
    return WorkflowApiService(
        client_factory=lambda: connect_client(
            address=settings.temporal_address,
            namespace=settings.temporal_namespace,
        ),
        settings=settings,
    )


@app.post("/workflows/start", response_model=StartWorkflowResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_workflow(
    request: StartWorkflowRequest,
    service: WorkflowApiService = Depends(get_workflow_api_service),
) -> StartWorkflowResponse:
    try:
        return await service.start_workflow(request)
    except WorkflowConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@app.get("/workflows/{document_id}/status", response_model=WorkflowStatusResponse)
async def get_status(
    document_id: str,
    service: WorkflowApiService = Depends(get_workflow_api_service),
) -> WorkflowStatusResponse:
    try:
        return await service.get_status(document_id)
    except WorkflowNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TemporalUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.get("/workflows/{document_id}/snapshot", response_model=WorkflowSnapshotResponse)
async def get_snapshot(
    document_id: str,
    service: WorkflowApiService = Depends(get_workflow_api_service),
) -> WorkflowSnapshotResponse:
    try:
        return await service.get_snapshot(document_id)
    except WorkflowNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TemporalUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.post("/workflows/{document_id}/reviews/ir", response_model=ReviewResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_ir_review(
    document_id: str,
    request: ReviewRequest,
    service: WorkflowApiService = Depends(get_workflow_api_service),
) -> ReviewResponse:
    try:
        return await service.submit_ir_review(document_id, request)
    except WorkflowNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TemporalUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.post("/workflows/{document_id}/reviews/final", response_model=ReviewResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_final_review(
    document_id: str,
    request: ReviewRequest,
    service: WorkflowApiService = Depends(get_workflow_api_service),
) -> ReviewResponse:
    try:
        return await service.submit_final_review(document_id, request)
    except WorkflowNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TemporalUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.post(
    "/workflows/{document_id}/artifacts/ir-update",
    response_model=ReviewResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_ir_artifact_update(
    document_id: str,
    request: ArtifactUpdateRequest,
    service: WorkflowApiService = Depends(get_workflow_api_service),
) -> ReviewResponse:
    try:
        return await service.submit_ir_artifact_update(document_id, request)
    except WorkflowNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TemporalUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
```

- [ ] **Step 4: Run the targeted route tests to verify they pass**

Run: `E:\workspace\doc-agents\.venv\Scripts\python.exe -m unittest tests.test_api_routes -v`

Expected: PASS

---

### Task 4: Replace the Demo Entrypoint and Run the Full Suite

**Files:**
- Modify: `E:/workspace/doc-agents/main.py`
- Modify: `E:/workspace/doc-agents/tests/test_api_routes.py`

- [ ] **Step 1: Add one failing route-level import/entrypoint test**

Append to `E:/workspace/doc-agents/tests/test_api_routes.py`:

```python
    def test_main_exports_fastapi_app(self) -> None:
        from main import app as main_app

        self.assertIs(main_app, app)
```

- [ ] **Step 2: Run the API-focused tests to verify the new assertion fails**

Run: `E:\workspace\doc-agents\.venv\Scripts\python.exe -m unittest tests.test_api_models tests.test_api_service tests.test_api_routes -v`

Expected: FAIL because `main.py` still prints demo payload instead of exporting the FastAPI app

- [ ] **Step 3: Replace the demo entrypoint with the FastAPI app export**

Update `E:/workspace/doc-agents/main.py` to:

```python
from __future__ import annotations

from doc_agents.api import app


__all__ = ["app"]
```

- [ ] **Step 4: Run the API-focused tests to verify they pass**

Run: `E:\workspace\doc-agents\.venv\Scripts\python.exe -m unittest tests.test_api_models tests.test_api_service tests.test_api_routes -v`

Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `E:\workspace\doc-agents\.venv\Scripts\python.exe -m unittest discover -s tests -v`

Expected: PASS

---

## Self-Review Checklist

- [ ] All 6 endpoints from the approved spec are covered by tests
- [ ] No API response returns large artifact payloads
- [ ] `WorkflowApiService` is the only layer that talks to the Temporal client directly
- [ ] `artifact_type` vs `target` consistency is validated before the signal is sent
- [ ] `404`, `409`, and `503` error mappings are asserted in route tests
- [ ] `main.py` stops being a demo script and becomes a valid API entrypoint
