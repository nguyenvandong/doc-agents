from __future__ import annotations

from dataclasses import dataclass, field

from .models import ArtifactRef, ArtifactReviewUpdate, ReviewDecision, ReviewTarget


@dataclass(frozen=True)
class WorkflowStartInput:
    document_id: str
    source_uri: str
    enable_vision: bool = False

    @property
    def workflow_id(self) -> str:
        return f"document-workflow-{self.document_id}"


@dataclass(frozen=True)
class ReviewSubmission:
    action: str
    comment: str = ""
    targets: list[str] = field(default_factory=list)

    def to_core_decision(self) -> ReviewDecision:
        mapped_targets = [ReviewTarget(target) for target in self.targets]
        if self.action == "approve":
            return ReviewDecision.approve(
                comment=self.comment,
                targets=mapped_targets or [ReviewTarget.IR],
            )
        if self.action == "comment":
            if not mapped_targets:
                return ReviewDecision.comment(comment=self.comment)
            return ReviewDecision(action="comment", comment=self.comment, targets=mapped_targets)
        return ReviewDecision.reject(comment=self.comment, targets=mapped_targets)


@dataclass(frozen=True)
class ArtifactReviewUpdatePayload:
    target: str
    artifact_id: str
    artifact_type: str
    version: int
    uri: str

    def target_enum(self) -> ReviewTarget:
        return ReviewTarget(self.target)

    def to_artifact_ref(self) -> ArtifactRef:
        return ArtifactRef(
            artifact_id=self.artifact_id,
            artifact_type=self.artifact_type,
            version=self.version,
            uri=self.uri,
        )

    def to_core_update(self) -> ArtifactReviewUpdate:
        return ArtifactReviewUpdate(
            target=self.target_enum(),
            artifact=self.to_artifact_ref(),
        )


@dataclass(frozen=True)
class WorkflowSnapshot:
    document_id: str
    status: str
    next_actions: list[str]
    artifact_versions: dict[str, int]
