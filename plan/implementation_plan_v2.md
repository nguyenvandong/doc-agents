# Document Workflow Remaining Work Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the remaining production-facing parts of the Temporal-native document workflow: real extraction over semantic chunks, persisted artifact versioning, review-driven reruns, richer synthesis artifacts, stronger validation, and storage-backed integration coverage.

**Architecture:** Keep workflow state small and durable by passing only `ArtifactRef` values through Temporal workflow state and activity inputs. All heavy payloads stay in persisted artifacts managed by repository/storage adapters, and every rerun that changes content must create a new artifact version instead of overwriting `v1`.

**Tech Stack:** Python 3.12, `unittest`, Temporal Python SDK, `python-docx`, `mammoth`, Postgres adapter, MinIO adapter

## Starting Point

- [x] `doc_agents/models.py`, `doc_agents/workflow.py`, `doc_agents/temporal_contract.py`, `doc_agents/temporal_runtime.py`, and `doc_agents/temporal_workflow.py` exist and are covered by tests
- [x] `parse_docx_activity` persists `parsed_document`
- [x] `semantic_chunk_activity`, `extract_*`, `synthesize_markdown_activity`, and `validate_markdown_against_chunks_activity` read persisted artifacts instead of carrying large payloads in workflow state
- [x] `tests/test_temporal_integration.py` passes
- [x] `python -m unittest discover -s tests -v` currently passes

## Definition Of Done For This Plan

- [x] `extract_data_schema_activity`, `extract_business_rules_activity`, and `extract_workflows_activity` emit structured JSON derived from semantic chunks rather than the current evidence scaffold
- [x] Artifact-producing activities create monotonic versions for reruns instead of always writing version `1`
- [x] Review loop can point reruns at the latest approved or edited artifact version
- [x] `render_mermaid_activity` and `generate_frontmatter_activity` read persisted artifacts and persist their own outputs
- [x] Validation checks the synthesized markdown against IR and chunks with explicit issue objects or stable issue strings
- [x] Storage-backed tests cover versioned reruns and persisted reads/writes across the pipeline

---

### Task 1: Add artifact version resolution and next-version writes

**Files:**
- Modify: `E:/workspace/doc-agents/doc_agents/repository.py`
- Modify: `E:/workspace/doc-agents/doc_agents/storage.py`
- Modify: `E:/workspace/doc-agents/doc_agents/activities.py`
- Modify: `E:/workspace/doc-agents/tests/test_repository.py`
- Modify: `E:/workspace/doc-agents/tests/test_activity_parser_integration.py`

- [x] **Step 1: Write the failing repository tests for latest-version lookup and next-version writes**

```python
def test_store_bytes_auto_increments_version_when_same_artifact_type_exists(self) -> None:
    blob_store = MinioArtifactBlobStore(client=FakeMinioClient(), bucket_name="doc-artifacts")
    connection = FakeConnection()
    connection.fetchone_result = (1,)
    catalog = PostgresArtifactCatalog(connection_factory=lambda: connection)
    repository = ArtifactRepository(blob_store=blob_store, catalog=catalog)

    artifact = repository.store_bytes(
        workflow_id="wf-9",
        document_id="doc-9",
        artifact_type="data_schema_json",
        payload=b'{"fields": []}',
        content_type="application/json",
        version=None,
    )

    self.assertEqual(artifact.version, 2)
    self.assertTrue(artifact.uri.endswith("/v2/doc-9-data_schema_json-v2.bin"))


def test_load_latest_returns_highest_version_for_artifact_type(self) -> None:
    blob_store = MinioArtifactBlobStore(client=FakeMinioClient(), bucket_name="doc-artifacts")
    connection = FakeConnection()
    connection.fetchone_result = (
        "doc-9-data_schema_json-v3",
        "data_schema_json",
        3,
        "s3://doc-artifacts/wf-9/data_schema_json/v3/doc-9-data_schema_json-v3.bin",
    )
    catalog = PostgresArtifactCatalog(connection_factory=lambda: connection)
    repository = ArtifactRepository(blob_store=blob_store, catalog=catalog)

    artifact = repository.load_latest(workflow_id="wf-9", artifact_type="data_schema_json")

    self.assertEqual(artifact.version, 3)
    self.assertEqual(artifact.artifact_id, "doc-9-data_schema_json-v3")
```

- [x] **Step 2: Run the targeted repository test to verify it fails**

