# Building a Module for opama

opama is a modular monolith: every feature — Collections, Storefront,
Portfolio, Card Grader, the Pokémon TCG suite, eBay Marketplace — is a
**module** with the same shape: a `plugin.yaml` manifest, a FastAPI
`APIRouter`, and (optionally) its own SQLModel tables and settings.

This guide is for anyone — human or AI agent — building a new module:
a third-party service integration (Stripe, Shopify, Anthropic, Ollama, …),
a new asset-class feature, or a community plugin for the marketplace.

For the high-level architecture and conventions of the existing codebase,
see [CLAUDE.md](../CLAUDE.md). For end-user documentation, see
[USERGUIDE.md](../USERGUIDE.md).

---

## 1. The four ways code becomes a module

| Channel | Code lives | Can declare new DB tables? | Install mechanism |
|---|---|---|---|
| **Built-in service** | `services/<id>/` in this repo | ✅ yes | Ships with opama; enabled via `ENABLED_PLUGINS` or the Modules UI |
| **External plugin** (`PLUGIN_PATHS`) | A separate directory mirroring `services/`, mounted into the container | ✅ yes | Operator sets `PLUGIN_PATHS` env var; mechanism for "ships with opama but lives in its own repo" |
| **Dynamic local install** (Plugin Store) | Downloaded archive under `DYNAMIC_PLUGINS_ROOT` | ❌ no — `model_modules` must be `[]`, but see below | `POST /plugin-store/install` (marketplace `type: local`); restart required |
| **Pip entry-point module** | Installed into `/app/pip-modules` via pip | ❌ no — same restriction, but see below | `POST /plugin-store/pip-install`; package declares `opama.modules` entry point |
| **Remote plugin** | Vendor's own server | n/a (no code runs in-process) | opama reverse-proxies; manifest sets `type: remote` |

**Rule of thumb:** if your module needs **its own relational tables** —
typed columns, FK joins, high write volume — it must be a **built-in
service** or an **external plugin**; both load before the database is
initialized, so SQLModel can register their tables. Modules installed later
at runtime (dynamic local / pip) cannot add tables this way.

That said, **every module — including dynamic/pip installs — can persist
settings, secrets, and per-entity extension fields** via the
`plugin_data` / `user_secrets` helpers (§4(A)): `plugin_data` and
`user_secret` are core tables that exist regardless of `ENABLED_PLUGINS`,
with zero migration required from your module. Reach for a dedicated table
(§4(B)) only once you outgrow that — and at that point you also need a
built-in service or external plugin to host it.

This is why service-provider modules (Stripe, Cloudflare, Firebase, an LLM
provider, …) should start life as built-in services under `services/` —
even if the long-term plan is to split them into their own repo and load
them via `PLUGIN_PATHS` (which has the same DB capability).

### Listing a module in the marketplace (`registry.json`)

The Plugin Store's browse list comes from **`registry.json`** at the repo root.
At runtime the backend merges two copies: the one shipped in the image
(`MARKETPLACE_REGISTRY_FILE`, default `/app/registry.json`) and a remote one
fetched from `MARKETPLACE_REGISTRY_URL` (the same file served via raw GitHub).
The shipped copy wins on `id` clash, so the remote registry can only *add* new
community modules, never silently override a built-in entry.

To list a module, add one object to the array:

```json
{
  "id": "my_module",
  "name": "My Module",
  "description": "One sentence shown in the store card.",
  "version": "1.0.0",
  "tier": "free",
  "type": "remote",
  "icon": "🧩",
  "author": "you",
  "repo": "https://github.com/<owner>/opama-my-module",
  "manifest_url": "https://raw.githubusercontent.com/<owner>/opama-my-module/main/plugin.yaml",
  "category": "Tools",
  "tags": ["example"],
  "enable_plugins": ""
}
```

- `type: builtin` → the code already ships in opama; clicking *Enable* adds the
  service IDs in `enable_plugins` to the active set (keep that list in sync with
  `BUILTIN_MODULE_SERVICE_IDS` in `app/plugin_loader.py`).
- `type: remote`/`local` → `manifest_url` points at the module's `plugin.yaml`;
  installing it goes through the signed-package flow (see §1 and the security
  notes below). Leave `enable_plugins` empty.

