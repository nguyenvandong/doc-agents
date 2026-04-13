import unittest

from doc_agents.temporal_contract import ACTIVITY_NAMES, WORKFLOW_NAME
from doc_agents.temporal_runtime import build_worker_config


class TemporalRuntimeTest(unittest.TestCase):
    def test_worker_config_uses_contract_names(self) -> None:
        config = build_worker_config(task_queue="doc-agents")
        self.assertEqual(config["workflow_name"], WORKFLOW_NAME)
        self.assertEqual(config["task_queue"], "doc-agents")
        self.assertEqual(config["activity_names"], list(ACTIVITY_NAMES))

    def test_worker_config_registers_single_workflow(self) -> None:
        config = build_worker_config(task_queue="doc-agents")
        self.assertEqual(len(config["workflows"]), 1)
        self.assertEqual(len(config["activities"]), len(ACTIVITY_NAMES))


if __name__ == "__main__":
    unittest.main()
