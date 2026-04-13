from __future__ import annotations

import os

from minio import Minio
import psycopg

from .models import ArtifactRef
from .settings import StorageSettings
from .storage import ArtifactMetadataRecord, MinioArtifactBlobStore, PostgresArtifactCatalog


class ArtifactRepository:
    def __init__(self, blob_store: MinioArtifactBlobStore, catalog: PostgresArtifactCatalog) -> None:
        self.blob_store = blob_store
        self.catalog = catalog

    def store_bytes(
        self,
        *,
        workflow_id: str,
        document_id: str,
        artifact_type: str,
        payload: bytes,
        content_type: str,
        version: int | None = 1,
    ) -> ArtifactRef:
        resolved_version = version if version is not None else self.catalog.next_version(workflow_id, artifact_type)
        artifact = ArtifactRef(
            artifact_id=f"{document_id}-{artifact_type}-v{resolved_version}",
            artifact_type=artifact_type,
            version=resolved_version,
            uri="",
        )
        object_key = self.blob_store.put_bytes(
            workflow_id=workflow_id,
            artifact=artifact,
            payload=payload,
            content_type=content_type,
        )
        persisted_artifact = ArtifactRef(
            artifact_id=artifact.artifact_id,
            artifact_type=artifact.artifact_type,
            version=artifact.version,
            uri=f"s3://{self.blob_store.bucket_name}/{object_key}",
        )
        self.catalog.upsert_artifact(
            ArtifactMetadataRecord(
                workflow_id=workflow_id,
                document_id=document_id,
                artifact=persisted_artifact,
                content_type=content_type,
                size_bytes=len(payload),
            )
        )
        return persisted_artifact

    def load_bytes(self, artifact: ArtifactRef) -> bytes:
        return self.blob_store.get_bytes(artifact.uri)

    def load_latest(self, workflow_id: str, artifact_type: str) -> ArtifactRef | None:
        return self.catalog.latest_artifact(workflow_id, artifact_type)


def build_repository(settings: StorageSettings) -> ArtifactRepository:
    blob_store = MinioArtifactBlobStore(
        client=Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        ),
        bucket_name=settings.minio_bucket,
    )
    catalog = PostgresArtifactCatalog(
        connection_factory=lambda: psycopg.connect(settings.postgres_dsn)
    )
    # ensure schema exists for fresh Postgres instances
    catalog.initialize_schema()
    return ArtifactRepository(blob_store=blob_store, catalog=catalog)


def build_repository_from_env() -> ArtifactRepository:
    settings = StorageSettings.from_env(os.environ)
    return build_repository(settings)
