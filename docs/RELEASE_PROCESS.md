# Release Process & Versioning

This document defines opama's versioning policy, what counts as a breaking
change for module/plugin authors, and how core releases are cut. It's aimed
at anyone maintaining a module — whether built-in (`services/<id>/`),
external (`external_plugins/`, `PLUGIN_PATHS`), or one of the split
`opama-oss-*` repos (Pokémon TCG, Shopify, Storefront, Card Grader,
Portfolio, AI Assistant, Marketplace).

For how to build a module in the first place, see
[MODULE_DEVELOPMENT.md](MODULE_DEVELOPMENT.md).

---

## Versioning

[`app/version.py`](../app/version.py) defines `CORE_VERSION` — the single
source of truth for opama core's version. It's surfaced via:

- `GET /docs` / `GET /openapi.json` (`info.version`, set on the `FastAPI()`
  app in `app/main.py`)
- `GET /system/info` (`api_version`, `services/system/router.py`)
- `app.plugin_loader._core_compatible()` — compared against each plugin's
  `requires_core` (see below)

opama follows [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`.

**Pre-1.0 caveat:** while `CORE_VERSION` is `0.x.y`, a MINOR bump
(`0.1.0` → `0.2.0`) *may* include breaking changes, per standard SemVer
semantics for initial development. PATCH bumps (`0.1.0` → `0.1.1`) never are.

## What's a breaking change for module/plugin authors

A change to opama core is **breaking** if it can make an otherwise-correct
module stop loading or stop working without any change to the module's own
code. Concretely:

- **`plugin.yaml` schema changes** — a new *required* field, a renamed or
  removed field, or changed semantics for `type`, `requires`, or
  `model_modules`.
- **`PluginManifest` dataclass field changes** (`app/plugin_loader.py`) —
  removing or renaming a field that manifests/entry-point modules rely on.
- **`services/shared/models.py` table/column changes** that other plugins
  FK to or query directly (e.g. `Card.id`, `User.id` — see
  `external_plugins/opama_pokemon_tcg/README.md`'s "Module dependencies"
  table for what depends on what).
- **`services/shared/plugin_data.py` / `user_secrets.py` helper signature
  changes** — these are the zero-migration persistence APIs every module
  (including dynamic/pip installs) is told to build on.
- **`get_session` / `get_current_user` dependency signature or behavior
  changes** (`services/auth/middleware.py`, `services/shared/database.py`).
- **Plugin discovery/loading contract changes** — `router_module`
  resolution, `sys.path` injection order for `PLUGIN_PATHS` roots, or the
  timing of `model_modules` imports relative to `init_db()`.

## What's NOT breaking

- New *optional* `plugin.yaml` fields (like `requires_core` itself).
- New endpoints on existing routers.
- New built-in plugins/services.
- New optional parameters with defaults on existing helper functions.

## How breaking changes are communicated

- `CHANGELOG.md` entries for breaking changes go under `### Changed` or
  `### Removed`, prefixed `**BREAKING:**`, describing what a module author
  needs to do.
- `app/version.py`'s `CORE_VERSION`, the `CHANGELOG.md` heading for that
  release, and a git tag (`vX.Y.Z`) are bumped together — see "Release
  cadence" below.

## `requires_core`: declaring compatibility

A module's `plugin.yaml` may declare `requires_core`: a
[PEP 440](https://peps.python.org/pep-0440/) specifier set (parsed with the
`packaging` library), e.g.:

```yaml
requires_core: ">=0.1.0,<0.2.0"
```

At startup, `discover_plugins()` (`app/plugin_loader.py`) checks
`CORE_VERSION` against every manifest's `requires_core`. A manifest with no
`requires_core` (or an empty string) is always treated as compatible — this
keeps all manifests that predate this field working unchanged.

If `CORE_VERSION` does **not** satisfy `requires_core`, the plugin is logged
as skipped and excluded from discovery — it never reaches
`resolve_enabled()`, `/plugins`, or `load_plugin_models()`. One out-of-date
module is not allowed to take down the whole instance.

**Recommended pattern:** `>=<core version you developed against>,<next
minor>.0` — e.g. a module built against core `0.1.0` declares
`>=0.1.0,<0.2.0`. After verifying the module still works against a new core
`0.2.0` release, widen the upper bound to `<0.3.0` (or drop it if you're
confident in long-term compatibility).

[`scripts/new_module.py`](../scripts/new_module.py) pre-fills this field
with the recommended range for the core version you're scaffolding against.

## Release cadence

opama doesn't follow a calendar release schedule — it's tag-driven:

1. Changes accumulate under `[Unreleased]` in `CHANGELOG.md` as they land.
2. When `[Unreleased]` has enough user-facing changes to warrant a release,
   bump `CORE_VERSION` in `app/version.py`, move the `[Unreleased]` content
   into a new dated `[X.Y.Z] — YYYY-MM-DD` section, and add a fresh empty
   `[Unreleased]` section above it.
3. Tag the release: `git tag -a vX.Y.Z -m "opama X.Y.Z" && git push origin vX.Y.Z`.
4. For the 6 opama-branded modules (Pokémon TCG, Shopify, Storefront, Card
   Grader, Portfolio, AI Assistant), run `scripts/sync_oss_module.sh <module>`
   for any that changed, then review and push the resulting commit to each
   `opama-oss-*` mirror repo. See
   [`external_plugins/README.md`](../external_plugins/README.md#development-workflow-for-the-opama-branded-modules)
   for the workflow. This is a release-time step, not per-commit.
5. If new Pokémon TCG sets were synced (`POST /cards/sync/trigger`) since the
   last release, re-run `scripts/export_baseline_catalog.py` to refresh
   `external_plugins/opama_pokemon_tcg/catalog/data/baseline_catalog.ndjson.gz`
   so future installs seed with the current catalog. See
   [`external_plugins/opama_pokemon_tcg/README.md`](../external_plugins/opama_pokemon_tcg/README.md#baseline-catalog-dataset).
   Also release-time, not per-commit.

## Split-repo note

For each `opama-oss-*` external plugin repo (Pokémon TCG, Shopify,
Storefront, Card Grader, Portfolio, AI Assistant, Marketplace): after a core
release that's relevant to that plugin, verify it against the new core and
bump its `requires_core` upper bound accordingly.

This addresses the *core → plugin compatibility* direction of the "Version
pinning" item listed as deliberately deferred in
[`external_plugins/README.md`](../external_plugins/README.md#whats-still-open-before-an-actual-repo-extraction).
The other direction — how a host pins/upgrades a `PLUGIN_PATHS` plugin to a
specific *plugin* release — remains open.
