# Docker Compose Environment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a one-command local infrastructure stack for this repo with Docker Compose, plus matching environment defaults so the Python code can run locally against Postgres, MinIO, and Temporal.

**Architecture:** Keep the Python app and worker out of Docker for now. Add a Compose-managed infrastructure stack with separate Postgres instances for application metadata and Temporal, bootstrap the MinIO bucket automatically, and make the repository initialize its own metadata schema so the stack is usable immediately after startup.

**Tech Stack:** Docker Compose, PostgreSQL, MinIO, Temporal, Temporal UI, Python 3.12, `unittest`

---

## File Structure

**Create**

- `E:\workspace\doc-agents\docker-compose.yml` — local infrastructure stack for app Postgres, Temporal Postgres, MinIO, MinIO bucket bootstrap, Temporal, and Temporal UI
- `E:\workspace\doc-agents\.env.example` — local environment values for running Python processes against the Compose stack

**Modify**

- `E:\workspace\doc-agents\doc_agents\repository.py` — initialize the Postgres artifact metadata schema when building the real repository from environment-backed settings
- `E:\workspace\doc-agents\tests\test_repository.py` — cover repository bootstrap behavior so Compose-based Postgres does not require a manual SQL step

**Test**

- `E:\workspace\doc-agents\tests\test_repository.py`
- `E:\workspace\doc-agents\tests\test_settings.py`
- `E:\workspace\doc-agents\tests\test_temporal_runtime.py`

**Note**

- The current workspace is not a Git repository, so commit steps are intentionally omitted from this plan.

---

### Task 1: Make the repository auto-create its metadata schema

**Files:**
- Modify: `E:\workspace\doc-agents\tests\test_repository.py`
- Modify: `E:\workspace\doc-agents\doc_agents\repository.py`
- Test: `E:\workspace\doc-agents\tests\test_repository.py`

- [ ] **Step 1: Write the failing repository bootstrap test**

Add this test and import to `E:\workspace\doc-agents\tests\test_repository.py`:

```python
from unittest.mock import patch

from doc_agents.repository import ArtifactRepository, build_repository
from doc_agents.settings import StorageSettings
```

```python
    def test_build_repository_initializes_catalog_schema(self) -> None:
        connection = FakeConnection()
        settings = StorageSettings(
            postgres_dsn="postgresql://postgres:postgres@localhost:5432/doc_agents",
            minio_endpoint="localhost:9000",
            minio_access_key="minioadmin",
            minio_secret_key="minioadmin",
            minio_bucket="doc-artifacts",
            minio_secure=False,
        )

        with patch("doc_agents.repository.Minio", return_value=FakeMinioClient()):
            with patch("doc_agents.repository.psycopg.connect", return_value=connection):
                repository = build_repository(settings)

        self.assertIsInstance(repository, ArtifactRepository)
        self.assertIn(
            "create table if not exists artifact_records",
            connection.commands[0][0].lower(),
        )
```

- [ ] **Step 2: Run the targeted repository tests to verify the new test fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_repository -v
```

Expected: FAIL because `build_repository(...)` currently returns without calling `initialize_schema()`.

- [ ] **Step 3: Implement schema initialization in the real repository builder**

Update `E:\workspace\doc-agents\doc_agents\repository.py`:

```python
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
    catalog.initialize_schema()
    return ArtifactRepository(blob_store=blob_store, catalog=catalog)
```

- [ ] **Step 4: Run the targeted repository tests to verify they pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_repository -v
```

Expected: PASS, including the new schema-bootstrap test.

---

### Task 2: Add a checked-in environment reference for the Compose stack

**Files:**
- Create: `E:\workspace\doc-agents\.env.example`

- [ ] **Step 1: Create the environment reference file**

Create `E:\workspace\doc-agents\.env.example` with this exact content:

```env
DOC_AGENTS_POSTGRES_DSN=postgresql://postgres:postgres@localhost:5432/doc_agents
DOC_AGENTS_MINIO_ENDPOINT=localhost:9000
DOC_AGENTS_MINIO_ACCESS_KEY=minioadmin
DOC_AGENTS_MINIO_SECRET_KEY=minioadmin
DOC_AGENTS_MINIO_BUCKET=doc-artifacts
DOC_AGENTS_MINIO_SECURE=false
DOC_AGENTS_TEMPORAL_ADDRESS=localhost:7233
DOC_AGENTS_TEMPORAL_NAMESPACE=default
DOC_AGENTS_TEMPORAL_TASK_QUEUE=doc-agents
```

- [ ] **Step 2: Verify the file matches the implemented settings names**

Run:

```powershell
Get-Content .env.example
```

