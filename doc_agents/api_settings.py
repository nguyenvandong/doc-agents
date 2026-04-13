from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Mapping


@dataclass(frozen=True)
class ApiSettings:
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "doc-agents"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "ApiSettings":
        env = environ if environ is not None else os.environ
        return cls(
            temporal_address=env.get("DOC_AGENTS_TEMPORAL_ADDRESS", "localhost:7233"),
            temporal_namespace=env.get("DOC_AGENTS_TEMPORAL_NAMESPACE", "default"),
            temporal_task_queue=env.get("DOC_AGENTS_TEMPORAL_TASK_QUEUE", "doc-agents"),
        )
