# Docker Compose Environment Design

**Date:** 2026-04-12

## Goal

Provision the infrastructure that the current codebase depends on through a single Docker Compose file, while keeping the Python application and worker processes running locally from the repository virtual environment.

## Scope

This change will cover:

- a single `docker-compose.yml` for local infrastructure
- environment values that match the current codebase
- enough bootstrap so the environment is usable immediately after `docker compose up -d`

This change will not cover:

- containerizing the Python app or worker
- production deployment hardening
- reverse proxy, TLS, auth, or secrets management

## Current Runtime Requirements

The implemented codebase currently depends on:

- Python dependencies from `requirements.txt`
- Temporal server reachable at `DOC_AGENTS_TEMPORAL_ADDRESS` (default `localhost:7233`)
- PostgreSQL for artifact metadata via `DOC_AGENTS_POSTGRES_DSN`
- MinIO for artifact blob storage via `DOC_AGENTS_MINIO_*`

The current storage code expects:

- Postgres DSN such as `postgresql://user:pass@localhost:5432/doc_agents`
- MinIO endpoint such as `localhost:9000`
- bucket name such as `doc-artifacts`

## Chosen Approach

Use one Docker Compose file that runs only infrastructure services:

- `postgres-app`
- `postgres-temporal`
- `minio`
- `minio-init`
- `temporal`
- `temporal-ui`

The recommended local development model stays:

1. start infrastructure with Docker Compose
2. export `DOC_AGENTS_*` environment variables locally
3. run the Python code from the repo virtualenv

## Service Design

### 1. `postgres-app`

Purpose:

- stores application artifact metadata, including `artifact_records`

Configuration:

- exposed on local port `5432`
- database `doc_agents`
- simple local credentials (`postgres` / `postgres`)
- named volume for persistence

### 2. `postgres-temporal`

Purpose:

- dedicated database backend for Temporal

Configuration:

- separate container and named volume
- exposed on a different local port than the app database

Rationale:

- avoids mixing Temporal schema with application schema
- makes reset and troubleshooting easier
- reduces coupling between Temporal upgrades and application data

### 3. `minio`

Purpose:

- stores artifact payloads referenced by `ArtifactRef.uri`

Configuration:

- API on `9000`
- console on `9001`
- local single-node mode
- named volume for persistence
- default local credentials matching the repo tests/examples (`minioadmin` / `minioadmin`)

### 4. `minio-init`

Purpose:

- bootstrap the `doc-artifacts` bucket automatically after MinIO becomes reachable

Configuration:

- one-shot helper container using the MinIO client
- creates the bucket idempotently

Rationale:

- avoids a manual first-run step
- keeps local setup to one `docker compose up -d`

### 5. `temporal`

Purpose:

- durable workflow engine for `DocumentWorkflow`

Configuration:

- exposed on local port `7233`
- configured to use `postgres-temporal`
- local self-hosted dev profile only

### 6. `temporal-ui`

Purpose:

- inspect workflow executions, statuses, and signals during development

Configuration:

- exposed on local port `8233`
- points to the `temporal` service in the same Compose network

## Environment Mapping For Local Python Processes

The compose-based environment should map to these values for local execution:

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

## Startup Behavior

Expected startup flow:

1. `postgres-app` and `postgres-temporal` start first
2. `minio` starts and becomes healthy
3. `minio-init` creates the `doc-artifacts` bucket
4. `temporal` starts once its database backend is reachable
5. `temporal-ui` starts after `temporal`

The compose file should prefer explicit readiness checks where possible so that dependent services do not start before their backing services are actually ready.

## Deliverables

The implementation should add:

- `docker-compose.yml`
- a short environment reference for local execution, preferably `.env.example` unless an existing doc is a better fit

## Success Criteria

After implementation:

- `docker compose up -d` brings up all required infrastructure locally
- no manual MinIO bucket creation is needed
- the repo can be pointed at the running stack through `DOC_AGENTS_*` environment variables
- Temporal UI is reachable locally for workflow inspection

## Notes

- This is a developer-local environment design, not a production deployment design.
- The repo is not currently a Git repository in this workspace, so the spec can be written here but not committed from this environment.