Run: `E:\workspace\doc-agents\.venv\Scripts\python.exe -m unittest tests.test_repository -v`
Expected: FAIL because `version=None`, `load_latest`, or catalog query helpers are not implemented yet

- [x] **Step 3: Implement minimal repository and catalog support for version lookup**

```python
class PostgresArtifactCatalog:
    def next_version(self, workflow_id: str, artifact_type: str) -> int:
        with self.connection_factory() as connection:
            cursor = connection.execute(
                """
                select coalesce(max(version), 0)
                from artifact_records
                where workflow_id = %s and artifact_type = %s
                """,
                (workflow_id, artifact_type),
            )
            row = cursor.fetchone()
        return int(row[0]) + 1

    def latest_artifact(self, workflow_id: str, artifact_type: str) -> ArtifactRef | None:
        with self.connection_factory() as connection:
            cursor = connection.execute(
                """
                select artifact_id, artifact_type, version, uri
                from artifact_records
                where workflow_id = %s and artifact_type = %s
                order by version desc
                limit 1
                """,
                (workflow_id, artifact_type),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return ArtifactRef(
            artifact_id=row[0],
            artifact_type=row[1],
            version=int(row[2]),
            uri=row[3],
        )
```

```python
class ArtifactRepository:
    def store_bytes(
        self,
        *,
        workflow_id: str,
        document_id: str,
        artifact_type: str,
        payload: bytes,
        content_type: str,
        version: int | None = None,
    ) -> ArtifactRef:
        resolved_version = version if version is not None else self.catalog.next_version(workflow_id, artifact_type)
        artifact = ArtifactRef(
            artifact_id=f"{document_id}-{artifact_type}-v{resolved_version}",
            artifact_type=artifact_type,
            version=resolved_version,
            uri="",
        )
        object_key = self.blob_store.put_bytes(
            workflow_id=workflow_id,
            artifact=artifact,
            payload=payload,
            content_type=content_type,
        )
        persisted_artifact = ArtifactRef(
            artifact_id=artifact.artifact_id,
            artifact_type=artifact.artifact_type,
            version=artifact.version,
            uri=f"s3://{self.blob_store.bucket_name}/{object_key}",
        )
        self.catalog.upsert_artifact(
            ArtifactMetadataRecord(
                workflow_id=workflow_id,
                document_id=document_id,
                artifact=persisted_artifact,
                content_type=content_type,
                size_bytes=len(payload),
            )
        )
        return persisted_artifact

    def load_latest(self, workflow_id: str, artifact_type: str) -> ArtifactRef | None:
        return self.catalog.latest_artifact(workflow_id, artifact_type)
```

- [x] **Step 4: Update activity tests so rerunable JSON/text artifacts write `v2`, `v3`, and `v4` when version is omitted**

```python
def test_synthesize_markdown_activity_creates_new_version_on_second_run(self) -> None:
    repository = FakeArtifactRepository()
    configure_activity_dependencies(docx_parser=DocxParser(), artifact_repository=repository)
    data_schema = persisted_artifact(
        repository,
        document_id="doc-synthesis",
        artifact_type="data_schema_json",
        payload=build_extraction_payload(
            extraction_kind="data_schema",
            source_chunk_artifact_id="doc-synthesis-semantic_chunks-v1",
            evidence=["Customer ID"],
        ),
    )
    business_rules = persisted_artifact(
        repository,
        document_id="doc-synthesis",
        artifact_type="business_rules_json",
        payload=build_extraction_payload(
            extraction_kind="business_rules",
            source_chunk_artifact_id="doc-synthesis-semantic_chunks-v1",
            evidence=["Applicant must be 18 years old."],
        ),
    )
    workflows_json = persisted_artifact(
        repository,
        document_id="doc-synthesis",
        artifact_type="workflows_json",
        payload=build_extraction_payload(
            extraction_kind="workflows",
            source_chunk_artifact_id="doc-synthesis-semantic_chunks-v1",
            evidence=["System validates application before approval."],
        ),
    )
    synthesis_input = SynthesisInput(
        document_id="doc-synthesis",
        data_schema=data_schema,
        business_rules=business_rules,
        workflows=workflows_json,
    )
    first = synthesize_markdown_activity(synthesis_input)
    second = synthesize_markdown_activity(synthesis_input)
    self.assertEqual(first.version, 1)
    self.assertEqual(second.version, 2)
    self.assertNotEqual(first.uri, second.uri)
```

- [x] **Step 5: Run the focused tests to verify they pass**

