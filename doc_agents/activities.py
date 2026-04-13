from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any

from temporalio import activity

from .models import ArtifactRef
from .parser import DocxParser
from .repository import build_repository_from_env


_docx_parser: DocxParser = DocxParser()
_artifact_repository: Any | None = None


@dataclass(frozen=True)
class ParseDocumentInput:
    document_id: str
    source_uri: str


@dataclass(frozen=True)
class ChunkInput:
    document_id: str
    parsed_document: ArtifactRef


@dataclass(frozen=True)
class ExtractInput:
    document_id: str
    chunk_set: ArtifactRef


@dataclass(frozen=True)
class SynthesisInput:
    document_id: str
    data_schema: ArtifactRef
    business_rules: ArtifactRef
    workflows: ArtifactRef


@dataclass(frozen=True)
class ValidationInput:
    document_id: str
    markdown_draft: ArtifactRef
    chunk_set: ArtifactRef


@dataclass(frozen=True)
class ValidationReport:
    passed: bool
    issues: list[str]


def _artifact(document_id: str, artifact_type: str, version: int = 1) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=f"{document_id}-{artifact_type}-v{version}",
        artifact_type=artifact_type,
        version=version,
        uri=f"memory://artifacts/{document_id}/{artifact_type}/v{version}",
    )


def configure_activity_dependencies(
    *,
    docx_parser: DocxParser | None = None,
    artifact_repository: Any | None = None,
) -> None:
    global _docx_parser, _artifact_repository
    if docx_parser is not None:
        _docx_parser = docx_parser
    _artifact_repository = artifact_repository


def _read_source_bytes(source_uri: str) -> bytes | None:
    if source_uri.startswith("file://"):
        return Path(source_uri.removeprefix("file://")).read_bytes()
    path = Path(source_uri)
    if path.exists():
        return path.read_bytes()
    return None


def _artifact_repository_or_none() -> Any | None:
    global _artifact_repository
    if _artifact_repository is not None:
        return _artifact_repository
    required = [
        "DOC_AGENTS_POSTGRES_DSN",
        "DOC_AGENTS_MINIO_ENDPOINT",
        "DOC_AGENTS_MINIO_ACCESS_KEY",
        "DOC_AGENTS_MINIO_SECRET_KEY",
        "DOC_AGENTS_MINIO_BUCKET",
    ]
    if all(os.environ.get(key) for key in required):
        _artifact_repository = build_repository_from_env()
    return _artifact_repository


def _load_artifact_payload(artifact: ArtifactRef) -> bytes | None:
    repository = _artifact_repository_or_none()
    if repository is None or not hasattr(repository, "load_bytes"):
        return None
    return repository.load_bytes(artifact)


def _store_json_artifact(
    *,
    document_id: str,
    artifact_type: str,
    payload: dict[str, Any],
) -> ArtifactRef:
    repository = _artifact_repository_or_none()
    if repository is None:
        return _artifact(document_id, artifact_type)
    return repository.store_bytes(
        workflow_id=document_id,
        document_id=document_id,
        artifact_type=artifact_type,
        payload=json.dumps(payload).encode("utf-8"),
        content_type="application/json",
        version=None,
    )


def _chunk_payload_from_parsed_document(parsed_document: dict[str, Any]) -> dict[str, Any]:
    chunks: list[dict[str, Any]] = []
    for index, block in enumerate(parsed_document.get("blocks", [])):
        text = str(block.get("text", "")).strip()
        if not text:
            continue
        chunks.append(
            {
                "chunk_id": f"chunk-{index}",
                "kind": block.get("kind", "paragraph"),
                "text": text,
                "source_block_indices": [index],
            }
        )
    return {"chunks": chunks}


def _load_json_artifact(artifact: ArtifactRef) -> dict[str, Any] | None:
    payload = _load_artifact_payload(artifact)
    if payload is None:
        return None
    return json.loads(payload.decode("utf-8"))


def _store_text_artifact(
    *,
    document_id: str,
    artifact_type: str,
    payload: str,
    content_type: str,
) -> ArtifactRef:
    repository = _artifact_repository_or_none()
    if repository is None:
        return _artifact(document_id, artifact_type)
    return repository.store_bytes(
        workflow_id=document_id,
        document_id=document_id,
        artifact_type=artifact_type,
        payload=payload.encode("utf-8"),
        content_type=content_type,
        version=None,
    )


def _extraction_payload_from_chunks(
    *,
    extraction_kind: str,
    chunk_set: ArtifactRef,
    chunk_payload: dict[str, Any],
) -> dict[str, Any]:
    chunks = chunk_payload.get("chunks", [])
    evidence = [
        str(chunk.get("text", "")).strip()
        for chunk in chunks
        if str(chunk.get("text", "")).strip()
    ]
    return {
        "extraction_kind": extraction_kind,
        "source_chunk_artifact_id": chunk_set.artifact_id,
        "source_chunk_count": len(chunks),
        "evidence": evidence,
    }


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