Expected: the file contains the same `DOC_AGENTS_*` variable names used by `doc_agents.settings.StorageSettings` and `doc_agents.api_settings.ApiSettings`.

---

### Task 3: Add the local Docker Compose stack

**Files:**
- Create: `E:\workspace\doc-agents\docker-compose.yml`

- [ ] **Step 1: Create the Compose file with the full infrastructure stack**

Create `E:\workspace\doc-agents\docker-compose.yml` with this exact content:

```yaml
services:
  postgres-app:
    image: postgres:15
    environment:
      POSTGRES_DB: doc_agents
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    volumes:
      - postgres-app-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d doc_agents"]
      interval: 5s
      timeout: 5s
      retries: 20

  postgres-temporal:
    image: postgres:15
    environment:
      POSTGRES_DB: temporal
      POSTGRES_USER: temporal
      POSTGRES_PASSWORD: temporal
    ports:
      - "5433:5432"
    volumes:
      - postgres-temporal-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U temporal -d temporal"]
      interval: 5s
      timeout: 5s
      retries: 20

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio-data:/data

  minio-init:
    image: minio/mc:latest
    depends_on:
      minio:
        condition: service_started
    entrypoint: >
      /bin/sh -c "
      until mc alias set local http://minio:9000 minioadmin minioadmin; do
        echo 'Waiting for MinIO...';
        sleep 2;
      done;
      mc mb --ignore-existing local/doc-artifacts;
      exit 0;
      "

  temporal:
    image: temporalio/auto-setup:latest
    depends_on:
      postgres-temporal:
        condition: service_healthy
    environment:
      DB: postgres12
      DB_PORT: 5432
      POSTGRES_USER: temporal
      POSTGRES_PWD: temporal
      POSTGRES_SEEDS: postgres-temporal
      DBNAME: temporal
      VISIBILITY_DBNAME: temporal_visibility
      DEFAULT_NAMESPACE: default
    ports:
      - "7233:7233"

  temporal-ui:
    image: temporalio/ui:latest
    depends_on:
      temporal:
        condition: service_started
    environment:
      TEMPORAL_ADDRESS: temporal:7233
      TEMPORAL_DEFAULT_NAMESPACE: default
    ports:
      - "8233:8080"

volumes:
  postgres-app-data:
  postgres-temporal-data:
  minio-data:
```

- [ ] **Step 2: Validate the Compose file shape before starting containers**

Run:

```powershell
docker compose config
```

Expected: Docker prints the normalized Compose configuration without YAML or schema errors.

- [ ] **Step 3: Start the infrastructure stack**

Run:

```powershell
docker compose up -d
```

Expected: all six services are created; `minio-init` may exit successfully after creating the bucket.

- [ ] **Step 4: Verify service status**

Run:

```powershell
docker compose ps
```

Expected:

- `postgres-app`, `postgres-temporal`, `minio`, `temporal`, and `temporal-ui` are running
- `minio-init` has exited with code `0`

- [ ] **Step 5: Verify the MinIO bucket bootstrap succeeded**

Run:

```powershell
docker compose logs minio-init
```

Expected: the logs show successful alias setup and bucket creation, or an idempotent already-exists message.

- [ ] **Step 6: Verify the local UIs/endpoints are reachable**

Run:

```powershell
Invoke-WebRequest http://localhost:9001 | Select-Object -ExpandProperty StatusCode
Invoke-WebRequest http://localhost:8233 | Select-Object -ExpandProperty StatusCode
```

Expected: both commands return `200`.

---

### Task 4: Run the repo verification commands against the new environment-aware changes

**Files:**
- Modify: `E:\workspace\doc-agents\doc_agents\repository.py`
- Modify: `E:\workspace\doc-agents\tests\test_repository.py`
- Create: `E:\workspace\doc-agents\.env.example`
- Create: `E:\workspace\doc-agents\docker-compose.yml`
- Test: `E:\workspace\doc-agents\tests\test_repository.py`
- Test: `E:\workspace\doc-agents\tests\test_settings.py`
- Test: `E:\workspace\doc-agents\tests\test_temporal_runtime.py`

- [ ] **Step 1: Run the focused Python tests that cover the touched code paths**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_repository tests.test_settings tests.test_temporal_runtime -v
```

Expected: PASS.

- [ ] **Step 2: Run the full test suite to ensure the repo still passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Expected: PASS.

- [ ] **Step 3: Record the local startup sequence for the engineer executing the plan**

Use these commands after implementation:

```powershell
docker compose up -d
Get-Content .env.example
```

The executing engineer should then export the values from `.env.example` into their shell before running the Python app or worker locally.
