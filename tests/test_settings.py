from __future__ import annotations

import unittest

from doc_agents.settings import StorageSettings


class StorageSettingsTest(unittest.TestCase):
    def test_from_env_reads_postgres_and_minio_settings(self) -> None:
        settings = StorageSettings.from_env(
            {
                "DOC_AGENTS_POSTGRES_DSN": "postgresql://user:pass@localhost:5432/doc_agents",
                "DOC_AGENTS_MINIO_ENDPOINT": "localhost:9000",
                "DOC_AGENTS_MINIO_ACCESS_KEY": "minioadmin",
                "DOC_AGENTS_MINIO_SECRET_KEY": "minioadmin",
                "DOC_AGENTS_MINIO_BUCKET": "doc-artifacts",
                "DOC_AGENTS_MINIO_SECURE": "false",
            }
        )

        self.assertEqual(settings.postgres_dsn, "postgresql://user:pass@localhost:5432/doc_agents")
        self.assertEqual(settings.minio_endpoint, "localhost:9000")
        self.assertFalse(settings.minio_secure)

    def test_from_env_requires_all_fields(self) -> None:
        with self.assertRaises(ValueError):
            StorageSettings.from_env({})


if __name__ == "__main__":
    unittest.main()
