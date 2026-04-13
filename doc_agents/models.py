from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class ArtifactRef:
    artifact_id: str
    artifact_type: str
    version: int
    uri: str

    @property
    def key(self) -> str:
        return f"{self.artifact_type}:v{self.version}"


class ReviewTarget(str, Enum):
    IR = "ir"
    DATA_SCHEMA = "data_schema"
    BUSINESS_RULES = "business_rules"
    WORKFLOWS = "workflows"
    MARKDOWN_DRAFT = "markdown_draft"


class IssueCategory(str, Enum):
    EXTRACTION_DATA_SCHEMA = "extraction.data_schema"
    EXTRACTION_BUSINESS_RULES = "extraction.business_rules"
    EXTRACTION_WORKFLOWS = "extraction.workflows"
    SYNTHESIS_FORMATTING = "synthesis.formatting"
    PARSE_SOURCE_LOSS = "parse.source_loss"

    @property
    def phase(self) -> str:
        return self.value.split(".", maxsplit=1)[0]


class ReviewDecision:
    def __init__(self, action: str, comment: str, targets: list[ReviewTarget]) -> None:
        self.action = action
        self.comment = comment
        self.targets = list(targets)

    @classmethod
    def approve(
        cls,
        comment: str = "",
        targets: list[ReviewTarget] | None = None,
    ) -> "ReviewDecision":
        return cls(action="approve", comment=comment, targets=targets or [ReviewTarget.IR])

    @classmethod
    def reject(cls, comment: str, targets: list[ReviewTarget]) -> "ReviewDecision":
        if not targets:
            raise ValueError("reject requires at least one target")
        return cls(action="reject", comment=comment, targets=targets)

    @classmethod
    def comment(cls, comment: str) -> "ReviewDecision":
        return cls(
            action="comment",
            comment=comment,
            targets=[ReviewTarget.MARKDOWN_DRAFT],
        )


@dataclass(frozen=True)
class ArtifactReviewUpdate:
    target: ReviewTarget
    artifact: ArtifactRef