Run: `E:\workspace\doc-agents\.venv\Scripts\python.exe -m unittest tests.test_repository tests.test_activity_parser_integration -v`
Expected: PASS

---

### Task 2: Replace extraction scaffolds with real structured outputs from semantic chunks

**Files:**
- Modify: `E:/workspace/doc-agents/doc_agents/activities.py`
- Create: `E:/workspace/doc-agents/tests/test_extraction_activities.py`
- Modify: `E:/workspace/doc-agents/tests/test_activity_parser_integration.py`

- [x] **Step 1: Write failing tests that expect structured extraction JSON instead of plain evidence lists**

```python
import json
import unittest

from doc_agents.activities import ExtractInput, configure_activity_dependencies, extract_business_rules_activity, extract_data_schema_activity, extract_workflows_activity
from doc_agents.models import ArtifactRef
from tests.test_activity_parser_integration import FakeArtifactRepository, build_chunk_set_payload, persisted_artifact


class ExtractionActivitiesTest(unittest.TestCase):
    def test_extract_data_schema_groups_field_like_chunks(self) -> None:
        repository = FakeArtifactRepository()
        configure_activity_dependencies(artifact_repository=repository)
        chunk_set = persisted_artifact(
            repository,
            document_id="doc-schema",
            artifact_type="semantic_chunks",
            payload=build_chunk_set_payload(
                "Field: Customer ID",
                "Field: Application Date",
                "Rule: Applicant must be 18 years old.",
            ),
        )

        result = extract_data_schema_activity(ExtractInput(document_id="doc-schema", chunk_set=chunk_set))

        payload = json.loads(repository.load_bytes(result).decode("utf-8"))
        self.assertEqual(
            payload["fields"],
            [
                {"name": "Customer ID", "source_chunk_id": "chunk-0"},
                {"name": "Application Date", "source_chunk_id": "chunk-1"},
            ],
        )

    def test_extract_business_rules_collects_rule_chunks(self) -> None:
        repository = FakeArtifactRepository()
        configure_activity_dependencies(artifact_repository=repository)
        chunk_set = persisted_artifact(
            repository,
            document_id="doc-rules",
            artifact_type="semantic_chunks",
            payload=build_chunk_set_payload(
                "Rule: Applicant must be 18 years old.",
                "Rule: Customer ID must be unique.",
                "Workflow: System validates application before approval.",
            ),
        )

        result = extract_business_rules_activity(ExtractInput(document_id="doc-rules", chunk_set=chunk_set))

        payload = json.loads(repository.load_bytes(result).decode("utf-8"))
        self.assertEqual(
            payload["rules"],
            [
                {"text": "Applicant must be 18 years old.", "source_chunk_id": "chunk-0"},
                {"text": "Customer ID must be unique.", "source_chunk_id": "chunk-1"},
            ],
        )

    def test_extract_workflows_collects_workflow_chunks(self) -> None:
        repository = FakeArtifactRepository()
        configure_activity_dependencies(artifact_repository=repository)
        chunk_set = persisted_artifact(
            repository,
            document_id="doc-workflows",
            artifact_type="semantic_chunks",
            payload=build_chunk_set_payload(
                "Workflow: System validates application before approval.",
                "Workflow: Manager approves eligible applications.",
                "Rule: Applicant must be 18 years old.",
            ),
        )

        result = extract_workflows_activity(ExtractInput(document_id="doc-workflows", chunk_set=chunk_set))

        payload = json.loads(repository.load_bytes(result).decode("utf-8"))
        self.assertEqual(
            payload["steps"],
            [
                {"text": "System validates application before approval.", "source_chunk_id": "chunk-0"},
                {"text": "Manager approves eligible applications.", "source_chunk_id": "chunk-1"},
            ],
        )
```

- [x] **Step 2: Run the new extraction test module to verify it fails**

Run: `E:\workspace\doc-agents\.venv\Scripts\python.exe -m unittest tests.test_extraction_activities -v`
Expected: FAIL because current extraction payloads only contain `extraction_kind`, `source_chunk_count`, and `evidence`

- [x] **Step 3: Implement the smallest real extraction heuristics over chunk text**

