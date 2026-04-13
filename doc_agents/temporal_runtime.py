from __future__ import annotations

import concurrent.futures
from typing import Any

from temporalio.client import Client
from temporalio.worker import Worker

from .activities import (
    extract_business_rules_activity,
    extract_data_schema_activity,
    extract_tables_activity,
    extract_workflows_activity,
    generate_frontmatter_activity,
    parse_docx_activity,
    persist_markdown_activity,
    render_mermaid_activity,
    semantic_chunk_activity,
    store_source_document,
    synthesize_markdown_activity,
    validate_markdown_against_chunks_activity,
    vision_extract_activity,
)
from .temporal_contract import ACTIVITY_NAMES, WORKFLOW_NAME
from .temporal_workflow import TemporalDocumentWorkflow


def registered_workflows() -> list[type]:
    return [TemporalDocumentWorkflow]


def registered_activities() -> list[Any]:
    return [
        store_source_document,
        parse_docx_activity,
        extract_tables_activity,
        semantic_chunk_activity,
        vision_extract_activity,
        extract_data_schema_activity,
        extract_business_rules_activity,
        extract_workflows_activity,
        synthesize_markdown_activity,
        render_mermaid_activity,
        generate_frontmatter_activity,
        persist_markdown_activity,
        validate_markdown_against_chunks_activity,
    ]


def build_worker_config(task_queue: str) -> dict[str, Any]:
    return {
        "workflow_name": WORKFLOW_NAME,
        "task_queue": task_queue,
        "workflows": registered_workflows(),
        "activities": registered_activities(),
        "activity_names": list(ACTIVITY_NAMES),
    }


async def connect_client(address: str = "localhost:7233", namespace: str = "default") -> Client:
    return await Client.connect(address, namespace=namespace)


def create_worker(client: Client, task_queue: str) -> Worker:
    config = build_worker_config(task_queue=task_queue)
    activity_executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)
    return Worker(
        client,
        task_queue=config["task_queue"],
        workflows=config["workflows"],
        activities=config["activities"],
        activity_executor=activity_executor,
    )
