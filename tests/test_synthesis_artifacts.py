from __future__ import annotations

import json
import unittest

from doc_agents.activities import (
    SynthesisInput,
    configure_activity_dependencies,
    generate_frontmatter_activity,
    render_mermaid_activity,
)
from tests.test_activity_parser_integration import FakeArtifactRepository, persisted_artifact


def build_synthesis_input(repository: FakeArtifactRepository, document_id: str) -> SynthesisInput:
    data_schema = persisted_artifact(
        repository,
        document_id=document_id,
        artifact_type="data_schema_json",
        payload=json.dumps(
            {
                "source_chunk_artifact_id": f"{document_id}-semantic_chunks-v1",
                "fields": [{"name": "Customer ID", "source_chunk_id": "chunk-0"}],
                "evidence": ["Customer ID"],
            }
        ).encode("utf-8"),
    )
    business_rules = persisted_artifact(
        repository,
        document_id=document_id,
        artifact_type="business_rules_json",
        payload=json.dumps(
            {
                "source_chunk_artifact_id": f"{document_id}-semantic_chunks-v1",
                "rules": [{"text": "Applicant must be 18 years old.", "source_chunk_id": "chunk-1"}],
                "evidence": ["Applicant must be 18 years old."],
            }
        ).encode("utf-8"),
    )
    workflows = persisted_artifact(
        repository,
        document_id=document_id,
        artifact_type="workflows_json",
        payload=json.dumps(
            {
                "source_chunk_artifact_id": f"{document_id}-semantic_chunks-v1",
                "steps": [{"text": "System validates application before approval.", "source_chunk_id": "chunk-2"}],
                "evidence": ["System validates application before approval."],
            }
        ).encode("utf-8"),
    )
    return SynthesisInput(
        document_id=document_id,
        data_schema=data_schema,
        business_rules=business_rules,
        workflows=workflows,
    )


class SynthesisArtifactsTest(unittest.TestCase):
    def tearDown(self) -> None:
        configure_activity_dependencies(artifact_repository=None)

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


if __name__ == "__main__":
    unittest.main()
