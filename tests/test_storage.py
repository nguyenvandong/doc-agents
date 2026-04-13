from __future__ import annotations

from io import BytesIO
import unittest

from doc_agents.models import ArtifactRef
from doc_agents.storage import (
    ArtifactMetadataRecord,
    MinioArtifactBlobStore,
    PostgresArtifactCatalog,
)


class FakeMinioClient:
    def __init__(self) -> None:
        self.buckets: set[str] = set()
        self.calls: list[tuple] = []

    def bucket_exists(self, bucket_name: str) -> bool:
        self.calls.append(("bucket_exists", bucket_name))
        return bucket_name in self.buckets

    def make_bucket(self, bucket_name: str) -> None:
        self.calls.append(("make_bucket", bucket_name))
        self.buckets.add(bucket_name)

    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: BytesIO,
        length: int,
        content_type: str,
        metadata: dict[str, str],
    ) -> None:
        self.calls.append(
            ("put_object", bucket_name, object_name, data.read(), length, content_type, metadata)
        )


class FakeCursor:
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection

    def fetchone(self):
        return self.connection.fetchone_result


class FakeConnection:
    def __init__(self) -> None:
        self.commands: list[tuple[str, tuple | None]] = []
        self.fetchone_result = None

    def execute(self, query: str, params: tuple | None = None) -> FakeCursor:
        self.commands.append((query, params))
        return FakeCursor(self)

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class MinioArtifactBlobStoreTest(unittest.TestCase):
    def test_put_bytes_creates_bucket_once_and_uploads_object(self) -> None:
        client = FakeMinioClient()
        store = MinioArtifactBlobStore(client=client, bucket_name="doc-artifacts")
        artifact = ArtifactRef(
            artifact_id="a1",
            artifact_type="data_schema_json",
            version=2,
            uri="memory://artifacts/a1",
        )

        object_key = store.put_bytes(
            workflow_id="wf-1",
            artifact=artifact,
            payload=b'{"ok":true}',
            content_type="application/json",
        )

        self.assertEqual(
            object_key,
            "wf-1/data_schema_json/v2/a1.bin",
        )
        self.assertEqual(client.calls[0], ("bucket_exists", "doc-artifacts"))
        self.assertEqual(client.calls[1], ("make_bucket", "doc-artifacts"))
        self.assertEqual(client.calls[2][0:4], ("put_object", "doc-artifacts", object_key, b'{"ok":true}'))


class PostgresArtifactCatalogTest(unittest.TestCase):
    def test_upsert_artifact_metadata_records_expected_values(self) -> None:
        connection = FakeConnection()
        catalog = PostgresArtifactCatalog(connection_factory=lambda: connection)
        record = ArtifactMetadataRecord(
            workflow_id="wf-1",
            document_id="doc-1",
            artifact=ArtifactRef(
                artifact_id="artifact-1",
                artifact_type="markdown_draft",
                version=4,
                uri="s3://doc-artifacts/wf-1/markdown_draft/v4/artifact-1.bin",
            ),
            content_type="text/markdown",
            size_bytes=128,
        )

        catalog.upsert_artifact(record)

        query, params = connection.commands[-1]
        self.assertIn("insert into artifact_records", query.lower())
        self.assertEqual(params[0], "wf-1")
        self.assertEqual(params[1], "doc-1")
        self.assertEqual(params[2], "artifact-1")
        self.assertEqual(params[3], "markdown_draft")
        self.assertEqual(params[4], 4)
        self.assertEqual(params[5], record.artifact.uri)


if __name__ == "__main__":
    unittest.main()
