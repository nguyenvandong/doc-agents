import unittest

from doc_agents.activities import (
    ValidationInput,
    configure_activity_dependencies,
    validate_markdown_against_chunks_activity,
)
from tests.test_activity_parser_integration import (
    FakeArtifactRepository,
    build_chunk_set_payload,
    persisted_artifact,
)


class ValidationActivityTest(unittest.TestCase):
    def tearDown(self) -> None:
        configure_activity_dependencies(artifact_repository=None)

    def test_validation_reports_missing_field_rule_and_workflow_coverage(self) -> None:
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
                "Missing workflow coverage in markdown: System validates application before approval.",
            ],
        )


if __name__ == "__main__":
    unittest.main()