```python
def _extract_fields(chunk_payload: dict[str, Any]) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []
    for chunk in chunk_payload.get("chunks", []):
        text = str(chunk.get("text", "")).strip()
        if text.lower().startswith("field:"):
            fields.append(
                {
                    "name": text.split(":", maxsplit=1)[1].strip(),
                    "source_chunk_id": chunk["chunk_id"],
                }
            )
    return fields


def _extract_rules(chunk_payload: dict[str, Any]) -> list[dict[str, str]]:
    rules: list[dict[str, str]] = []
    for chunk in chunk_payload.get("chunks", []):
        text = str(chunk.get("text", "")).strip()
        if text.lower().startswith("rule:"):
            rules.append(
                {
                    "text": text.split(":", maxsplit=1)[1].strip(),
                    "source_chunk_id": chunk["chunk_id"],
                }
            )
    return rules


def _extract_workflow_steps(chunk_payload: dict[str, Any]) -> list[dict[str, str]]:
    steps: list[dict[str, str]] = []
    for chunk in chunk_payload.get("chunks", []):
        text = str(chunk.get("text", "")).strip()
        if text.lower().startswith("workflow:"):
            steps.append(
                {
                    "text": text.split(":", maxsplit=1)[1].strip(),
                    "source_chunk_id": chunk["chunk_id"],
                }
            )
    return steps
```

```python
@activity.defn(name="extract_data_schema_activity")
def extract_data_schema_activity(extract_input: ExtractInput) -> ArtifactRef:
    chunk_payload = _load_json_artifact(extract_input.chunk_set)
    if chunk_payload is None:
        return _artifact(extract_input.document_id, "data_schema_json")
    return _store_json_artifact(
        document_id=extract_input.document_id,
        artifact_type="data_schema_json",
        payload={
            "source_chunk_artifact_id": extract_input.chunk_set.artifact_id,
            "fields": _extract_fields(chunk_payload),
        },
    )
```

- [x] **Step 4: Update the integration test fixture payloads to include field/rule/workflow markers and assert the new JSON shape**

```python
self.assertEqual(payload["fields"][0]["name"], "Customer ID")
self.assertEqual(payload["rules"][0]["text"], "Applicant must be 18 years old.")
self.assertEqual(payload["steps"][0]["text"], "System validates application before approval.")
```

- [x] **Step 5: Run extraction tests and the parser/activity integration tests**

Run: `E:\workspace\doc-agents\.venv\Scripts\python.exe -m unittest tests.test_extraction_activities tests.test_activity_parser_integration -v`
Expected: PASS

---

### Task 3: Persist real frontmatter and Mermaid artifacts during synthesis

**Files:**
- Modify: `E:/workspace/doc-agents/doc_agents/activities.py`
- Create: `E:/workspace/doc-agents/tests/test_synthesis_artifacts.py`
- Modify: `E:/workspace/doc-agents/tests/test_activity_parser_integration.py`

- [x] **Step 1: Write failing tests for `render_mermaid_activity` and `generate_frontmatter_activity`**

```python
class SynthesisArtifactsTest(unittest.TestCase):
    def test_generate_frontmatter_persists_yaml_metadata(self) -> None:
        repository = FakeArtifactRepository()
        configure_activity_dependencies(artifact_repository=repository)
        synthesis_input = build_synthesis_input(repository, document_id="doc-frontmatter")

        result = generate_frontmatter_activity(synthesis_input)

        payload = repository.load_bytes(result).decode("utf-8")
        self.assertIn("document_id: doc-frontmatter", payload)
        self.assertIn("data_schema_version: 1", payload)

    def test_render_mermaid_persists_diagram_when_workflow_steps_exist(self) -> None:
        repository = FakeArtifactRepository()
        configure_activity_dependencies(artifact_repository=repository)
        synthesis_input = build_synthesis_input(repository, document_id="doc-mermaid")

        result = render_mermaid_activity(synthesis_input)

        payload = repository.load_bytes(result).decode("utf-8")
        self.assertIn("flowchart TD", payload)
        self.assertIn("System validates application before approval.", payload)
```

- [x] **Step 2: Run the synthesis-artifacts test module to verify it fails**

Run: `E:\workspace\doc-agents\.venv\Scripts\python.exe -m unittest tests.test_synthesis_artifacts -v`
Expected: FAIL because both activities still return placeholder `ArtifactRef` values only

- [x] **Step 3: Implement minimal persisted outputs for frontmatter and Mermaid**

```python
@activity.defn(name="generate_frontmatter_activity")
def generate_frontmatter_activity(synthesis_input: SynthesisInput) -> ArtifactRef:
    frontmatter = "\n".join(
        [
            "---",
            f"document_id: {synthesis_input.document_id}",
            f"data_schema_version: {synthesis_input.data_schema.version}",
            f"business_rules_version: {synthesis_input.business_rules.version}",
            f"workflows_version: {synthesis_input.workflows.version}",
            "---",
            "",
        ]
    )
    return _store_text_artifact(
        document_id=synthesis_input.document_id,
        artifact_type="frontmatter",
        payload=frontmatter,
        content_type="text/yaml; charset=utf-8",
    )
```

