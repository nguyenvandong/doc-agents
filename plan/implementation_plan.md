# Document Workflow Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a testable Python core for the document workflow defined in `plan/adr_v2.md`, including workflow state, review gates, selective rerun routing, and a Temporal-oriented contract surface.

**Architecture:** Keep the orchestration core framework-agnostic so it can be tested without the Temporal SDK. Model workflow state and review actions as pure Python dataclasses plus a state machine class, then add a thin Temporal mapping module that names the workflow, activities, and review messages expected by a future SDK integration.

**Tech Stack:** Python 3.12, standard library `dataclasses`, `enum`, `unittest`

## Current Status

- [x] Plan Task 1 completed: domain model implemented and covered by `tests/test_models.py`
- [x] Plan Task 2 completed: workflow state machine and review gates implemented and covered by `tests/test_workflow.py`
- [x] Plan Task 3 completed: selective rerun mapping and review history implemented and covered by `tests/test_rerun_routing.py`
- [x] Plan Task 4 completed: Temporal-facing contract, `main.py` demo, runtime wiring, and related tests implemented
- [x] Additional work completed beyond this plan: Temporal Python SDK integration, parser thật với `python-docx` + `mammoth`, storage adapter với Postgres + MinIO, repository load/store artifact APIs, persisted-artifact chaining cho parse/chunk/extract/synthesis/validation activities, và workflow integration tests

## Remaining Work

- [ ] Thay scaffold hiện tại trong `extract_data_schema_activity`, `extract_business_rules_activity`, và `extract_workflows_activity` bằng extractor logic thật dựa trên `semantic_chunks`
- [ ] Hoàn thiện `render_mermaid_activity` và `generate_frontmatter_activity` để đọc/ghi persisted artifacts thay vì chỉ trả `ArtifactRef` giả
- [ ] Bổ sung versioning/rerun strategy cho artifacts để review loop không luôn ghi đè `v1`
- [ ] Nối review loop với persisted artifact versions và selective rerun theo artifact đã được reviewer sửa hoặc reject
- [ ] Nâng `validate_markdown_against_chunks_activity` từ string containment đơn giản lên validation thực sự dựa trên IR/chunk mapping
- [ ] Bổ sung integration tests cho storage-backed execution path với repository thật hoặc fake gần thực tế hơn

---

### Task 1: Create the domain model and failing tests

**Files:**
- Create: `E:/workspace/doc-agents/doc_agents/__init__.py`
- Create: `E:/workspace/doc-agents/doc_agents/models.py`
- Create: `E:/workspace/doc-agents/tests/test_models.py`

- [x] **Step 1: Write the failing tests**

```python
import unittest

from doc_agents.models import ArtifactRef, IssueCategory, ReviewDecision, ReviewTarget


class ArtifactRefTest(unittest.TestCase):
    def test_artifact_key_includes_type_and_version(self) -> None:
        artifact = ArtifactRef(
            artifact_id="a1",
            artifact_type="data_schema_json",
            version=3,
            uri="memory://artifacts/a1",
        )
        self.assertEqual(artifact.key, "data_schema_json:v3")


class ReviewDecisionTest(unittest.TestCase):
    def test_reject_requires_at_least_one_target(self) -> None:
        with self.assertRaises(ValueError):
            ReviewDecision.reject(comment="wrong", targets=[])

    def test_comment_defaults_to_markdown_target(self) -> None:
        decision = ReviewDecision.comment(comment="fix formatting")
        self.assertEqual(decision.targets, [ReviewTarget.MARKDOWN_DRAFT])


class IssueCategoryTest(unittest.TestCase):
    def test_issue_category_knows_its_phase(self) -> None:
        self.assertEqual(IssueCategory.EXTRACTION_BUSINESS_RULES.phase, "extraction")


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_models -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'doc_agents'`

- [x] **Step 3: Write minimal implementation**

```python
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
    EXTRACTION_BUSINESS_RULES = "extraction.business_rules"

    @property
    def phase(self) -> str:
        return self.value.split(".", maxsplit=1)[0]


@dataclass(frozen=True)
class ReviewDecision:
    action: str
    comment: str
    targets: list[ReviewTarget]

    @classmethod
    def reject(cls, comment: str, targets: list[ReviewTarget]) -> "ReviewDecision":
        if not targets:
            raise ValueError("reject requires at least one target")
        return cls(action="reject", comment=comment, targets=targets)

    @classmethod
    def comment(cls, comment: str) -> "ReviewDecision":
        return cls(action="comment", comment=comment, targets=[ReviewTarget.MARKDOWN_DRAFT])
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_models -v`
Expected: PASS

