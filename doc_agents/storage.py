from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Callable
from urllib.parse import urlparse

from minio import Minio
import psycopg

from .models import ArtifactRef


@dataclass(frozen=True)
class ArtifactMetadataRecord:
    workflow_id: str
    document_id: str
    artifact: ArtifactRef
    content_type: str
    size_bytes: int


class MinioArtifactBlobStore:
    _ARTIFACT_EXTENSIONS = {
        "parsed_document": ".json",
        "semantic_chunks": ".json",
        "data_schema_json": ".json",
        "business_rules_json": ".json",
        "workflows_json": ".json",
        "markdown_draft": ".md",
        "frontmatter": ".yaml",
        "mermaid_render": ".mmd",
    }

    def __init__(self, client: Minio, bucket_name: str) -> None:
        self.client = client
        self.bucket_name = bucket_name
        self._bucket_ready = False

    def put_bytes(
        self,
        *,
        workflow_id: str,
        artifact: ArtifactRef,
        payload: bytes,
        content_type: str,
    ) -> str:
        self.ensure_bucket()
        object_key = self.object_key_for(workflow_id=workflow_id, artifact=artifact)
        self.client.put_object(
            self.bucket_name,
            object_key,
            BytesIO(payload),
            len(payload),
            content_type=content_type,
            metadata={
                "artifact-id": artifact.artifact_id,
                "artifact-type": artifact.artifact_type,
                "artifact-version": str(artifact.version),
            },
        )
        return object_key

    def ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        if not self.client.bucket_exists(self.bucket_name):
            self.client.make_bucket(self.bucket_name)
        self._bucket_ready = True

    @staticmethod
    def object_key_for(*, workflow_id: str, artifact: ArtifactRef) -> str:
        extension = MinioArtifactBlobStore._ARTIFACT_EXTENSIONS.get(artifact.artifact_type, ".bin")
        return f"{workflow_id}/{artifact.artifact_type}/v{artifact.version}/{artifact.artifact_id}{extension}"

    def get_bytes(self, artifact_uri: str) -> bytes:
        parsed = urlparse(artifact_uri)
        if parsed.scheme != "s3":
            raise ValueError(f"Unsupported artifact URI: {artifact_uri}")
        bucket_name = parsed.netloc
        object_name = parsed.path.lstrip("/")
        response = self.client.get_object(bucket_name, object_name)
        try:
            return response.read()
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
            release_conn = getattr(response, "release_conn", None)
            if callable(release_conn):
                release_conn()


class PostgresArtifactCatalog:
    def __init__(self, connection_factory: Callable[[], psycopg.Connection | object]) -> None:
        self.connection_factory = connection_factory

    def initialize_schema(self) -> None:
        with self.connection_factory() as connection:
            connection.execute(
                """
                create table if not exists artifact_records (
                    workflow_id text not null,
                    document_id text not null,
                    artifact_id text not null,
                    artifact_type text not null,
                    version integer not null,
                    uri text not null,
                    content_type text not null,
                    size_bytes bigint not null,
                    created_at timestamptz not null default now(),
                    primary key (workflow_id, artifact_type, version)
                )
                """
            )

    def upsert_artifact(self, record: ArtifactMetadataRecord) -> None:
        with self.connection_factory() as connection:
            connection.execute(
                """
                insert into artifact_records (
                    workflow_id,
                    document_id,
                    artifact_id,
                    artifact_type,
                    version,
                    uri,
                    content_type,
                    size_bytes
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (workflow_id, artifact_type, version) do update
                set artifact_id = excluded.artifact_id,
                    uri = excluded.uri,
                    content_type = excluded.content_type,
                    size_bytes = excluded.size_bytes
                """,
                (
                    record.workflow_id,
                    record.document_id,
                    record.artifact.artifact_id,
                    record.artifact.artifact_type,
                    record.artifact.version,
                    record.artifact.uri,
                    record.content_type,
                    record.size_bytes,
                ),
            )

    def next_version(self, workflow_id: str, artifact_type: str) -> int:
        with self.connection_factory() as connection:
            cursor = connection.execute(
                """
                select coalesce(max(version), 0)
                from artifact_records
                where workflow_id = %s and artifact_type = %s
                """,
                (workflow_id, artifact_type),
            )
            row = cursor.fetchone()
        return int(row[0]) + 1 if row is not None else 1

    def latest_artifact(self, workflow_id: str, artifact_type: str) -> ArtifactRef | None:
        with self.connection_factory() as connection:
            cursor = connection.execute(
                """
                select artifact_id, artifact_type, version, uri
                from artifact_records
                where workflow_id = %s and artifact_type = %s
                order by version desc
                limit 1
                """,
                (workflow_id, artifact_type),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return ArtifactRef(
            artifact_id=row[0],
            artifact_type=row[1],
            version=int(row[2]),
            uri=row[3],
        )