```python
@activity.defn(name="render_mermaid_activity")
def render_mermaid_activity(synthesis_input: SynthesisInput) -> ArtifactRef:
    workflows_payload = _load_json_artifact(synthesis_input.workflows)
    if workflows_payload is None:
        return _artifact(synthesis_input.document_id, "mermaid_render")
    steps = workflows_payload.get("steps", [])
    lines = ["flowchart TD"]
    for index, step in enumerate(steps):
        lines.append(f"    S{index}[\"{step['text']}\"]")
        if index > 0:
            lines.append(f"    S{index-1} --> S{index}")
    mermaid = "\n".join(lines) + "\n"
    return _store_text_artifact(
        document_id=synthesis_input.document_id,
        artifact_type="mermaid_render",
        payload=mermaid,
        content_type="text/plain; charset=utf-8",
    )
```

- [x] **Step 4: Extend synthesis integration assertions so markdown generation, frontmatter generation, and Mermaid rendering all read from the same persisted IR versions**

```python
self.assertEqual(frontmatter.version, 1)
self.assertEqual(mermaid.version, 1)
self.assertIn("flowchart TD", repository.load_bytes(mermaid).decode("utf-8"))
```

- [x] **Step 5: Run the synthesis-focused tests**

Run: `E:\workspace\doc-agents\.venv\Scripts\python.exe -m unittest tests.test_synthesis_artifacts tests.test_activity_parser_integration -v`
Expected: PASS

---

### Task 4: Track versioned artifacts through workflow state and reruns

**Files:**
- Modify: `E:/workspace/doc-agents/doc_agents/workflow.py`
- Modify: `E:/workspace/doc-agents/doc_agents/temporal_workflow.py`
- Modify: `E:/workspace/doc-agents/doc_agents/temporal_payloads.py`
- Modify: `E:/workspace/doc-agents/tests/test_workflow.py`
- Modify: `E:/workspace/doc-agents/tests/test_rerun_routing.py`
- Modify: `E:/workspace/doc-agents/tests/test_temporal_integration.py`

- [x] **Step 1: Write failing tests for reruns producing newer artifact refs in workflow state**

```python
def test_apply_final_review_keeps_latest_markdown_ref_after_synthesis_rerun(self) -> None:
    state = DocumentWorkflowState.ready_for_final_review(document_id="doc-1")
    state.artifacts["markdown_draft"] = ArtifactRef(
        artifact_id="doc-1-markdown_draft-v1",
        artifact_type="markdown_draft",
        version=1,
        uri="s3://doc-artifacts/doc-1/markdown_draft/v1/doc-1-markdown_draft-v1.bin",
    )
    state.apply_final_review(
        ReviewDecision.reject(comment="fix draft", targets=[ReviewTarget.MARKDOWN_DRAFT])
    )
    self.assertEqual(state.next_actions, ["rerun:synthesis"])
```

```python
async def test_workflow_rerun_updates_artifact_versions(self) -> None:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with create_worker(env.client, task_queue="doc-agents-test"):
            handle = await env.client.start_workflow(
                TemporalDocumentWorkflow.run,
                WorkflowStartInput(
                    document_id="doc-rerun",
                    source_uri="memory://source/doc-rerun",
                ),
                id="document-workflow-doc-rerun",
                task_queue="doc-agents-test",
            )
            for _ in range(10):
                if await handle.query(TemporalDocumentWorkflow.current_status) == WorkflowStatus.WAITING_FOR_IR_REVIEW.value:
                    break
                await env.sleep(1)
            await handle.signal(
                TemporalDocumentWorkflow.submit_ir_review,
                ReviewSubmission(action="approve", comment="ir ok", targets=[]),
            )
            await handle.signal(
                TemporalDocumentWorkflow.submit_final_review,
                ReviewSubmission(action="reject", comment="rerun markdown", targets=[ReviewTarget.MARKDOWN_DRAFT.value]),
            )
            await env.sleep(1)
    snapshot = await handle.query(TemporalDocumentWorkflow.snapshot)
    self.assertIn("markdown_draft", snapshot.artifact_versions)
    self.assertGreaterEqual(snapshot.artifact_versions["markdown_draft"], 2)
```

