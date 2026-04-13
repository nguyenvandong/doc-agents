from __future__ import annotations

from typing import Final


WORKFLOW_NAME: Final[str] = "DocumentWorkflow"

ACTIVITY_NAMES: Final[tuple[str, ...]] = (
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

REVIEW_SIGNAL_NAMES: Final[dict[str, str]] = {
    "ir_review_submitted": "ir_review_submitted",
    "ir_artifact_updated": "ir_artifact_updated",
    "final_review_submitted": "final_review_submitted",
}


def build_workflow_start_payload(document_id: str, source_uri: str) -> dict[str, str]:
    return {
        "workflow_name": WORKFLOW_NAME,
        "document_id": document_id,
        "source_uri": source_uri,
    }