To get a module added to the official store, open a PR that appends your entry
to `registry.json`.

---

## 2. `plugin.yaml` manifest reference

Every module has a `plugin.yaml` at its root (`services/<id>/plugin.yaml` for
built-in modules).

```yaml
id: my_module                  # unique plugin id — used in ENABLED_PLUGINS,
                                # requires:, BUILTIN_MODULE_SERVICE_IDS, etc.
name: My Module                # display name (Modules UI)
version: 1.0.0
tier: premium                  # core | free | premium | enterprise
type: local                    # local (in-process) | remote (proxied)
description: One-line description shown in the Modules UI.
icon: "🔌"                      # emoji shown in the Modules UI
api_prefix: ""                 # prepended to all routes, e.g. "/my-module"
tags: [my-module]

# --- type: local fields ---
router_module: services.my_module.router   # dotted path, must expose `router`
router_attr: router            # default "router" — rarely overridden
model_modules:                 # SQLModel table modules to import before
  - services.my_module.models  # init_db() — see table above for restrictions
requires:                       # other plugin ids this module depends on
  - auth
requires_core: ">=0.1.0,<0.2.0" # optional — opama core versions this module
                                # is compatible with (PEP 440 specifier)

# --- type: remote fields (mutually exclusive with the above) ---
# remote_url: https://my-vendor.example.com
# auth_type: signed_jwt        # none | signed_jwt
# scopes: [read:inventory]
```

`requires:` is documentation/dependency-ordering metadata — `services/auth`
and `services/shared` (auth middleware, DB session, base models) are implicit
dependencies of almost everything.

`requires_core` is optional; if omitted, the module is treated as compatible
with every core version. If set and the running core's
[`CORE_VERSION`](../app/version.py) doesn't satisfy it, the module is logged
and excluded at discovery rather than crashing startup. See
[RELEASE_PROCESS.md](RELEASE_PROCESS.md) for the versioning policy, what
counts as a breaking change, and the recommended `requires_core` range.

---

## 3. Anatomy of a module

```
services/my_module/
├── plugin.yaml
├── __init__.py
├── router.py          # FastAPI APIRouter — the only required export
├── models.py           # SQLModel table(s), if any
└── schemas.py          # Pydantic request/response models
```

### `router.py` skeleton

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from services.shared.database import get_session
from services.auth.middleware import get_current_user
from services.shared.models import User
from .models import MyModuleSettings
from .schemas import MyModuleSettingsOut, MyModuleSettingsIn

router = APIRouter(prefix="/my-module", tags=["my-module"])