- [x] **Step 2: Run workflow and Temporal integration tests to verify they fail**

Run: `E:\workspace\doc-agents\.venv\Scripts\python.exe -m unittest tests.test_workflow tests.test_rerun_routing tests.test_temporal_integration -v`
Expected: FAIL because snapshots do not expose artifact versions and reruns are not asserted against version growth

- [x] **Step 3: Add artifact-version summaries to workflow state and Temporal snapshot payloads**

```python
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
```

```python
@dataclass(frozen=True)
class WorkflowSnapshot:
    document_id: str
    status: str
    next_actions: list[str]
    artifact_versions: dict[str, int]
```

- [x] **Step 4: Update workflow queries and rerun paths so tests assert the latest artifact version after reruns**

```python
return WorkflowSnapshot(
    document_id=self._state.document_id,
    status=self._state.status.value,
    next_actions=list(self._state.next_actions),
    artifact_versions=self._state.artifact_versions,
)
```

- [x] **Step 5: Run the workflow-focused tests**

Run: `E:\workspace\doc-agents\.venv\Scripts\python.exe -m unittest tests.test_workflow tests.test_rerun_routing tests.test_temporal_integration -v`
Expected: PASS

---

### Task 5: Support review-edited artifact refs and targeted reruns

**Files:**
- Modify: `E:/workspace/doc-agents/doc_agents/models.py`
- Modify: `E:/workspace/doc-agents/doc_agents/workflow.py`
- Modify: `E:/workspace/doc-agents/doc_agents/temporal_payloads.py`
- Modify: `E:/workspace/doc-agents/doc_agents/temporal_workflow.py`
- Create: `E:/workspace/doc-agents/tests/test_review_artifact_updates.py`

- [x] **Step 1: Write failing tests for review submissions that replace an artifact ref without rerunning every upstream step**

```python
class ReviewArtifactUpdatesTest(unittest.TestCase):
    def test_ir_review_can_replace_data_schema_artifact_ref(self) -> None:
        state = DocumentWorkflowState.ready_for_ir_review(document_id="doc-1")
        state.artifacts["data_schema_json"] = ArtifactRef(
            artifact_id="doc-1-data_schema_json-v1",
            artifact_type="data_schema_json",
            version=1,
            uri="s3://doc-artifacts/doc-1/data_schema_json/v1/doc-1-data_schema_json-v1.bin",
        )
        replacement = ArtifactRef(
            artifact_id="doc-1-data_schema_json-v2",
            artifact_type="data_schema_json",
            version=2,
            uri="s3://doc-artifacts/doc-1/data_schema_json/v2/doc-1-data_schema_json-v2.bin",
        )

        state.apply_ir_artifact_update(ReviewTarget.DATA_SCHEMA, replacement)

        self.assertEqual(state.artifacts["data_schema_json"].version, 2)
        self.assertEqual(state.next_actions, ["rerun:synthesis"])
```

- [x] **Step 2: Run the new review-artifact test module to verify it fails**

Run: `E:\workspace\doc-agents\.venv\Scripts\python.exe -m unittest tests.test_review_artifact_updates -v`
Expected: FAIL because there is no artifact-update path in workflow state or payloads yet

- [x] **Step 3: Add a review artifact update contract that carries a replacement `ArtifactRef`**

```python
@dataclass(frozen=True)
class ArtifactReviewUpdate:
    target: str
    artifact_id: str
    artifact_type: str
    version: int
    uri: str

    def to_artifact_ref(self) -> ArtifactRef:
        return ArtifactRef(
            artifact_id=self.artifact_id,
            artifact_type=self.artifact_type,
            version=self.version,
            uri=self.uri,
        )
```

```python
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
```

- [x] **Step 4: Wire a Temporal signal or update handler to accept artifact replacements and update state without rerunning extraction**

```python
@workflow.signal(name="ir_artifact_updated")
def submit_ir_artifact_update(self, update: ArtifactReviewUpdatePayload) -> None:
    assert self._state is not None
    self._state.apply_ir_artifact_update(update.target_enum(), update.to_artifact_ref())
```

- [x] **Step 5: Run the review-update and Temporal integration tests**

Run: `E:\workspace\doc-agents\.venv\Scripts\python.exe -m unittest tests.test_review_artifact_updates tests.test_temporal_integration -v`
Expected: PASS

---

### Task 6: Strengthen validation against markdown, IR, and chunks

