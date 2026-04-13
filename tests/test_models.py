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