def _markdown_section(title: str, lines: list[str]) -> str:
    body_lines = lines or ["- None"]
    return "\n".join([f"## {title}", "", *body_lines])


def _synthesized_markdown(
    *,
    data_schema_payload: dict[str, Any],
    business_rules_payload: dict[str, Any],
    workflows_payload: dict[str, Any],
) -> str:
    sections = [
        "# Document Specification",
        "",
        _markdown_section(
            "Data Schema",
            [f"- {item}" for item in data_schema_payload.get("evidence", [])],
        ),
        "",
        _markdown_section(
            "Business Rules",
            [f"- {item}" for item in business_rules_payload.get("evidence", [])],
        ),
        "",
        _markdown_section(
            "Workflows",
            [f"- {item}" for item in workflows_payload.get("evidence", [])],
        ),
    ]
    return "\n".join(sections) + "\n"


def _frontmatter_text(synthesis_input: SynthesisInput) -> str:
    return "\n".join(
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


def _mermaid_text(workflows_payload: dict[str, Any]) -> str:
    steps = workflows_payload.get("steps", [])
    lines = ["flowchart TD"]
    for index, step in enumerate(steps):
        lines.append(f"    S{index}[\"{step['text']}\"]")
        if index > 0:
            lines.append(f"    S{index-1} --> S{index}")
    return "\n".join(lines) + "\n"


def _prefixed_chunk_items(chunk_payload: dict[str, Any], prefix: str) -> list[str]:
    items: list[str] = []
    normalized_prefix = prefix.lower()
    for chunk in chunk_payload.get("chunks", []):
        text = str(chunk.get("text", "")).strip()
        if text.lower().startswith(normalized_prefix):
            items.append(text.split(":", maxsplit=1)[1].strip())
    return items


def _missing_items(markdown: str, items: list[str], prefix: str) -> list[str]:
    issues: list[str] = []
    for item in items:
        if item and item not in markdown:
            issues.append(f"{prefix}: {item}")
    return issues


def _markdown_section_body(markdown: str, title: str) -> str:
    lines = markdown.splitlines()
    heading = f"## {title}".strip()
    section_lines: list[str] = []
    in_section = False
    for line in lines:
        if line.strip() == heading:
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if in_section:
            section_lines.append(line)
    return "\n".join(section_lines).strip()


@activity.defn(name="store_source_document")
def store_source_document(source: ParseDocumentInput) -> ArtifactRef:
    return _artifact(source.document_id, "source_document")


@activity.defn(name="parse_docx_activity")
def parse_docx_activity(source: ParseDocumentInput) -> ArtifactRef:
    payload = _read_source_bytes(source.source_uri)
    if payload is None:
        return _artifact(source.document_id, "parsed_document")

    parsed = _docx_parser.parse_bytes(payload)
    parsed_payload = json.dumps(
        {
            "blocks": [
                {
                    "kind": block.kind,
                    "text": block.text,
                    "markdown": block.markdown,
                    "style_name": block.style_name,
                }
                for block in parsed.blocks
            ],
            "semantic_html": parsed.semantic_html,
            "mammoth_messages": parsed.mammoth_messages,
        }
    ).encode("utf-8")
    repository = _artifact_repository_or_none()
    if repository is not None:
        return repository.store_bytes(
            workflow_id=source.document_id,
            document_id=source.document_id,
            artifact_type="parsed_document",
            payload=parsed_payload,
            content_type="application/json",
            version=1,
        )
    return _artifact(source.document_id, "parsed_document")


@activity.defn(name="extract_tables_activity")
def extract_tables_activity(parsed: ParseDocumentInput) -> ArtifactRef:
    return _artifact(parsed.document_id, "table_extract")


@activity.defn(name="semantic_chunk_activity")
def semantic_chunk_activity(chunk_input: ChunkInput) -> ArtifactRef:
    payload = _load_artifact_payload(chunk_input.parsed_document)
    if payload is None:
        return _artifact(chunk_input.document_id, "semantic_chunks")
    parsed_document = json.loads(payload.decode("utf-8"))
    return _store_json_artifact(
        document_id=chunk_input.document_id,
        artifact_type="semantic_chunks",
        payload=_chunk_payload_from_parsed_document(parsed_document),
    )


@activity.defn(name="vision_extract_activity")
def vision_extract_activity(source: ParseDocumentInput) -> ArtifactRef:
    return _artifact(source.document_id, "vision_extract")


@activity.defn(name="extract_data_schema_activity")
def extract_data_schema_activity(extract_input: ExtractInput) -> ArtifactRef:
    payload = _load_artifact_payload(extract_input.chunk_set)
    if payload is None:
        return _artifact(extract_input.document_id, "data_schema_json")
    chunk_payload = json.loads(payload.decode("utf-8"))
    extraction_payload = _extraction_payload_from_chunks(
        extraction_kind="data_schema",
        chunk_set=extract_input.chunk_set,
        chunk_payload=chunk_payload,
    )
    return _store_json_artifact(
        document_id=extract_input.document_id,
        artifact_type="data_schema_json",
        payload={
            **extraction_payload,
            "fields": _extract_fields(chunk_payload),
        },
    )


@activity.defn(name="extract_business_rules_activity")
def extract_business_rules_activity(extract_input: ExtractInput) -> ArtifactRef:
    payload = _load_artifact_payload(extract_input.chunk_set)
    if payload is None:
        return _artifact(extract_input.document_id, "business_rules_json")
    chunk_payload = json.loads(payload.decode("utf-8"))
    extraction_payload = _extraction_payload_from_chunks(
        extraction_kind="business_rules",
        chunk_set=extract_input.chunk_set,
        chunk_payload=chunk_payload,
    )
    return _store_json_artifact(
        document_id=extract_input.document_id,
        artifact_type="business_rules_json",
        payload={
            **extraction_payload,
            "rules": _extract_rules(chunk_payload),
        },
    )


@activity.defn(name="extract_workflows_activity")
def extract_workflows_activity(extract_input: ExtractInput) -> ArtifactRef:
    payload = _load_artifact_payload(extract_input.chunk_set)
    if payload is None:
        return _artifact(extract_input.document_id, "workflows_json")
    chunk_payload = json.loads(payload.decode("utf-8"))
    extraction_payload = _extraction_payload_from_chunks(
        extraction_kind="workflows",
        chunk_set=extract_input.chunk_set,
        chunk_payload=chunk_payload,
    )
    return _store_json_artifact(
        document_id=extract_input.document_id,
        artifact_type="workflows_json",
        payload={
            **extraction_payload,
            "steps": _extract_workflow_steps(chunk_payload),
        },
    )


@activity.defn(name="synthesize_markdown_activity")
def synthesize_markdown_activity(synthesis_input: SynthesisInput) -> ArtifactRef:
    data_schema_payload = _load_json_artifact(synthesis_input.data_schema)
    business_rules_payload = _load_json_artifact(synthesis_input.business_rules)
    workflows_payload = _load_json_artifact(synthesis_input.workflows)
    if (
        data_schema_payload is None
        or business_rules_payload is None
        or workflows_payload is None
    ):
        return _artifact(synthesis_input.document_id, "markdown_draft")
    markdown = _synthesized_markdown(
        data_schema_payload=data_schema_payload,
        business_rules_payload=business_rules_payload,
        workflows_payload=workflows_payload,
    )
    return _store_text_artifact(
        document_id=synthesis_input.document_id,
        artifact_type="markdown_draft",
        payload=markdown,
        content_type="text/markdown; charset=utf-8",
    )


@activity.defn(name="render_mermaid_activity")
def render_mermaid_activity(synthesis_input: SynthesisInput) -> ArtifactRef:
    workflows_payload = _load_json_artifact(synthesis_input.workflows)
    if workflows_payload is None:
        return _artifact(synthesis_input.document_id, "mermaid_render")
    return _store_text_artifact(
        document_id=synthesis_input.document_id,
        artifact_type="mermaid_render",
        payload=_mermaid_text(workflows_payload),
        content_type="text/plain; charset=utf-8",
    )


@activity.defn(name="generate_frontmatter_activity")
def generate_frontmatter_activity(synthesis_input: SynthesisInput) -> ArtifactRef:
    return _store_text_artifact(
        document_id=synthesis_input.document_id,
        artifact_type="frontmatter",
        payload=_frontmatter_text(synthesis_input),
        content_type="text/yaml; charset=utf-8",
    )


@activity.defn(name="persist_markdown_activity")
def persist_markdown_activity(markdown_draft: ArtifactRef) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=markdown_draft.artifact_id,
        artifact_type=markdown_draft.artifact_type,
        version=markdown_draft.version,
        uri=markdown_draft.uri.replace("memory://", "memory://persisted/"),
    )