**Files:**
- Modify: `E:/workspace/doc-agents/doc_agents/activities.py`
- Create: `E:/workspace/doc-agents/tests/test_validation_activity.py`
- Modify: `E:/workspace/doc-agents/tests/test_activity_parser_integration.py`

- [x] **Step 1: Write failing tests for validation issues covering missing fields, missing rules, and missing workflow steps**

```python
class ValidationActivityTest(unittest.TestCase):
    def test_validation_reports_missing_rule_and_field(self) -> None:
        repository = FakeArtifactRepository()
        configure_activity_dependencies(artifact_repository=repository)
        chunk_set = persisted_artifact(
            repository,
            document_id="doc-validate",
            artifact_type="semantic_chunks",
            payload=build_chunk_set_payload(
                "Field: Customer ID",
                "Rule: Applicant must be 18 years old.",
                "Workflow: System validates application before approval.",
            ),
        )
        markdown = persisted_artifact(
            repository,
            document_id="doc-validate",
            artifact_type="markdown_draft",
            payload=(
                "# Document Specification\n\n"
                "## Data Schema\n\n"
                "- Application Date\n\n"
                "## Business Rules\n\n"
                "- Customer ID must be unique.\n"
            ).encode("utf-8"),
        )
        report = validate_markdown_against_chunks_activity(
            ValidationInput(
                document_id="doc-validate",
                markdown_draft=markdown,
                chunk_set=chunk_set,
            )
        )
        self.assertFalse(report.passed)
        self.assertEqual(
            report.issues,
            [
                "Missing field coverage in markdown: Customer ID",
                "Missing rule coverage in markdown: Applicant must be 18 years old.",
            ],
        )
```

- [x] **Step 2: Run the validation test module to verify it fails**

Run: `E:\workspace\doc-agents\.venv\Scripts\python.exe -m unittest tests.test_validation_activity -v`
Expected: FAIL because current validation only checks raw chunk text containment

- [x] **Step 3: Implement minimal category-aware validation helpers**

```python
def _missing_items(markdown: str, items: list[str], prefix: str) -> list[str]:
    issues: list[str] = []
    for item in items:
        if item and item not in markdown:
            issues.append(f"{prefix}: {item}")
    return issues
```

```python
def validate_markdown_against_chunks_activity(validation_input: ValidationInput) -> ValidationReport:
    markdown_payload = _load_artifact_payload(validation_input.markdown_draft)
    chunk_payload = _load_json_artifact(validation_input.chunk_set)
    if markdown_payload is None or chunk_payload is None:
        return ValidationReport(passed=True, issues=[])
    markdown = markdown_payload.decode("utf-8")
    chunks = chunk_payload.get("chunks", [])
    field_names = [chunk["text"].split(":", maxsplit=1)[1].strip() for chunk in chunks if chunk["text"].lower().startswith("field:")]
    rules = [chunk["text"].split(":", maxsplit=1)[1].strip() for chunk in chunks if chunk["text"].lower().startswith("rule:")]
    steps = [chunk["text"].split(":", maxsplit=1)[1].strip() for chunk in chunks if chunk["text"].lower().startswith("workflow:")]
    issues = []
    issues.extend(_missing_items(markdown, field_names, "Missing field coverage in markdown"))
    issues.extend(_missing_items(markdown, rules, "Missing rule coverage in markdown"))
    issues.extend(_missing_items(markdown, steps, "Missing workflow coverage in markdown"))
    return ValidationReport(passed=not issues, issues=issues)
```

- [x] **Step 4: Update integration coverage so the failing markdown draft omits one field/rule/step on purpose**

```python
self.assertIn("Missing workflow coverage in markdown: System validates application before approval.", report.issues)
```

- [x] **Step 5: Run validation-focused tests**

Run: `E:\workspace\doc-agents\.venv\Scripts\python.exe -m unittest tests.test_validation_activity tests.test_activity_parser_integration -v`
Expected: PASS

---

### Task 7: Add storage-backed rerun integration coverage

**Files:**
- Modify: `E:/workspace/doc-agents/tests/test_temporal_integration.py`
- Create: `E:/workspace/doc-agents/tests/test_storage_backed_pipeline.py`
- Modify: `E:/workspace/doc-agents/tests/test_activity_parser_integration.py`

- [x] **Step 1: Write failing integration tests that exercise two synthesis runs and assert persisted version growth**

