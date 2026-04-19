from __future__ import annotations

from io import BytesIO
import unittest

from doc_agents.repository import ArtifactRepository
from doc_agents.storage import MinioArtifactBlobStore, PostgresArtifactCatalog


class FakeMinioClient:
    def __init__(self) -> None:
        self.buckets: set[str] = set()
        self.objects: dict[tuple[str, str], bytes] = {}

    def bucket_exists(self, bucket_name: str) -> bool:
        return bucket_name in self.buckets

    def make_bucket(self, bucket_name: str) -> None:
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
        self.objects[(bucket_name, object_name)] = data.read()

    def get_object(self, bucket_name: str, object_name: str):
        return FakeObjectResponse(self.objects[(bucket_name, object_name)])


class FakeObjectResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return self.payload

    def close(self) -> None:
        return None

    def release_conn(self) -> None:
        return None


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


class ArtifactRepositoryTest(unittest.TestCase):
    def test_store_bytes_persists_blob_and_metadata(self) -> None:
        blob_store = MinioArtifactBlobStore(client=FakeMinioClient(), bucket_name="doc-artifacts")
        connection = FakeConnection()
        catalog = PostgresArtifactCatalog(connection_factory=lambda: connection)
        repository = ArtifactRepository(blob_store=blob_store, catalog=catalog)

        artifact = repository.store_bytes(
            workflow_id="wf-7",
            document_id="doc-7",
            artifact_type="parsed_document",
            payload=b'{"blocks": []}',
            content_type="application/json",
            version=1,
        )

        self.assertEqual(
            artifact.uri,
            "s3://doc-artifacts/wf-7/parsed_document/v1/doc-7-parsed_document-v1.json",
        )
        self.assertIn("insert into artifact_records", connection.commands[-1][0].lower())
        self.assertEqual(connection.commands[-1][1][1], "doc-7")

    def test_load_bytes_reads_blob_from_artifact_uri(self) -> None:
        blob_store = MinioArtifactBlobStore(client=FakeMinioClient(), bucket_name="doc-artifacts")
        connection = FakeConnection()
        catalog = PostgresArtifactCatalog(connection_factory=lambda: connection)
        repository = ArtifactRepository(blob_store=blob_store, catalog=catalog)

        artifact = repository.store_bytes(
            workflow_id="wf-8",
            document_id="doc-8",
            artifact_type="semantic_chunks",
            payload=b'{"chunks": [{"text": "Eligibility"}]}',
            content_type="application/json",
            version=1,
        )

        payload = repository.load_bytes(artifact)

        self.assertEqual(payload, b'{"chunks": [{"text": "Eligibility"}]}')

    def test_store_bytes_auto_increments_version_when_same_artifact_type_exists(self) -> None:
        blob_store = MinioArtifactBlobStore(client=FakeMinioClient(), bucket_name="doc-artifacts")
        connection = FakeConnection()
        connection.fetchone_result = (1,)
        catalog = PostgresArtifactCatalog(connection_factory=lambda: connection)
        repository = ArtifactRepository(blob_store=blob_store, catalog=catalog)

        artifact = repository.store_bytes(
            workflow_id="wf-9",
            document_id="doc-9",
            artifact_type="data_schema_json",
            payload=b'{"fields": []}',
            content_type="application/json",
            version=None,
        )

        self.assertEqual(artifact.version, 2)
        self.assertTrue(artifact.uri.endswith("/v2/doc-9-data_schema_json-v2.json"))

    def test_load_latest_returns_highest_version_for_artifact_type(self) -> None:
        blob_store = MinioArtifactBlobStore(client=FakeMinioClient(), bucket_name="doc-artifacts")
        connection = FakeConnection()
        connection.fetchone_result = (
            "doc-9-data_schema_json-v3",
            "data_schema_json",
            3,
            "s3://doc-artifacts/wf-9/data_schema_json/v3/doc-9-data_schema_json-v3.json",
        )
        catalog = PostgresArtifactCatalog(connection_factory=lambda: connection)
        repository = ArtifactRepository(blob_store=blob_store, catalog=catalog)

        artifact = repository.load_latest(workflow_id="wf-9", artifact_type="data_schema_json")

        self.assertIsNotNone(artifact)
        assert artifact is not None
        self.assertEqual(artifact.version, 3)
        self.assertEqual(artifact.artifact_id, "doc-9-data_schema_json-v3")


    def test_build_repository_initializes_schema(self) -> None:
        import unittest.mock as mock
        from doc_agents.repository import build_repository
        from doc_agents.settings import StorageSettings

        # patch Minio and psycopg.connect to avoid real network/database
        connection = FakeConnection()
        with mock.patch("doc_agents.repository.Minio", return_value=FakeMinioClient()) as _minio_patch, \
             mock.patch("doc_agents.repository.psycopg.connect", return_value=connection) as _pg_patch:
            settings = StorageSettings(
                postgres_dsn="postgres://user:pass@localhost/db",
                minio_endpoint="minio:9000",
                minio_access_key="ak",
                minio_secret_key="sk",
                minio_bucket="doc-artifacts",
            )
            _ = build_repository(settings)

        # the catalog should have executed the schema creation SQL on connection enter
        self.assertTrue(len(connection.commands) > 0)
        first_sql = connection.commands[0][0].lower()
        self.assertIn("create table if not exists artifact_records", first_sql)


if __name__ == "__main__":
    unittest.main()
