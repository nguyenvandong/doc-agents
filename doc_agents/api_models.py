from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError


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
    targets: list[str] = Field(default_factory=list)

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
            raise PydanticCustomError(
                "artifact_update_target_invalid",
                "target must be one of data_schema, business_rules, workflows",
            )
        if self.artifact_type != expected:
            raise PydanticCustomError(
                "artifact_update_type_mismatch",
                "artifact_type does not match target",
            )
        return self
