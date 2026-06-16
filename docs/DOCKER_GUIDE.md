# Docker Guide

How opama runs under Docker Compose, and how to operate it day to day.

> **Just want to get started?** Use the launcher: `./opama.sh setup` then
> `./opama.sh start` (Windows: `.\opama.ps1`). It wraps everything on this
> page. This guide is for people who want to understand or operate the stack
> directly with `docker compose`.

## Table of Contents

- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Configuration](#configuration)
- [Common Commands](#common-commands)
- [Database Operations](#database-operations)
- [Plugin Volumes](#plugin-volumes)
- [Troubleshooting](#troubleshooting)
- [Production Notes](#production-notes)

---

## Architecture

One compose file (`docker-compose.yml`) starts four services:

```
┌──────────────────────────────────────────────────────────────┐
│  frontend (node:22-alpine, Vite dev server)    → :5173       │
│      proxies /api → backend                                  │
│  backend  (FastAPI + uvicorn)                  → :6000→8000  │
│      runs `alembic upgrade head` on boot                     │
│  postgres (postgres:16-alpine)                 → :5433→5432  │
│  redis    (redis:7-alpine)                      (internal)   │
└──────────────────────────────────────────────────────────────┘
```

| Service | Container | Host port | Notes |
|---|---|---|---|
| backend | `opama-backend` | **6000** | FastAPI; API docs at `/docs` |
| frontend | `opama-frontend` | **5173** | Vite dev server, hot-reloads from `opama-ui/` mount |
| postgres | `opama-postgres` | **5433** | Data in the `postgres_data` named volume |
| redis | `opama-redis` | — | Not exposed to the host |

Source code (`app/`, `services/`, `opama-ui/`) is volume-mounted, so backend
and frontend changes take effect without rebuilding the image. The backend
applies Alembic migrations automatically on every start.

There is also `docker-compose.oss-test.yml`, an isolated second stack
(UI 5174, API 6001, Postgres 5435) for testing changes against a clean
database — see [CONTRIBUTING.md](../CONTRIBUTING.md).

---

## Prerequisites

- **Docker** 20.10+ with **Compose v2** (`docker compose version`).
  Docker Desktop or [OrbStack](https://orbstack.dev) (Mac) both work.
- Nothing else — Python, Node, and Postgres all run inside containers.

Optional, for AI features:

- **Ollama** on the host ([ollama.ai](https://ollama.ai)) — local chat and
  card-identification vision models. The backend reaches it via
  `host.docker.internal:11434`.
- **OpenAI or Anthropic API key** — hosted LLM provider for `/ai/chat` and
  suggestions (`AI_PROVIDER` selects which).

---

## Configuration

Two env files at the repo root (both gitignored, both written by
`./opama.sh setup`):

- **`.env`** — read by Compose itself for interpolation. Must define
  `POSTGRES_PASSWORD` (the postgres service refuses to start without it).
- **`.env.local`** — injected into the backend container via `env_file`.
  Holds `DATABASE_URL`, auth provider settings, API keys, etc.

Key variables (see the [README](../README.md) for the full table):

```env
# .env
POSTGRES_PASSWORD=<strong-random-password>

# .env.local
DATABASE_URL=postgresql://opama:<password>@postgres:5432/opama
AUTH_PROVIDER=local            # or firebase
LOCAL_AUTH_SECRET=<generated>
AI_PROVIDER=openai             # openai | anthropic | ollama
OPENAI_API_KEY=...
CORS_ORIGINS=http://localhost:5173
```

Compose-level knobs (set in `.env` or the shell):

| Variable | Default | Purpose |
|---|---|---|
| `ENABLED_PLUGINS` | *(all)* | Comma-separated backend plugin IDs to load |
| `VITE_ENABLED_MODULES` | *(all)* | Comma-separated frontend module IDs |
| `PLUGIN_PATHS` | `/app/external_plugins` | Directories of external plugin packages |
| `OPAMA_LICENSE_KEY` | *(empty)* | Empty = dev mode, all modules enabled |

---

## Common Commands

```bash
# Start / stop
docker compose up -d                  # start everything
docker compose down                   # stop
docker compose down -v                # stop + wipe volumes (⚠️ deletes the database)

# After backend (Python) changes — image rebuild required for dependency changes,
# but plain code edits only need a restart since source is volume-mounted:
docker compose up -d --no-deps --force-recreate backend

# Frontend hot-reloads automatically. If Vite's module cache goes stale
# ("export not found" errors after a pull):
docker restart opama-frontend

# Logs
docker compose logs -f                # all services
docker compose logs -f backend       # one service
docker compose logs --tail=100 backend

# Status / health
docker compose ps                     # all containers + health
curl http://localhost:6000/healthz    # backend health probe
```

---

## Database Operations

The launcher provides `./opama.sh backup` and `./opama.sh restore`
(timestamped SQL dumps in `./backups/`). Manually:

```bash
# psql shell
docker exec -it opama-postgres psql -U opama_user -d opama_dev

# Backup
docker exec opama-postgres pg_dump -U opama_user opama_dev > backup_$(date +%Y%m%d).sql

# Restore
cat backup_20260612.sql | docker exec -i opama-postgres psql -U opama_user -d opama_dev

# Migrations run automatically on backend start; to run them manually:
docker exec opama-backend alembic upgrade head
docker exec opama-backend alembic current
```

(`opama_user`/`opama_dev` are what `./opama.sh setup` writes to `.env`; if you
configured different `POSTGRES_USER`/`POSTGRES_DB` values, substitute them.)

---

## Plugin Volumes

Three separate locations hold module/plugin code — deliberately kept apart so
packages are never double-registered:

| Location | What lives there | Persistence |
|---|---|---|
| `./external_plugins/` (bind mount) | Plugins you develop or drop in manually; each subdir has its own `plugin.yaml` | On disk in the repo |
| `dynamic_plugins_data` (named volume) | `type=local` marketplace installs, downloaded at runtime | Survives recreates; wiped by `down -v` |
| `pip_modules_data` (named volume) | pip-distributed module packages from `requirements-modules.txt`, installed on container boot | Survives recreates; wiped by `down -v` |

See [MODULE_DEVELOPMENT.md](MODULE_DEVELOPMENT.md) for how these are loaded.

---

## Troubleshooting

### A container won't start

```bash
docker compose logs backend
```

Usual suspects: missing `POSTGRES_PASSWORD` in `.env`, missing `.env.local`
(run `./opama.sh setup`), or a port conflict.

### Port already in use

Ports 5173, 6000, or 5433 taken by something else:

```bash
sudo lsof -i :6000          # find the process
```

Either stop the conflicting process or edit the host-side port in
`docker-compose.yml` (the left number in `"6000:8000"`).

### Frontend can't reach the backend

The Vite dev server proxies API calls to `http://backend:8000` inside the
compose network (`VITE_API_TARGET`). Check that the backend is healthy:

```bash
docker compose ps backend
curl http://localhost:6000/healthz
```

### Database connection errors on boot

Postgres has a health check and the backend waits for it, but a corrupted
volume or changed password can still break the connection:

```bash
docker exec opama-postgres pg_isready -U opama
# Last resort — destroys data:
docker compose down -v && docker compose up -d
```

### Backend can't reach Ollama

Ollama runs on the host; the container reaches it through the
`host.docker.internal` mapping. Verify `OLLAMA_URL=http://host.docker.internal:11434`
in `.env.local` and that `ollama serve` is running on the host.

### Hot-reload not picking up changes

Backend code is mounted from `./app` and `./services`; uvicorn does **not**
run with `--reload`, so restart it after edits:

```bash
docker compose up -d --no-deps --force-recreate backend
```

---

## Production Notes

The compose file is tuned for local/self-hosted use. Before exposing an
instance beyond localhost:

1. **Strong secrets** — `POSTGRES_PASSWORD`, `LOCAL_AUTH_SECRET`, and a real
   password on your local account (the UI prompts when it detects exposure).
2. **TLS** — terminate HTTPS at a reverse proxy (Caddy, Traefik, nginx) in
   front of ports 5173/6000; don't expose them directly.
3. **CORS + URLs** — set `CORS_ORIGINS` to your real origin and
   `PUBLIC_API_URL` to the public API base (needed for storefront image URLs).
4. **Don't expose Postgres** — remove the `5433:5432` port mapping if nothing
   on the host needs it.
5. **Back up** — `./opama.sh backup` on a cron, plus the `uploads/` directory.

See [SECURITY_CHECKLIST.md](SECURITY_CHECKLIST.md) for the full checklist.
