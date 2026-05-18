# Backend development

## Prerequisites

- Python 3.12
- Docker (optional, for infra services)

## Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Environment

Backend reads env from the root env file selected by `ENV_FILE`.

Example:

```bash
export ENV_FILE=.env.dev
```

Required for most features:

- Neo4j: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`
- Postgres: `PG_DSN` (required for auth/users)

## Run locally

```bash
cd backend
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

Open:

- http://localhost:8000/docs

## Tests

```bash
cd backend
pytest -q
```

## Linting

This repository currently uses ESLint for frontend. Backend linting is not configured.

## Common issues

- If `PG_DSN` is empty, auth endpoints return `503 postgres not configured`.
- If `JWT_SECRET_KEY` is empty, login/refresh will fail.
