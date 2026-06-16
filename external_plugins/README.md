# external_plugins/ — plugins that live outside this repo

This directory holds plugin code that physically lives outside `services/`,
loaded at runtime via the `PLUGIN_PATHS` mechanism in `app/plugin_loader.py`.
It exists as **prep work for the "repo split"** described in the open-source
vision: opama-branded modules each live in their own GitHub repo while still
loading into the core opama backend at runtime. Pokémon TCG, Shopify,
Storefront, Card Grader, Portfolio, and AI Assistant have already made this
move — see `opama_pokemon_tcg/`, `opama_shopify/`, `opama_storefront/`,
`opama_grading/`, `opama_portfolio/`, and `opama_ai/` below.

Each of these 6 directories is also mirrored to its own GitHub repo under
`github.com/GeneralOperationsDirector/`:

| Directory | Mirror repo |
|---|---|
| `opama_pokemon_tcg/` | `opama-oss-pokemon` |
| `opama_shopify/` | `opama-oss-shopify` |
| `opama_storefront/` | `opama-oss-storefront` |
| `opama_grading/` | `opama-oss-card-grader` |
| `opama_portfolio/` | `opama-oss-portfolio` |
| `opama_ai/` | `opama-oss-ai-assistant` |

`opama_marketplace/` (see below) was the original same-repo `git mv`
proof-of-concept and has since moved on to become a real standalone premium
plugin in its own private repo (no longer present in this tree; its shape is
kept below for illustration).

## How discovery works (`PLUGIN_PATHS`)

`PLUGIN_PATHS` is a comma-separated list of directories — parsed the same way
`ENABLED_PLUGINS` is. Each entry is a **plugin root** that mirrors `services/`:
its immediate subdirectories are plugin packages, each containing a
`plugin.yaml` directly inside (the exact `services/<id>/plugin.yaml`
convention, just rooted elsewhere).

`discover_plugins()` globs `SERVICES_DIR/*/plugin.yaml` (unchanged) **plus**
`<plugin_root>/*/plugin.yaml` for every `PLUGIN_PATHS` entry. Before importing
any external manifest's code, the loader adds that plugin root (the *parent*
of the package directory — e.g. `external_plugins/`, not
`external_plugins/opama_marketplace/`) to `sys.path` exactly once, so
`importlib.import_module("opama_marketplace.router")` resolves like any other
installed package. `load_plugins()` / `load_plugin_models()` need no special
handling — they already just call `importlib.import_module(dotted_path)`.

In the dev Docker stack, `PLUGIN_PATHS` defaults to `/app/external_plugins`
(see `docker-compose.yml` and `.env.example`).

## The `opama_<id>` package-naming convention

External plugin packages are named `opama_<id>` — the underscore form (PEP 8)
of the eventual repo name `opama-<id>`. So the `marketplace` plugin's package
is `opama_marketplace`, matching what a `github.com/<owner>/opama-marketplace`
repo would ship. `router_module` and `model_modules` in `plugin.yaml` reference this
dotted package path (e.g. `opama_marketplace.router`), exactly like in-repo
plugins reference `services.<id>.router`.

## Development workflow for the opama-branded modules

The 6 modules listed above are first-party "opama branded" modules — unlike
`opama_marketplace` (an arms-length premium plugin in its own private repo),
they ship as part of every opama installation. Their mirror repos
(`opama-oss-*`, table above) do **not** make them independently-developed:

- **Development happens here**, in this monorepo's `external_plugins/opama_<id>/`
  — same hot-reload bind-mount as any other plugin (`docker-compose.yml`'s
  `PLUGIN_PATHS` default).
- The `opama-oss-*` mirror repos exist for focused issue tracking / external
  visibility into a single module, and as the source the public core repo
  (`opama-oss-prelaunch`) bundles from — `opama-oss-prelaunch` ships
  `external_plugins/<module>/` directly, the same way this repo does.
- Mirrors are kept up to date with `scripts/sync_oss_module.sh <id>`, run by
  a maintainer at release points (see `docs/RELEASE_PROCESS.md`), not on
  every commit. The script never force-pushes or rewrites history — it stages
  an additive "sync" commit in a local clone and prints the review/push step.

## Reference example: `opama_marketplace/` (moved)

`marketplace` (eBay search & price discovery) was chosen as the proof-of-concept
relocation because it's the lowest-blast-radius real plugin in the codebase.
**It has since moved on to its own private repo** —
`external_plugins/opama_marketplace/` is gitignored and no longer part of
this tree — but its shape is kept below as the illustrative reference:

