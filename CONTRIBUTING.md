# Contributing to opama

Thanks for your interest in improving opama! This guide covers everything you
need to get a development environment running and land a change.

## Development setup

Everything runs in Docker — you don't need Python, Node, or PostgreSQL on your
host.

```bash
git clone <your fork>
cd opama
./opama.sh setup     # wizard: choose "local" auth — no external accounts needed
./opama.sh start
```

- UI: http://localhost:5173
- API + interactive docs: http://localhost:6000/docs

After code changes:

```bash
# Backend (Python) — requires container recreate:
docker compose up -d --no-deps --force-recreate backend

# Frontend (React/TS) — hot-reloads via volume mount automatically.
# If Vite's module cache goes stale:
docker restart opama-frontend
```

An isolated second stack for testing (separate ports and database) is available
via `docker compose -f docker-compose.oss-test.yml up -d` — UI on 5174, API on
6001. Handy for testing against a clean instance without touching your data.

## Running tests

The test suite is black-box HTTP tests against a running API:

```bash
# Against the Docker stack:
API_BASE=http://localhost:6000 pytest

# Tests for authenticated endpoints need a bearer token and skip without one:
API_BASE=http://localhost:6000 API_TOKEN=<your token> pytest
```

Lint must pass the blocking gate used by CI:

```bash
ruff check app services tests alembic scripts celery_app.py --select E9,F,W --ignore F403,F405
```

Frontend type checks:

```bash
cd opama-ui && npx tsc --noEmit
```

## Making changes

- New to the codebase? Start with [ARCHITECTURE.md](ARCHITECTURE.md) for a code
  tour — directory layout, how a request flows, and how the plugin system works.
- Branch from `main`.
- Follow the conventions documented in [CLAUDE.md](CLAUDE.md) — dependency-injected
  DB sessions, static-before-dynamic routes, ownership checks, validated uploads.
- Commit messages: `feat|fix|chore|docs|test: short summary`.
- Building a new module/plugin? Start with
  [docs/MODULE_DEVELOPMENT.md](docs/MODULE_DEVELOPMENT.md).

## Pull requests

- Keep PRs focused — one change per PR.
- CI must be green (lint, migrations, tests, frontend typecheck + build).
- Describe what changed and why; include screenshots for UI changes.

## Reporting bugs / requesting features

Use the GitHub issue templates. For security vulnerabilities, **do not open a
public issue** — see [SECURITY.md](SECURITY.md).
