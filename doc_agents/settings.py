from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class StorageSettings:
    postgres_dsn: str
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    minio_secure: bool = False

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "StorageSettings":
        required_keys = {
            "DOC_AGENTS_POSTGRES_DSN": "postgres_dsn",
            "DOC_AGENTS_MINIO_ENDPOINT": "minio_endpoint",
            "DOC_AGENTS_MINIO_ACCESS_KEY": "minio_access_key",
            "DOC_AGENTS_MINIO_SECRET_KEY": "minio_secret_key",
            "DOC_AGENTS_MINIO_BUCKET": "minio_bucket",
        }
        missing = [key for key in required_keys if not env.get(key)]
        if missing:
            raise ValueError(f"missing storage settings: {', '.join(missing)}")

        return cls(
            postgres_dsn=env["DOC_AGENTS_POSTGRES_DSN"],
            minio_endpoint=env["DOC_AGENTS_MINIO_ENDPOINT"],
            minio_access_key=env["DOC_AGENTS_MINIO_ACCESS_KEY"],
            minio_secret_key=env["DOC_AGENTS_MINIO_SECRET_KEY"],
            minio_bucket=env["DOC_AGENTS_MINIO_BUCKET"],
            minio_secure=env.get("DOC_AGENTS_MINIO_SECURE", "false").lower() in {"1", "true", "yes"},
        )
