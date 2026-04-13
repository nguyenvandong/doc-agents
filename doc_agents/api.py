from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

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

_BUSINESS_VALIDATION_TYPES = {
    "artifact_update_target_invalid",
    "artifact_update_type_mismatch",
}


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    if any(error["type"] in _BUSINESS_VALIDATION_TYPES for error in exc.errors()):
        status_code = status.HTTP_400_BAD_REQUEST
    return JSONResponse(status_code=status_code, content={"detail": exc.errors()})


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


@app.post(
    "/workflows/start",
    response_model=StartWorkflowResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_workflow(
    request: StartWorkflowRequest,
    service: WorkflowApiService = Depends(get_workflow_api_service),
) -> StartWorkflowResponse:
    try:
        return await service.start_workflow(request)
    except WorkflowConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except TemporalUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


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


@app.post(
    "/workflows/{document_id}/reviews/ir",
    response_model=ReviewResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
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


@app.post(
    "/workflows/{document_id}/reviews/final",
    response_model=ReviewResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
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