### Task 2: Implement workflow state machine with review gates

**Files:**
- Create: `E:/workspace/doc-agents/doc_agents/workflow.py`
- Create: `E:/workspace/doc-agents/tests/test_workflow.py`

- [x] **Step 1: Write the failing tests**

```python
import unittest

from doc_agents.models import ArtifactRef, ReviewDecision, ReviewTarget
from doc_agents.workflow import DocumentWorkflowState, WorkflowStatus


def artifact(name: str, version: int = 1) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=f"{name}-{version}",
        artifact_type=name,
        version=version,
        uri=f"memory://artifacts/{name}-{version}",
    )


class DocumentWorkflowStateTest(unittest.TestCase):
    def test_extraction_outputs_move_workflow_to_ir_review(self) -> None:
        state = DocumentWorkflowState.start(document_id="doc-1", source_uri="memory://source/doc-1")
        state.record_chunk_set(artifact("semantic_chunks"))
        state.record_extraction_outputs(
            data_schema=artifact("data_schema_json"),
            business_rules=artifact("business_rules_json"),
            workflows=artifact("workflows_json"),
        )
        self.assertEqual(state.status, WorkflowStatus.WAITING_FOR_IR_REVIEW)

    def test_approve_ir_moves_to_synthesis_ready(self) -> None:
        state = DocumentWorkflowState.ready_for_ir_review(document_id="doc-1")
        state.apply_ir_review(ReviewDecision.approve(comment="ok"))
        self.assertEqual(state.status, WorkflowStatus.SYNTHESIS_READY)

    def test_markdown_comment_routes_only_synthesis(self) -> None:
        state = DocumentWorkflowState.ready_for_final_review(document_id="doc-1")
        state.apply_final_review(
            ReviewDecision.reject(
                comment="fix formatting",
                targets=[ReviewTarget.MARKDOWN_DRAFT],
            )
        )
        self.assertEqual(state.next_actions, ["rerun:synthesis"])


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_workflow -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'doc_agents.workflow'`

- [x] **Step 3: Write minimal implementation**

```python
from dataclasses import dataclass, field
from enum import Enum

from .models import ArtifactRef, ReviewDecision, ReviewTarget


class WorkflowStatus(str, Enum):
    CREATED = "created"
    WAITING_FOR_IR_REVIEW = "waiting_for_ir_review"
    SYNTHESIS_READY = "synthesis_ready"
    WAITING_FOR_FINAL_REVIEW = "waiting_for_final_review"


@dataclass
class DocumentWorkflowState:
    document_id: str
    source_uri: str | None = None
    status: WorkflowStatus = WorkflowStatus.CREATED
    artifacts: dict[str, ArtifactRef] = field(default_factory=dict)
    next_actions: list[str] = field(default_factory=list)

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
        if decision.action == "approve":
            self.status = WorkflowStatus.SYNTHESIS_READY

    def apply_final_review(self, decision: ReviewDecision) -> None:
        self.next_actions.clear()
        if ReviewTarget.MARKDOWN_DRAFT in decision.targets:
            self.next_actions.append("rerun:synthesis")
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_workflow -v`
Expected: PASS

### Task 3: Add selective rerun mapping and review event log

**Files:**
- Modify: `E:/workspace/doc-agents/doc_agents/models.py`
- Modify: `E:/workspace/doc-agents/doc_agents/workflow.py`
- Create: `E:/workspace/doc-agents/tests/test_rerun_routing.py`

- [x] **Step 1: Write the failing tests**

```python
import unittest

from doc_agents.models import IssueCategory, ReviewDecision, ReviewTarget
from doc_agents.workflow import DocumentWorkflowState


class SelectiveRerunRoutingTest(unittest.TestCase):
    def test_business_rule_comment_reruns_extraction_and_synthesis(self) -> None:
        state = DocumentWorkflowState.ready_for_final_review(document_id="doc-1")
        state.apply_final_review(
            ReviewDecision.reject(
                comment="business rule is missing",
                targets=[ReviewTarget.BUSINESS_RULES],
            )
        )
        self.assertEqual(
            state.next_actions,
            ["rerun:extract_business_rules", "rerun:synthesis"],
        )

    def test_issue_category_maps_to_expected_rerun_action(self) -> None:
        self.assertEqual(
            DocumentWorkflowState.action_for_issue(IssueCategory.PARSE_SOURCE_LOSS),
            "rerun:parse",
        )

    def test_review_event_log_keeps_history(self) -> None:
        state = DocumentWorkflowState.ready_for_ir_review(document_id="doc-1")
        state.apply_ir_review(
            ReviewDecision.reject(
                comment="schema incomplete",
                targets=[ReviewTarget.DATA_SCHEMA],
            )
        )
        self.assertEqual(state.review_history[-1].comment, "schema incomplete")


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_rerun_routing -v`
Expected: FAIL because `PARSE_SOURCE_LOSS`, `review_history`, or routing logic is missing

