import json
import unittest

from doc_agents.activities import (
    SynthesisInput,
    configure_activity_dependencies,
    synthesize_markdown_activity,
)
from doc_agents.parser import DocxParser
from tests.test_activity_parser_integration import (
    FakeArtifactRepository,
    persisted_artifact,
)


class StorageBackedPipelineTest(unittest.TestCase):
    def tearDown(self) -> None:
        configure_activity_dependencies(docx_parser=DocxParser(), artifact_repository=None)

    def test_storage_backed_pipeline_creates_new_markdown_version_after_rerun(self) -> None:
        repository = FakeArtifactRepository()
        configure_activity_dependencies(docx_parser=DocxParser(), artifact_repository=repository)
        data_schema = persisted_artifact(
            repository,
            document_id="doc-storage",
            artifact_type="data_schema_json",
            payload=json.dumps(
                {
                    "source_chunk_artifact_id": "doc-storage-semantic_chunks-v1",
                    "fields": [{"name": "Customer ID", "source_chunk_id": "chunk-0"}],
                    "evidence": ["Customer ID"],
                }
            ).encode("utf-8"),
        )
        business_rules = persisted_artifact(
            repository,
            document_id="doc-storage",
            artifact_type="business_rules_json",
            payload=json.dumps(
                {
                    "source_chunk_artifact_id": "doc-storage-semantic_chunks-v1",
                    "rules": [{"text": "Applicant must be 18 years old.", "source_chunk_id": "chunk-1"}],
                    "evidence": ["Applicant must be 18 years old."],
                }
            ).encode("utf-8"),
        )
        workflows = persisted_artifact(
            repository,
            document_id="doc-storage",
            artifact_type="workflows_json",
            payload=json.dumps(
                {
                    "source_chunk_artifact_id": "doc-storage-semantic_chunks-v1",
                    "steps": [{"text": "System validates application before approval.", "source_chunk_id": "chunk-2"}],
                    "evidence": ["System validates application before approval."],
                }
            ).encode("utf-8"),
        )
        synthesis_input = SynthesisInput(
            document_id="doc-storage",
            data_schema=data_schema,
            business_rules=business_rules,
            workflows=workflows,
        )

        first = synthesize_markdown_activity(synthesis_input)
        second = synthesize_markdown_activity(synthesis_input)

        self.assertEqual(first.version, 1)
        self.assertEqual(second.version, 2)
        self.assertNotEqual(first.uri, second.uri)
        self.assertIn("Customer ID", repository.load_bytes(second).decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
