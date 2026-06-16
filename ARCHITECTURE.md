# Architecture

A code tour for contributors — where things live, how a request flows, and how
the plugin system fits together. For day-to-day conventions (DB sessions, route
ordering, ownership checks) see [CLAUDE.md](CLAUDE.md); for building a module
see [docs/MODULE_DEVELOPMENT.md](docs/MODULE_DEVELOPMENT.md).

## The shape of it

opama is a **modular monolith**: one FastAPI process, one React app, one
Postgres database. Features are organised as **plugins** (called modules in the
UI) that are discovered and mounted at startup rather than hard-wired. The
"micro-everything" appearance — separate routers, models, and frontend
features per domain — is organisational, not a distributed system. There is no
service mesh, message bus, or per-service database.

```
Browser ──HTTP──▶ FastAPI (app/main.py) ──▶ plugin routers (services/<id>/router.py)
   │                   │                              │
React app         auth middleware              SQLModel ──▶ Postgres
(opama-ui/)      (Firebase or local)        (services/shared/)
```

## Backend layout (`app/` + `services/`)

`app/` is the **platform** — the thin core that boots the application and
implements the cross-cutting machinery. Nothing domain-specific lives here:

| File | Responsibility |
|---|---|
| `main.py` | Builds the FastAPI app, middleware, CORS, static `/uploads`; mounts plugin routers; startup hooks |
| `plugin_loader.py` | Discovers `plugin.yaml` manifests, resolves which are enabled, imports their routers + models |
| `plugin_installer.py` | Runtime install of marketplace (`type=local`) plugins into a separate root |
| `plugin_signing.py` | Verifies signatures on downloaded plugin packages |
| `license.py` | RS256 license verification (public key here; the private signing key is **not** in the repo) |
| `secrets.py` | Symmetric encryption for secrets stored in the DB (e.g. the storefront GitHub token) |
| `network_validators.py` | SSRF guards — refuses non-public URLs for outbound calls |

`services/` holds the **domain plugins**. Each subdirectory is a self-contained
module, and (except for `shared/` and `auth/`) follows the same shape:

```
services/<id>/
├── plugin.yaml     # manifest: id, name, tier, api_prefix, router_module, model_modules, requires
├── router.py       # FastAPI APIRouter — the HTTP endpoints
├── models.py       # SQLModel tables owned by this module
└── schemas.py      # Pydantic request/response shapes
```

Two directories are special and always present:

- **`services/shared/`** — the database engine, `get_session`, and the
  SQLModel table definitions that multiple modules touch (User, etc.).
- **`services/auth/`** — token verification and the `get_current_user`
  dependency. It's registered before any plugin because every protected
  endpoint depends on it. Auth is **pluggable** (`services/auth/providers/`):
  `local` username/password (the self-hosted default) or `firebase`.

The domain modules: `catalog`, `inventory`, `decks`, `trading`, `ai`,
`portfolio`, `showcase`, `grading`, `custom_assets` (Collections — the
whitelabel core), `storefront`, `integrations`, `licensing`, `plugin_store`,
`system`. (A few features are frontend-only — e.g. the eBay `marketplace` view
under `opama-ui/src/features/` has no dedicated backend service.)

## How a request flows

1. The React app calls `api<T>()` (`opama-ui/src/lib/api.ts`), which attaches
   the auth token and hits the FastAPI server.
2. Middleware runs: CORS, gzip, security headers, rate limiting (slowapi).
3. The matching plugin router handles it. Protected routes depend on
   `get_current_user`; routes that mutate user data also call an
   `_assert_owner()` helper that 403s on cross-user access.
4. The handler uses an injected `Session` (`Depends(get_session)`) to talk to
   Postgres via SQLModel, then commits and returns.

## How plugins get mounted (`app/main.py`)

At startup the app:

1. Reads `ENABLED_PLUGINS` (empty = load all). `plugin_loader.discover_plugins`
   scans `services/*/plugin.yaml` and any `PLUGIN_PATHS` directories.
2. Always registers the auth router first.
3. For each enabled plugin, calls `app.include_router(loaded.router, prefix=manifest.api_prefix)`.
4. Mounts `/uploads` for user files.
5. On the startup event, initialises the DB and loads any **dynamic** plugins
   that were installed at runtime via `POST /plugin-store/install` (these
   become active after a restart).

This is why a module is "just" a directory with a `plugin.yaml` — there's no
central registry file to edit. The frontend mirrors this: `lib/moduleRegistry`
gates which modules render, and `OpamaApp.tsx` is the module router (see its
header comment for the `activeModule` / `tab` model).

### Three ways a plugin reaches the runtime

| Source | Loaded by | Lives in |
|---|---|---|
| In-tree / external dir | `plugin_loader` at startup | `services/` or a `PLUGIN_PATHS` dir |
| Marketplace `type=local` install | `plugin_installer` at runtime | `DYNAMIC_PLUGINS_ROOT` (named volume) |
| pip package | Python entry points | `pip-modules` (named volume) |

These are kept deliberately separate so the same package can't be registered
twice. See `app/plugin_installer.py` for the reasoning.

## Frontend layout (`opama-ui/src/`)

- `OpamaApp.tsx` — app shell and module router (header comment explains the
  routing model).
- `features/<name>/` — one folder per module, mirroring the backend domains
  (`custom-assets`, `storefront`, `grading`, `portfolio`, `decks`, …).
- `shared/` — reusable atoms (CardTile, ConfirmModal, HeaderBar, modals).
- `lib/` — `api.ts` (the HTTP client), `firebase.ts`, `images.ts`,
  `moduleRegistry`.
- `contexts/` — `AuthContext`, `LicenseContext`.

## External integrations

- **Storefront → static shop site:** `POST /storefront/publish` writes a
  `catalog.json` to GitHub (Cloudflare Pages auto-deploys); a Stripe webhook
  posts sales back to `/assets/website-listings/{slug}/sold`. Full flow in the
  Storefront section of CLAUDE.md.
- **LLM providers:** `external_plugins/opama_ai/providers/` abstracts OpenAI /
  Anthropic / Ollama behind one interface, selected by `AI_PROVIDER`.
- **Card identification:** Ollama vision models + Tesseract OCR
  (`external_plugins/opama_grading/identifier.py`).

## Data & files

- **Postgres** holds all structured data; schema changes go through Alembic
  (`alembic/versions/`). The backend runs `alembic upgrade head` on boot.
- **Uploaded files** live in `uploads/` (volume-mounted, gitignored), served
  read-only at `/uploads`. Filenames are always `{integer_id}.{ext}` — no
  user-controlled paths.

## Where to start reading

- Adding an endpoint to an existing module → that module's `router.py` +
  CLAUDE.md "Backend Conventions".
- Building a new module → [docs/MODULE_DEVELOPMENT.md](docs/MODULE_DEVELOPMENT.md).
- Understanding the grading math → `external_plugins/opama_grading/analyzer.py`
  (the pipeline is documented step-by-step in CLAUDE.md).
- Running it locally → [CONTRIBUTING.md](CONTRIBUTING.md) and
  [docs/DOCKER_GUIDE.md](docs/DOCKER_GUIDE.md).
