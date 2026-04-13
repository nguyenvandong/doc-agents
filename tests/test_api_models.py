import unittest

from doc_agents.api_models import (
    ArtifactUpdateRequest,
    ReviewRequest,
    StartWorkflowRequest,
)
from doc_agents.api_settings import ApiSettings


class ApiModelsTest(unittest.TestCase):
    def test_start_workflow_request_allows_optional_task_queue(self) -> None:
        request = StartWorkflowRequest(
            document_id="doc-123",
            source_uri="file:///tmp/source.docx",
        )
        self.assertIsNone(request.task_queue)
        self.assertFalse(request.enable_vision)

    def test_artifact_update_request_rejects_mismatched_target_and_artifact_type(self) -> None:
        with self.assertRaises(ValueError):
            ArtifactUpdateRequest(
                target="data_schema",
                artifact_id="doc-123-business_rules_json-v2",
                artifact_type="business_rules_json",
                version=2,
                uri="s3://doc-artifacts/doc-123/business_rules_json/v2/doc-123-business_rules_json-v2.bin",
            )

    def test_review_request_accepts_known_actions(self) -> None:
        request = ReviewRequest(
            action="reject",
            comment="missing rules",
            targets=["business_rules"],
        )
        self.assertEqual(request.action, "reject")
        self.assertEqual(request.targets, ["business_rules"])


class ApiSettingsTest(unittest.TestCase):
    def test_from_env_uses_defaults_when_temporal_env_not_set(self) -> None:
        settings = ApiSettings.from_env({})
        self.assertEqual(settings.temporal_address, "localhost:7233")
        self.assertEqual(settings.temporal_namespace, "default")
        self.assertEqual(settings.temporal_task_queue, "doc-agents")


if __name__ == "__main__":
    unittest.main()