```python
class StorageBackedPipelineTest(unittest.TestCase):
    def test_storage_backed_pipeline_creates_new_markdown_version_after_rerun(self) -> None:
        repository = FakeArtifactRepository()
        configure_activity_dependencies(docx_parser=DocxParser(), artifact_repository=repository)
        data_schema = persisted_artifact(
            repository,
            document_id="doc-storage",
            artifact_type="data_schema_json",
            payload=build_extraction_payload(
                extraction_kind="data_schema",
                source_chunk_artifact_id="doc-storage-semantic_chunks-v1",
                evidence=["Customer ID"],
            ),
        )
        business_rules = persisted_artifact(
            repository,
            document_id="doc-storage",
            artifact_type="business_rules_json",
            payload=build_extraction_payload(
                extraction_kind="business_rules",
                source_chunk_artifact_id="doc-storage-semantic_chunks-v1",
                evidence=["Applicant must be 18 years old."],
            ),
        )
        workflows_json = persisted_artifact(
            repository,
            document_id="doc-storage",
            artifact_type="workflows_json",
            payload=build_extraction_payload(
                extraction_kind="workflows",
                source_chunk_artifact_id="doc-storage-semantic_chunks-v1",
                evidence=["System validates application before approval."],
            ),
        )
        synthesis_input = SynthesisInput(
            document_id="doc-storage",
            data_schema=data_schema,
            business_rules=business_rules,
            workflows=workflows_json,
        )
        first = synthesize_markdown_activity(synthesis_input)
        second = synthesize_markdown_activity(synthesis_input)
        self.assertEqual(first.version, 1)
        self.assertEqual(second.version, 2)
        self.assertNotEqual(first.uri, second.uri)
```

```python
async def test_temporal_workflow_snapshot_exposes_version_growth_after_rejection(self) -> None:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with create_worker(env.client, task_queue="doc-agents-test"):
            handle = await env.client.start_workflow(
                TemporalDocumentWorkflow.run,
                WorkflowStartInput(
                    document_id="doc-storage-rerun",
                    source_uri="memory://source/doc-storage-rerun",
                ),
                id="document-workflow-doc-storage-rerun",
                task_queue="doc-agents-test",
            )
            for _ in range(10):
                if await handle.query(TemporalDocumentWorkflow.current_status) == WorkflowStatus.WAITING_FOR_IR_REVIEW.value:
                    break
                await env.sleep(1)
            await handle.signal(
                TemporalDocumentWorkflow.submit_ir_review,
                ReviewSubmission(action="approve", comment="ir ok", targets=[]),
            )
    await handle.signal(TemporalDocumentWorkflow.submit_final_review, ReviewSubmission(action="reject", comment="fix format", targets=[ReviewTarget.MARKDOWN_DRAFT.value]))
    await env.sleep(1)
    snapshot = await handle.query(TemporalDocumentWorkflow.snapshot)
    self.assertGreaterEqual(snapshot.artifact_versions["markdown_draft"], 2)
```

- [x] **Step 2: Run the storage-backed test modules to verify they fail**

Run: `E:\workspace\doc-agents\.venv\Scripts\python.exe -m unittest tests.test_storage_backed_pipeline tests.test_temporal_integration -v`
Expected: FAIL until versioned reruns and snapshot reporting are complete

- [x] **Step 3: Implement only the missing glue identified by the failing tests**

```python
# Example expected outcome, not a new subsystem:
# - reuse FakeArtifactRepository with next-version behavior
# - make sure workflow rerun paths call activities that write version=None
# - preserve latest refs in workflow state after each rerun
```

- [x] **Step 4: Run the full suite**

Run: `E:\workspace\doc-agents\.venv\Scripts\python.exe -m unittest discover -s tests -v`
Expected: PASS

- [x] **Step 5: Update the original tracking file with actual completion status**

```markdown
- [x] implementation_plan_v2 Task 1 completed
- [x] implementation_plan_v2 Task 2 completed
- [x] implementation_plan_v2 Task 3 completed
- [x] implementation_plan_v2 Task 4 completed
- [x] implementation_plan_v2 Task 5 completed
- [x] implementation_plan_v2 Task 6 completed
- [x] implementation_plan_v2 Task 7 completed
```

---

## Self-Review Checklist

- [x] Every task keeps Temporal workflow state small by passing only `ArtifactRef`
- [x] Every rerunable artifact-producing activity is covered by at least one failing-then-passing test
- [x] Every new versioning behavior is asserted in tests, not just described
- [x] Review-driven artifact replacement path is covered separately from rerun path
- [x] The final verification command remains `E:\workspace\doc-agents\.venv\Scripts\python.exe -m unittest discover -s tests -v`