- `model_modules: []` — no DB tables, zero Alembic involvement
- No cross-plugin imports — not even `services.shared` or `services.auth`
- Nothing in any manifest declares `requires: [marketplace]`

Its shape:

```
external_plugins/opama_marketplace/
├── __init__.py
├── plugin.yaml          # router_module: opama_marketplace.router
├── pyproject.toml       # documents the eventual standalone-package shape
├── config.py
├── router.py
└── ebay/
    ├── __init__.py
    ├── client.py
    └── schemas.py
```

Nothing inside the package imports from `services.*` or `app.*` — only
relative imports (`from ..config import settings`) and third-party deps
(`fastapi`, `pydantic`, `requests`), which is what makes a plugin safe to
relocate outside the monorepo without code changes.

## Dynamic local installs — the marketplace `type: local` distribution channel

The "Distribution channel" question below is now answered for one important
case: plugins a self-hoster adds *later*, at runtime, through the Plugin
Store (`POST /plugin-store/install`). For a manifest declaring `type: local`,
`app/plugin_installer.py` downloads the vendor's package archive, safely
extracts it, and `load_dynamic_plugins()` (in `app/plugin_loader.py`) imports
it on the next restart — all without the package ever living in this repo or
in `PLUGIN_PATHS`.

`PLUGIN_PATHS`/`external_plugins/` remains the mechanism for plugins that
*ship with* an opama installation (the "repo split" scenario this directory
preps for). Dynamic local installs are deliberately kept on a wholly separate
loading path — DB-driven (`dynamic_plugins` table), rooted at
`DYNAMIC_PLUGINS_ROOT` (default `/app/dynamic_plugins`), and **never** added
to `PLUGIN_PATHS`. Mixing the two would make `discover_plugins()`'s
`<root>/*/plugin.yaml` glob find the same package `load_dynamic_plugins()`
already loads from its DB row, double-registering it (two routers mounted,
undefined behaviour).

### The archive contract a vendor must meet

A `type: local` marketplace manifest additionally declares:

```yaml
id: my_plugin
type: local
tier: premium                       # core | free | premium | enterprise
version: 1.2.0
download_url: https://cdn.example.com/my_plugin-1.2.0.tar.gz
router_module: my_plugin.router     # dotted path, imported via importlib
# router_attr: router               # optional — "router" is the only value
                                    # supported in v1; simplest just to omit it
model_modules: []                   # MUST be empty — see "Why no DB models" below
```

