from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .models import ArtifactRef, IssueCategory, ReviewDecision, ReviewTarget


class WorkflowStatus(str, Enum):
    CREATED = "created"
    WAITING_FOR_IR_REVIEW = "waiting_for_ir_review"
    SYNTHESIS_READY = "synthesis_ready"
    WAITING_FOR_FINAL_REVIEW = "waiting_for_final_review"
    COMPLETED = "completed"


@dataclass
class DocumentWorkflowState:
    document_id: str
    source_uri: str | None = None
    status: WorkflowStatus = WorkflowStatus.CREATED
    artifacts: dict[str, ArtifactRef] = field(default_factory=dict)
    next_actions: list[str] = field(default_factory=list)
    review_history: list[ReviewDecision] = field(default_factory=list)

    @property
    def artifact_versions(self) -> dict[str, int]:
        return {
            artifact_type: artifact.version
            for artifact_type, artifact in self.artifacts.items()
        }

    @classmethod
    def start(cls, document_id: str, source_uri: str) -> "DocumentWorkflowState":
        return cls(document_id=document_id, source_uri=source_uri)

    @classmethod
    def ready_for_ir_review(cls, document_id: str) -> "DocumentWorkflowState":
        return cls(document_id=document_id, status=WorkflowStatus.WAITING_FOR_IR_REVIEW)

    @classmethod
    def ready_for_final_review(cls, document_id: str) -> "DocumentWorkflowState":
        return cls(document_id=document_id, status=WorkflowStatus.WAITING_FOR_FINAL_REVIEW)

    def record_chunk_set(self, chunk_set: ArtifactRef) -> None:
        self.artifacts["semantic_chunks"] = chunk_set

    def record_extraction_outputs(
        self,
        *,
        data_schema: ArtifactRef,
        business_rules: ArtifactRef,
        workflows: ArtifactRef,
    ) -> None:
        self.artifacts["data_schema_json"] = data_schema
        self.artifacts["business_rules_json"] = business_rules
        self.artifacts["workflows_json"] = workflows
        self.status = WorkflowStatus.WAITING_FOR_IR_REVIEW

    def apply_ir_review(self, decision: ReviewDecision) -> None:
        self.review_history.append(decision)
        self.next_actions = self.actions_for_targets(decision.targets)
        if decision.action == "approve":
            self.status = WorkflowStatus.SYNTHESIS_READY

    def apply_final_review(self, decision: ReviewDecision) -> None:
        self.review_history.append(decision)
        self.next_actions = self.actions_for_targets(decision.targets)

    def apply_ir_artifact_update(self, target: ReviewTarget, artifact: ArtifactRef) -> None:
        target_to_key = {
            ReviewTarget.DATA_SCHEMA: "data_schema_json",
            ReviewTarget.BUSINESS_RULES: "business_rules_json",
            ReviewTarget.WORKFLOWS: "workflows_json",
        }
        artifact_key = target_to_key[target]
        self.artifacts[artifact_key] = artifact
        self.next_actions = ["rerun:synthesis"]
        self.status = WorkflowStatus.SYNTHESIS_READY

    @staticmethod
    def actions_for_targets(targets: list[ReviewTarget]) -> list[str]:
        actions: list[str] = []
        target_actions = {
            ReviewTarget.DATA_SCHEMA: ["rerun:extract_data_schema", "rerun:synthesis"],
            ReviewTarget.BUSINESS_RULES: ["rerun:extract_business_rules", "rerun:synthesis"],
            ReviewTarget.WORKFLOWS: ["rerun:extract_workflows", "rerun:synthesis"],
            ReviewTarget.MARKDOWN_DRAFT: ["rerun:synthesis"],
            ReviewTarget.IR: ["rerun:extract_data_schema", "rerun:extract_business_rules", "rerun:extract_workflows"],
        }
        for target in targets:
            for action in target_actions.get(target, []):
                if action not in actions:
                    actions.append(action)
        return actions

    @staticmethod
    def action_for_issue(issue: IssueCategory) -> str:
        issue_actions = {
            IssueCategory.EXTRACTION_DATA_SCHEMA: "rerun:extract_data_schema",
            IssueCategory.EXTRACTION_BUSINESS_RULES: "rerun:extract_business_rules",
            IssueCategory.EXTRACTION_WORKFLOWS: "rerun:extract_workflows",
            IssueCategory.SYNTHESIS_FORMATTING: "rerun:synthesis",
            IssueCategory.PARSE_SOURCE_LOSS: "rerun:parse",
        }
        return issue_actions[issue]
