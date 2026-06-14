# opama Portfolio (`opama_portfolio`)

Portfolio valuation, historical snapshots, sale-transaction tracking, and
P&L analysis over a user's Pokémon TCG inventory.

- Plugin id: `portfolio` (premium tier), manifest: `plugin.yaml`
- Mounted at `/portfolio` (`router.py`)
- Models (`models.py`): `MarketPrice`, `SaleTransaction`, `PortfolioSnapshot`,
  `UserPortfolioSettings`
- `valuation.py` — valuation/breakdown calculations

## Endpoints

```
GET    /portfolio/value              # current portfolio value
GET    /portfolio/{user_id}/breakdown
GET    /portfolio/history            # snapshot history
POST   /portfolio/snapshot           # record a snapshot
PUT    /portfolio/prices             # upsert MarketPrice rows
GET    /portfolio/prices/{card_id}
GET    /portfolio/sales
POST   /portfolio/sales
DELETE /portfolio/sales/{sale_id}
GET    /portfolio/sales/summary
```

## Dependencies

Like `opama_grading` and `opama_storefront`, this plugin imports from core
(`services.*`) and from the sibling `opama_pokemon_tcg` external plugin — it
is **not** a zero-dependency relocation like `opama_marketplace`:

- `services.shared.database.get_session`, `services.shared.models.User`
- `services.auth.middleware.get_optional_user`
- **Hard imports** `opama_pokemon_tcg.catalog.models.{Card, Set}` and
  `opama_pokemon_tcg.inventory.models.InventoryItem` (in both `router.py` and
  `valuation.py`) — valuation is computed directly from Pokémon TCG inventory
  + market prices. `plugin.yaml` declares `requires: [auth, inventory, catalog]`
  (`inventory` and `catalog` both being `opama_pokemon_tcg` sub-plugins).

This works at runtime because `discover_plugins()` adds every `PLUGIN_PATHS`
root (including `external_plugins/`) to `sys.path` once, so
`opama_pokemon_tcg.*` imports resolve like any other installed package. If
`opama_pokemon_tcg` isn't on `PLUGIN_PATHS`, `opama_portfolio.router` fails to
import; `load_plugins()` logs and skips it (see
`external_plugins/opama_ai/README.md` for the same pattern). As a separate
repo with no shared CI, a
`opama_pokemon_tcg.catalog`/`inventory` schema change would break this plugin
at the next restart with no warning beforehand.

## Status

Relocated from `services/portfolio/` (full history preserved via `git mv`) on
2026-06-14, following the same pattern as the Pokémon TCG, Shopify,
Storefront, and Card Grader extractions. Pushed as a single-commit snapshot to
`git@github.com:GeneralOperationsDirector/opama-oss-portfolio.git` `main`.

`pyproject.toml` documents this package's shape as a standalone install
(`opama-portfolio`) — not yet exercised by the host's loader, which uses
directory discovery rather than `pip install`.
