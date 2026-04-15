import unittest
from unittest.mock import AsyncMock, patch

from doc_agents.api_settings import ApiSettings


class RunWorkerTest(unittest.IsolatedAsyncioTestCase):
    async def test_main_connects_client_and_runs_worker_with_api_settings(self) -> None:
        from run_worker import main

        fake_worker = AsyncMock()
        fake_worker.run = AsyncMock()
        settings = ApiSettings(
            temporal_address="temporal:7233",
            temporal_namespace="default",
            temporal_task_queue="doc-agents",
        )

        with patch("run_worker.ApiSettings.from_env", return_value=settings), patch(
            "run_worker.connect_client",
            new=AsyncMock(return_value="client"),
        ) as connect_client_mock, patch(
            "run_worker.create_worker",
            return_value=fake_worker,
        ) as create_worker_mock:
            await main()

        connect_client_mock.assert_awaited_once_with(
            address="temporal:7233",
            namespace="default",
        )
        create_worker_mock.assert_called_once_with("client", task_queue="doc-agents")
        fake_worker.run.assert_awaited_once_with()


if __name__ == "__main__":
    unittest.main()