`download_url` is fetched with `Authorization: Bearer <download-token>` (see
"Download tokens" below) and must resolve to a **tar or zip archive**
(detected by sniffing content — `tarfile.is_tarfile`/`zipfile.is_zipfile` —
never by trusting the URL's file extension) whose root — after stripping at
most one common wrapper directory (the GitHub-tarball `reponame-<sha>/`
convention) — contains:

- `plugin.yaml`, re-parsed and re-validated post-download: its `id` **must**
  match the `plugin_id` opama originally requested, or the install is
  refused. This stops a malicious or compromised archive from masquerading as
  a different (or higher-trust) plugin than the one a user thinks they're
  installing.
- the importable Python package itself (e.g. `my_plugin/__init__.py`,
  `my_plugin/router.py`)
- an `APIRouter` instance accessible as `<router_module>.router`

Extraction runs under hard caps — see `MAX_DOWNLOAD_BYTES` /
`MAX_EXTRACTED_BYTES` / `MAX_MEMBERS` in `app/plugin_installer.py` for current
values — and rejects any archive member that's a symlink, hardlink, or device
file outright; every extracted file's permission bits are reset to
`rw-r--r--` regardless of what the archive claims (no legitimate plugin needs
setuid/setgid/sticky bits or executable permissions on its source files).

### Why no DB models (`model_modules: []`)

Unlike static `PLUGIN_PATHS` plugins, a dynamically-installed local plugin
**cannot** declare `model_modules` — enforced with a 422 at install time.
Two independent reasons (documented in full in `app/plugin_installer.py`'s
module docstring and as a TODO beside `load_plugin_models()` in
`app/plugin_loader.py`):

1. **Import ordering** — `load_plugin_models()` runs at module-import time,
   before `init_db()`/`create_all()` and before the FastAPI app object
   exists, so SQLModel can see the tables. `load_dynamic_plugins()` runs a
   full lifecycle phase later, inside `@app.on_event("startup")`, against an
   already-initialized engine — too late for `create_all()` to pick up new
   tables, and entangling plugin discovery with DB bootstrap in a way this
   codebase deliberately keeps separate.
2. **Migration-on-install** — even if ordering were solved, `create_all()`
   only creates tables that don't already exist; production Postgres schemas
   are Alembic-managed (see the `migration_practices` notes). Running
   arbitrary third-party DDL against an instance's database at install time
   is a wholly separate security problem.

Exactly the same "lowest blast radius" reasoning made `marketplace` (also
zero DB tables — see above) the static `PLUGIN_PATHS` proof-of-concept.

**This restriction is about new tables, not persistence in general.** A
dynamically-installed (or pip entry-point) plugin can still store settings,
secrets, and per-entity extension fields via `services/shared/plugin_data.py`
and `services/shared/user_secrets.py` — these wrap the `plugin_data` and
`user_secret` core tables, which exist on every opama instance regardless of
`ENABLED_PLUGINS` or `model_modules`. See
[`docs/MODULE_DEVELOPMENT.md` §4(A)](../docs/MODULE_DEVELOPMENT.md#4-settings--secrets)
for the pattern.

### Download tokens

Requests to `download_url` carry `Authorization: Bearer <token>` — a
short-lived (15-minute) RS256 JWT signed with this instance's keypair,
verifiable with the very same `GET /plugin-store/public-key` endpoint vendors
already use to verify `X-Opama-Plugin-Token` proxy requests (see
`app/plugin_signing.py`'s module docstring for the full picture). The claim
shape is a sibling of the proxy token's — same `iss`/`instance_id`/`iat`/`exp`
envelope — but **`tier` takes the place of `user_id`**:

```json
{
  "iss": "opama",
  "instance_id": "<uuid>",
  "plugin_id": "<plugin-id>",
  "tier": "premium",
  "iat": <unix-ts>,
  "exp": <unix-ts + 900>
}
```

A vendor can verify the signature against the published public key and gate
the download by `tier`. opama itself already checked the same entitlement
(`LicenseInfo.allows_plugin`) before minting the token and refuses with `403`
otherwise — a vendor-side check is defense-in-depth, not the only gate.
`instance_id` + `tier` is deliberately **all** the token discloses; no
licensee identity (`LicenseInfo.customer`) is ever sent to a third-party
vendor on every install.

### Lifecycle: install → restart → uninstall / update

Exactly like remote-plugin installs, a local install only takes effect after
a restart (`status: installed_restart_required`/`updated_restart_required`).
Uninstalling deletes only the DB row — never the on-disk package immediately,
because its module may still be imported and its router still mounted in the
running process. A garbage-collection sweep (`_gc_orphaned_local_installs`,
run once at the next startup, right after the load loop) removes any
`DYNAMIC_PLUGINS_ROOT` directory no longer referenced by an *enabled* row —
the single mechanism that cleans up both uninstalled plugins and orphaned
previous versions left behind by an update. Installs are version-suffixed
(`<plugin_id>-<version>/`), so an update's download lands alongside the
currently-running version rather than overwriting it; the GC sweep reclaims
the old directory once it's no longer referenced.

## What's still open before an actual repo extraction

This prep proves the *loader* can load a plugin from outside `services/`.
For the 6 opama-branded modules, two of the three original open questions are
now resolved by the "Development workflow" section above:

- **Distribution channel for plugins that ship *with* an installation** —
  **resolved** for these 6: they ship as part of `external_plugins/` in both
  this repo and `opama-oss-prelaunch`, kept in sync via
  `scripts/sync_oss_module.sh`. git submodule / `pip install` from a private
  index remain open only for a self-hoster who wants to *replace* one of
  these 6 with their own fork — not needed for the bundled-by-default case.
  (The *runtime* add-a-plugin-later channel is separately answered — see
  "Dynamic local installs" above.)
- **CI** — **resolved as "not needed for mirrors"**: the `opama-oss-*` repos
  are synced snapshots with no independent code path, so CI continues to run
  only in this monorepo. If a mirror repo ever starts accepting its own PRs
  (truly independent development), it gets its own CI at that point.

Still open:

- **Version pinning** — how a host pins/upgrades an external (`PLUGIN_PATHS`)
  plugin to a specific version once it's not just a subdirectory of this repo.
  (Dynamic local installs sidestep this — they're DB-versioned and
  GC-managed; see above.) The *other* direction — a plugin declaring which
  opama core versions it's compatible with — is now answered by
  `requires_core` in `plugin.yaml`; see
  [docs/RELEASE_PROCESS.md](../docs/RELEASE_PROCESS.md). Pinning a plugin to
  one of its own releases remains open and is independent of the
  branded-module sync workflow above.