@router.get("/settings", response_model=MyModuleSettingsOut)
def get_settings(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    row = session.exec(
        select(MyModuleSettings).where(MyModuleSettings.user_id == current_user.id)
    ).first()
    if not row:
        raise HTTPException(404, "Not configured yet")
    return row
```

Conventions to follow (all enforced elsewhere in the codebase — see
[CLAUDE.md](../CLAUDE.md) "Backend Conventions"):

- **Always** inject `session` via `Depends(get_session)` — never
  `Session(engine)` directly.
- **Always** require `current_user` via `Depends(get_current_user)` for
  anything touching user data.
- **Ownership checks** — if a resource has a `user_id`, verify
  `resource.user_id == current_user.id` and raise `403` otherwise (see
  `_assert_owner()` in `services/custom_assets/router.py` for the pattern).
- **Static routes before dynamic routes** — `/my-module/summary` must be
  declared before `/my-module/{id}`.
- **Commit/refresh after writes** — `session.add(x); session.commit();
  session.refresh(x)`.

---

## 4. Settings & secrets

There's no single "settings framework" — pick the pattern that fits:

### A. Generic plugin data + secrets — start here

`services/shared/plugin_data.py` and `services/shared/user_secrets.py` wrap
two core tables — `plugin_data` (a JSON blob per `(plugin_id, entity_type,
entity_id)`) and `user_secret` (a per-`(user_id, service)` encrypted vault) —
that exist on **every** opama instance, regardless of `ENABLED_PLUGINS` or
which channel (§1) your module uses. No new table, no new migration.

```python
from fastapi import APIRouter, Depends
from sqlmodel import Session

from services.shared.database import get_session
from services.auth.middleware import get_current_user
from services.shared.models import User
from services.shared.plugin_data import get_user_plugin_data, set_user_plugin_data
from services.shared.user_secrets import get_user_secret, set_user_secret, user_secret_status
from .schemas import MyModuleSettingsIn

router = APIRouter(prefix="/my-module", tags=["my-module"])

PLUGIN_ID = "my_module"


@router.get("/settings")
def get_settings(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    data = get_user_plugin_data(session, PLUGIN_ID, current_user.id)
    api_key_set, api_key_hint = user_secret_status(session, current_user.id, f"{PLUGIN_ID}_api_key")
    return {
        "base_url": data.get("base_url", ""),
        "api_key_set": api_key_set,
        "api_key_hint": api_key_hint,
    }


@router.put("/settings")
def update_settings(
    body: MyModuleSettingsIn,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    set_user_plugin_data(session, PLUGIN_ID, current_user.id, base_url=body.base_url)
    if body.api_key:  # empty/omitted = keep the existing secret
        set_user_secret(session, current_user.id, f"{PLUGIN_ID}_api_key", body.api_key)
    return get_settings(session=session, current_user=current_user)
```

Notes:

- `set_user_plugin_data()` does a read-modify-write **merge** — it won't
  clobber keys you don't pass. Passing a key with value `None` deletes it.
- Never put secrets in `plugin_data` — use `user_secrets` for those.
  `user_secret_status()` returns `(is_set, hint)` without decrypting, which
  is exactly the `*_set`/`*_hint` response shape used throughout the
  codebase (e.g. `StorefrontSettingsOut.github_token_set` /
  `github_token_hint`).
- `("instance", 0)` is also a valid scope (`get_instance_plugin_data` /
  `set_instance_plugin_data`) for instance-wide config editable via the
  Modules UI — see (C) below for when to prefer that over env vars.
- `(<table_name>, row.id)` is a valid scope for attaching extension fields
  to another module's rows (e.g. `("customasset", asset.id)`) without a
  schema-level FK or column addition.
- This is a low-write-volume settings mechanism. If you need SQL-level
  filtering/joins on individual fields or expect frequent writes, use (B)
  instead.

### B. Dedicated settings table

For modules with genuinely relational needs — many fields, typed columns,
joins, or high write volume — define your own SQLModel table, the same way
`StorefrontSettings` (`external_plugins/opama_storefront/models.py`) does:

```python
class MyModuleSettings(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, unique=True)

    api_key: Optional[str] = None       # encrypted at rest — see below
    base_url: str = Field(default="")
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
```

This requires `model_modules` (built-in service or external plugin only —
see §1) and an Alembic migration for existing databases.

**Encrypting secrets in your own table** — use `app/secrets.py` directly
(or skip this and use `user_secrets`, §A, even from a dedicated-table
module):

```python
from app.secrets import encrypt_secret, decrypt_secret_safe, secret_hint

# On save:
row.api_key = encrypt_secret(plaintext_key)

# On use:
plaintext = decrypt_secret_safe(row.api_key)

# In the response schema, never return the secret — return a hint:
api_key_set = bool(row.api_key)
api_key_hint = secret_hint(decrypt_secret_safe(row.api_key)) if row.api_key else None
```

This is exactly the pattern `external_plugins/opama_storefront/router.py` uses for
`github_token`. Submitting an empty value on update should **preserve** the
existing secret (`null`/empty in the request = "keep current").

### C. Instance-wide env-var config (for service-account-style credentials)

For credentials that are the same for every user of this opama instance
(e.g. a shared Ollama URL, a shared OAuth app), use a Pydantic settings
object reading from env vars — see `external_plugins/opama_marketplace/config.py`
(`EbaySettings`) for the pattern. No DB table, no migration, but requires a
redeploy/restart to change.

If the config needs to be editable from the Modules UI without a redeploy,
use `plugin_data`'s `("instance", 0)` scope instead (§A) —
`get_instance_plugin_data` / `set_instance_plugin_data`.

### D. Don't invent a third pattern

If you're tempted to store config in `custom_fields` or another module's
table, stop — that conflates concerns and makes the module harder to split
out later. (A) is the sanctioned outlet for exactly that impulse: a
zero-migration place to put a settings blob. Use (A), (B), or (C).

---

## 5. Worked example: a minimal "Hello" module

> **Shortcut:** `python3 scripts/new_module.py hello --name "Hello Module"`
> generates exactly the files below (plugin.yaml, `__init__.py`, router.py,
> models.py), including a `requires_core` range computed from the current
> [`CORE_VERSION`](../app/version.py). The steps that follow are what it
> generates, spelled out.

1. **Create the directory and manifest:**

```bash
mkdir -p services/hello
```

`services/hello/plugin.yaml`:
```yaml
id: hello
name: Hello Module
version: 0.1.0
tier: free
type: local
description: Example module — says hello.
icon: "👋"
api_prefix: ""
tags: [example]
router_module: services.hello.router
model_modules: []
requires:
  - auth
```

2. **`services/hello/__init__.py`** — empty file.

3. **`services/hello/router.py`:**
```python
from fastapi import APIRouter, Depends
from sqlmodel import Session

from services.shared.database import get_session
from services.auth.middleware import get_current_user
from services.shared.models import User
from services.shared.plugin_data import get_user_plugin_data, set_user_plugin_data

router = APIRouter(prefix="/hello", tags=["hello"])


@router.get("")
def say_hello(current_user: User = Depends(get_current_user)):
    return {"message": f"Hello, {current_user.display_name or current_user.email}!"}


@router.get("/settings")
def get_settings(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    data = get_user_plugin_data(session, "hello", current_user.id)
    return {"greeting": data.get("greeting", "Hello")}


@router.put("/settings")
def update_settings(
    body: dict,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return {"greeting": set_user_plugin_data(session, "hello", current_user.id, **body).get("greeting", "Hello")}
```

This module persists a per-user setting with **zero new tables or
migrations** — `get_user_plugin_data`/`set_user_plugin_data` read and write
the core `plugin_data` table. See §4(A) for the full pattern, including
secrets.

4. **Restart the backend:**
```bash
docker compose up -d --no-deps --force-recreate backend
```

`discover_plugins()` picks up `services/hello/plugin.yaml` automatically;
`GET /hello` and `GET/PUT /hello/settings` are now live (auth required).

If `model_modules` were non-empty, the same restart is sufficient for a
**built-in** module — `load_plugin_models()` runs at import time, before
`init_db()`, so new tables are created by `SQLModel.metadata.create_all()`
on first boot. For an existing database, you'd still need an Alembic
migration (see `CLAUDE.md` → Migration Practices).

---

## 6. Testing locally

Use the isolated OSS test stack (`docker-compose.oss-test.yml`) — separate
ports (5174/6001/5435) and a separate Postgres volume, so you don't risk the
main dev database:

```bash
docker compose -f docker-compose.oss-test.yml up -d --build
```

- UI: http://localhost:5174
- API: http://localhost:6001/docs
- Local auth is enabled by default — log in as the seeded admin account.

After backend changes:
```bash
docker compose -f docker-compose.oss-test.yml up -d --no-deps --force-recreate backend
```

---

## 7. Where to go next

- **Reference implementations** — `external_plugins/opama_storefront/`
  (settings + secrets + external publishing), `external_plugins/opama_marketplace/`
  (zero-DB external plugin, env-var config).
- **Plugin loader internals** — `app/plugin_loader.py` (manifest schema,
  discovery, dynamic loading) and `app/plugin_installer.py` (install
  security model for marketplace `type: local`).
- **External plugin / repo-split mechanics** — `external_plugins/README.md`.
- **Adding a remote (hosted) plugin** — see `auth_type: signed_jwt` and
  `app/plugin_signing.py` for how opama signs requests on a vendor's behalf.
- **Adding an AI provider** — `external_plugins/opama_ai/providers/base.py` defines the
  `LLMProvider` interface (`chat()` + `chat_json()`) used by `/ai/chat`,
  `/suggest/chat`, and `/suggest/ai`. `openai_provider.py`,
  `anthropic_provider.py`, and `ollama_provider.py` are worked examples;
  `factory.py` (`get_provider()`) resolves the active provider from the
  `AI_PROVIDER` env var. A new provider (Gemini, Grok, IBM Watson, ...) is one
  adapter module plus one branch in `factory.py` — no router changes needed.
