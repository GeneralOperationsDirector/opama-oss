# opama Pokémon TCG (`opama_pokemon_tcg`)

Pokémon TCG catalog, deck building, inventory tracking, and trading/wishlists
for [opama](https://github.com/GeneralOperationsDirector/opama-oss) — Open
Personal Asset Management.

This package ships **four separate plugins** that load into opama's plugin
system via `PLUGIN_PATHS` (see the host repo's `external_plugins/README.md`
and `docs/MODULE_DEVELOPMENT.md`):

| Plugin              | `id`        | `api_prefix` | Tier    | Manifest               |
|---------------------|-------------|--------------|---------|------------------------|
| Catalog             | `catalog`   | `/cards`     | premium | `catalog/plugin.yaml`  |
| Inventory           | `inventory` | `/inventory` | premium | `inventory/plugin.yaml`|
| Deck Builder        | `decks`     | `/decks`     | premium | `decks/plugin.yaml`    |
| Trading & Wishlists | `trading`   | (none)       | premium | `trading/plugin.yaml`  |

Each subpackage is independently toggleable via `ENABLED_PLUGINS` — but read
"Module dependencies" below before disabling `catalog`.

## Structure

```
opama_pokemon_tcg/
├── __init__.py
├── pyproject.toml             # standalone-package shape (see Status)
├── catalog/                    # foundational — owns Set, Card, CardFeatures
│   ├── plugin.yaml
│   ├── models.py                # Set, Card, CardFeatures, CatalogSyncLog, SetSyncStatus
│   ├── router.py                # GET /cards, /cards/sets, /cards/export*
│   ├── pokemon_tcg_client.py    # Pokémon TCG API client
│   ├── sync_service.py          # catalog sync logic
│   └── tasks.py                 # Celery tasks: check_and_sync_catalog, sync_single_set
├── inventory/
│   ├── plugin.yaml
│   ├── models.py                # InventoryItem
│   └── router.py                # GET/POST/PATCH/DELETE /inventory
├── decks/
│   ├── plugin.yaml
│   ├── models.py                # Deck, DeckCard
│   └── router.py                # GET/POST/PATCH/DELETE /decks
└── trading/
    ├── plugin.yaml
    ├── models.py                # WishList, TradeItem
    └── router.py                # wishlist/trade-list endpoints
```

## Module dependencies

`catalog` is the **foundational sub-module** — it owns the `Set` and `Card`
tables that everything else in this package builds on:

- `inventory.InventoryItem.card_id` → FK `card.id`
- `decks.DeckCard.card_id` → FK `card.id` (`deck_id` is a self-referential FK
  to `decks.Deck.id`, owned by the same plugin)
- `trading.WishList.card_id` / `trading.TradeItem.card_id` → logical
  references to `card.id` (not a schema-level FK, but unusable without it)

Each dependent plugin's `plugin.yaml` declares this via `requires`:

| Plugin      | `requires`                  |
|-------------|------------------------------|
| `catalog`   | `auth`                       |
| `inventory` | `auth`, `catalog`            |
| `decks`     | `auth`, `catalog`            |
| `trading`   | `auth`, `catalog`             |

`tests/test_plugin_manifests.py::TestKnownDataDependencies` enforces that
each of these `requires` entries stays declared — it's a regression guard
for exactly this table, not a substitute for it.

**If you disable `catalog`** (via `ENABLED_PLUGINS`), `inventory`, `decks`,
and `trading` will break — `load_plugin_models()` still registers every
plugin's tables (so Alembic/`create_all` always see the full schema), but
their FK columns reference a table whose owning plugin's router and sync
logic are no longer mounted. The plugin loader does not currently *enforce*
`requires` at the `ENABLED_PLUGINS` level (see `app/plugin_loader.py`) — in
practice, treat `catalog` as a hard prerequisite for the other three plugins
in this package.

**When changing `catalog/models.py`** (e.g. renaming or removing a `Card`
column), update `inventory`, `decks`, and `trading` — and their Alembic
migrations — in the same change. Because all four plugins ship together in
this package/repo, that's enforced the same way any other same-repo schema
change is: by the shared test suite and a single Alembic migration covering
the full schema. If any of these four plugins is ever split into its own
repo, the `requires` table above is the contract that must be preserved
(and versioned) across repos.

## Catalog sync

`catalog/sync_service.py` + `catalog/tasks.py` pull set/card data from the
Pokémon TCG API. `CatalogSyncLog` and `SetSyncStatus` track sync progress.
Celery tasks (`check_and_sync_catalog`, `sync_single_set`) are merged into
the host's `celery_app` via its plugin-discovery loop (`TASK_ROUTES` → queue
`catalog`).

## Baseline catalog dataset

`catalog/data/baseline_catalog.ndjson.gz` ships a metadata-only snapshot of
the Pokémon TCG catalog (169 sets / 19,500 cards as of 2026-06-14) — names,
numbers, sets/series, rarity, types, attacks/abilities text, legality, etc.
No card artwork is bundled: `image_small`/`image_large` are plain URL strings
pointing at the official Pokémon TCG API's image CDN (or `null`), never local
image files. This keeps the module copyright-safe — only structured game
data ships, never scanned/owned card images.

`catalog/seed.py`'s `seed_baseline_catalog()` loads this snapshot on first
startup, only if the `Set` table is empty (`app/main.py`'s startup handler,
gated on the `catalog` plugin being loaded). A fresh self-hosted install gets
the full card catalog immediately — no API key or sync step required before
using inventory/decks.

### Keeping it current

Pokémon TCG releases new sets continuously, so the bundled snapshot will go
stale. Two paths, for two audiences:

- **Self-hosters**: `POST /cards/sync/trigger` pulls new sets directly from
  the live Pokémon TCG API and only adds sets not already present — composes
  cleanly with the bundled baseline, no duplication.
- **Maintainers**: re-run `scripts/export_baseline_catalog.py` against an
  instance kept up to date via the above, to refresh
  `baseline_catalog.ndjson.gz` for *future* installs. Tie this to
  `CORE_VERSION` release points alongside `scripts/sync_oss_module.sh` (see
  `docs/RELEASE_PROCESS.md`) — not a per-commit step.

## Status

Extracted from `services/{catalog,inventory,decks,trading}/` into this
external-plugin package on 2026-06-13 and pushed to
[`opama-oss-pokemon`](https://github.com/GeneralOperationsDirector/opama-oss-pokemon)
(`main`, single-commit snapshot — no prior history). Loaded by the host
opama instance via `PLUGIN_PATHS` and the `opama_<id>` naming convention; see
the host repo's `external_plugins/README.md` for how discovery and
`sys.path` injection work.

Development happens here, in the `opama` monorepo — the mirror repo is
kept in sync via `scripts/sync_oss_module.sh pokemon_tcg` (see
`external_plugins/README.md`).

`pyproject.toml` documents this package's shape as a standalone install
(`opama-pokemon-tcg`, pip-installable with `fastapi`/`sqlmodel`/`celery`/
`requests`) — not yet exercised by the host's loader, which uses directory
discovery rather than `pip install` (see "What's still open" in the host's
`external_plugins/README.md`).