- [x] **Step 3: Write minimal implementation**

```python
class IssueCategory(str, Enum):
    EXTRACTION_DATA_SCHEMA = "extraction.data_schema"
    EXTRACTION_BUSINESS_RULES = "extraction.business_rules"
    EXTRACTION_WORKFLOWS = "extraction.workflows"
    SYNTHESIS_FORMATTING = "synthesis.formatting"
    PARSE_SOURCE_LOSS = "parse.source_loss"
```

```python
REVIEW_TARGET_ACTIONS = {
    ReviewTarget.DATA_SCHEMA: ["rerun:extract_data_schema", "rerun:synthesis"],
    ReviewTarget.BUSINESS_RULES: ["rerun:extract_business_rules", "rerun:synthesis"],
    ReviewTarget.WORKFLOWS: ["rerun:extract_workflows", "rerun:synthesis"],
    ReviewTarget.MARKDOWN_DRAFT: ["rerun:synthesis"],
}
```

```python
review_history: list[ReviewDecision] = field(default_factory=list)

def apply_ir_review(self, decision: ReviewDecision) -> None:
    self.review_history.append(decision)
    if decision.action == "approve":
        self.status = WorkflowStatus.SYNTHESIS_READY
    else:
        self.next_actions = self.actions_for_targets(decision.targets)

def apply_final_review(self, decision: ReviewDecision) -> None:
    self.review_history.append(decision)
    self.next_actions = self.actions_for_targets(decision.targets)

@staticmethod
def actions_for_targets(targets: list[ReviewTarget]) -> list[str]:
    ...

@staticmethod
def action_for_issue(issue: IssueCategory) -> str:
    ...
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_rerun_routing -v`
Expected: PASS

### Task 4: Add Temporal-facing contract module and CLI demo

**Files:**
- Create: `E:/workspace/doc-agents/doc_agents/temporal_contract.py`
- Modify: `E:/workspace/doc-agents/main.py`
- Create: `E:/workspace/doc-agents/tests/test_temporal_contract.py`

- [x] **Step 1: Write the failing tests**

```python
import unittest

from doc_agents.temporal_contract import (
    ACTIVITY_NAMES,
    REVIEW_SIGNAL_NAMES,
    build_workflow_start_payload,
)


class TemporalContractTest(unittest.TestCase):
    def test_contract_exposes_expected_activity_names(self) -> None:
        self.assertIn("parse_docx_activity", ACTIVITY_NAMES)
        self.assertIn("validate_markdown_against_chunks_activity", ACTIVITY_NAMES)

    def test_review_signal_names_cover_both_review_gates(self) -> None:
        self.assertEqual(
            REVIEW_SIGNAL_NAMES,
            {
                "ir_review_submitted": "ir_review_submitted",
                "final_review_submitted": "final_review_submitted",
            },
        )

    def test_start_payload_keeps_document_identity_small(self) -> None:
        payload = build_workflow_start_payload(
            document_id="doc-1",
            source_uri="memory://source/doc-1",
        )
        self.assertEqual(payload["document_id"], "doc-1")
        self.assertNotIn("raw_document", payload)


if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_temporal_contract -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'doc_agents.temporal_contract'`

- [x] **Step 3: Write minimal implementation**

```python
ACTIVITY_NAMES = (
    "store_source_document",
    "parse_docx_activity",
    "extract_tables_activity",
    "semantic_chunk_activity",
    "vision_extract_activity",
    "extract_data_schema_activity",
    "extract_business_rules_activity",
    "extract_workflows_activity",
    "synthesize_markdown_activity",
    "render_mermaid_activity",
    "generate_frontmatter_activity",
    "persist_markdown_activity",
    "validate_markdown_against_chunks_activity",
)

REVIEW_SIGNAL_NAMES = {
    "ir_review_submitted": "ir_review_submitted",
    "final_review_submitted": "final_review_submitted",
}

def build_workflow_start_payload(document_id: str, source_uri: str) -> dict[str, str]:
    return {
        "document_id": document_id,
        "source_uri": source_uri,
    }
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_temporal_contract -v`
Expected: PASS

- [x] **Step 5: Run the full verification suite**

Run: `python -m unittest discover -s tests -v`
Expected: PASS with all tests green
