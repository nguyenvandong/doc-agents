# Copilot Instructions

## Commands

Install dependencies:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Run the full test suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Run one test module:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_workflow -v
```

Run one test method:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_workflow.DocumentWorkflowStateTest.test_markdown_comment_routes_only_synthesis -v
```

## Architecture

The repository implements a document-processing pipeline that turns a DOCX source into versioned intermediate artifacts and a synthesized Markdown specification.

- `doc_agents/parser.py` parses DOCX bytes into ordered blocks plus `semantic_html`.
- `doc_agents/activities.py` is the core pipeline implementation: parse -> chunk -> extract three IR artifacts (`data_schema_json`, `business_rules_json`, `workflows_json`) -> render side artifacts -> synthesize Markdown -> validate Markdown against chunk evidence.
- `doc_agents/workflow.py` is the pure state machine. It owns workflow status, artifact refs, review history, and rerun routing.
- `doc_agents/temporal_workflow.py` wraps that state machine in Temporal orchestration. It pauses at two review gates (`WAITING_FOR_IR_REVIEW` and `WAITING_FOR_FINAL_REVIEW`) and resumes based on review signals.
- `doc_agents/temporal_payloads.py`, `doc_agents/temporal_contract.py`, and `doc_agents/temporal_runtime.py` form the Temporal boundary: small payload models, stable workflow/activity/signal names, and worker registration.
- `doc_agents/repository.py`, `doc_agents/storage.py`, and `doc_agents/settings.py` are the persistence boundary for MinIO + Postgres-backed artifact storage.

## Conventions

- Keep large content out of workflow state and Temporal payloads. The system passes `ArtifactRef` metadata between phases and stores the real payload in artifact storage.
- Preserve the split between pure domain logic and Temporal wrappers: workflow transitions and rerun decisions belong in `workflow.py`; Temporal modules should translate signals, queries, and activity calls without reimplementing that logic.
- Review feedback drives selective reruns. `ReviewTarget.DATA_SCHEMA`, `BUSINESS_RULES`, and `WORKFLOWS` rerun the matching extraction and then synthesis; `MARKDOWN_DRAFT` reruns synthesis only.
- IR artifact replacement is first-class. The `ir_artifact_updated` signal can swap in a newer IR artifact version without rerunning extraction, and downstream synthesis should use that replacement ref.
- In `activities.py`, behavior changes depending on whether an artifact repository is configured. Without storage settings or injected test doubles, activities return `memory://` placeholder refs; with a repository, they persist bytes and auto-increment versions where `version=None`.
- `document_id` is reused in two different identities: storage writes use it as the repository `workflow_id`, while Temporal execution ids are `document-workflow-{document_id}` via `WorkflowStartInput.workflow_id`.
- The current extraction and validation logic is evidence-driven from chunk text prefixes (`Field:`, `Rule:`, `Workflow:`). If you change extraction behavior, update both synthesis and validation expectations together.
- Tests commonly inject dependencies through `configure_activity_dependencies(...)` and reuse fake repositories from `tests.test_activity_parser_integration`; follow that pattern instead of adding heavyweight integration setup for unit-level changes.