@activity.defn(name="validate_markdown_against_chunks_activity")
def validate_markdown_against_chunks_activity(validation_input: ValidationInput) -> ValidationReport:
    markdown_payload = _load_artifact_payload(validation_input.markdown_draft)
    chunk_payload = _load_json_artifact(validation_input.chunk_set)
    if markdown_payload is None or chunk_payload is None:
        return ValidationReport(passed=True, issues=[])

    markdown = markdown_payload.decode("utf-8")
    issues: list[str] = []
    data_schema_section = _markdown_section_body(markdown, "Data Schema")
    business_rules_section = _markdown_section_body(markdown, "Business Rules")
    workflows_section = _markdown_section_body(markdown, "Workflows")
    issues.extend(
        _missing_items(
            data_schema_section,
            _prefixed_chunk_items(chunk_payload, "field:"),
            "Missing field coverage in markdown",
        )
    )
    issues.extend(
        _missing_items(
            business_rules_section,
            _prefixed_chunk_items(chunk_payload, "rule:"),
            "Missing rule coverage in markdown",
        )
    )
    issues.extend(
        _missing_items(
            workflows_section,
            _prefixed_chunk_items(chunk_payload, "workflow:"),
            "Missing workflow coverage in markdown",
        )
    )
    return ValidationReport(passed=not issues, issues=issues)
