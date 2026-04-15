from __future__ import annotations

import asyncio

from doc_agents.api_settings import ApiSettings
from doc_agents.temporal_runtime import connect_client, create_worker


async def main() -> None:
    settings = ApiSettings.from_env()
    client = await connect_client(
        address=settings.temporal_address,
        namespace=settings.temporal_namespace,
    )
    worker = create_worker(client, task_queue=settings.temporal_task_queue)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
