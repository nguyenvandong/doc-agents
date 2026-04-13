from __future__ import annotations

import json
import unittest

from doc_agents.activities import (
    ExtractInput,
    configure_activity_dependencies,
    extract_business_rules_activity,
    extract_data_schema_activity,
    extract_workflows_activity,
)
from tests.test_activity_parser_integration import (
    FakeArtifactRepository,
    build_chunk_set_payload,
    persisted_artifact,
)


class ExtractionActivitiesTest(unittest.TestCase):
    def tearDown(self) -> None:
        configure_activity_dependencies(artifact_repository=None)

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

        result = extract_data_schema_activity(
            ExtractInput(document_id="doc-schema", chunk_set=chunk_set)
        )

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

        result = extract_business_rules_activity(
            ExtractInput(document_id="doc-rules", chunk_set=chunk_set)
        )

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

        result = extract_workflows_activity(
            ExtractInput(document_id="doc-workflows", chunk_set=chunk_set)
        )

        payload = json.loads(repository.load_bytes(result).decode("utf-8"))
        self.assertEqual(
            payload["steps"],
            [
                {"text": "System validates application before approval.", "source_chunk_id": "chunk-0"},
                {"text": "Manager approves eligible applications.", "source_chunk_id": "chunk-1"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
