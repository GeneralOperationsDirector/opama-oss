# opama Shopify (`opama_shopify`)

Publishes an opama storefront catalog to [Shopify](https://www.shopify.com/)
as products via the Admin REST API — a sibling publish target to the
GitHub/file/webhook flow in `opama_storefront`.

- Plugin id: `shopify` (premium tier), manifest: `plugin.yaml`
- Mounted at `/shopify` (`router.py`)
- Models: `ShopifySettings` (per-user shop domain + encrypted access token),
  `ShopifyProductMapping` (remembers which Shopify product a catalog entry
  maps to, so re-publishing updates rather than duplicates)

## Dependencies

Unlike `opama_marketplace` — the repo-split reference shape, which
deliberately imports nothing from `services.*`/`app.*` — `opama_shopify`
has a **hard dependency on the `opama_storefront` plugin**, a sibling
external plugin (`external_plugins/opama_storefront/`, pushed to its own
[`opama-oss-storefront`](https://github.com/GeneralOperationsDirector/opama-oss-storefront)
repo), not on opama core itself:

- `from opama_storefront.models import StorefrontSettings`
- `from opama_storefront.router import _generate_catalog` — a **private**
  helper (leading underscore) that builds the catalog entries this plugin
  syncs to Shopify

`plugin.yaml` declares this in `requires: [auth, storefront]`. This works at
runtime because `discover_plugins()` adds every `PLUGIN_PATHS` root
(including `external_plugins/`) to `sys.path` once — so
`opama_shopify.router` can `import opama_storefront.*` exactly like a normal
installed package, as long as both plugins are present in the host's
`PLUGIN_PATHS`. But because this plugin lives in a **separate repo**
(`opama-oss-shopify`) from `opama-oss-storefront`, there is no shared CI: if
`opama_storefront` renames or changes the signature of `_generate_catalog`
(or `StorefrontSettings`), this plugin breaks at the next restart with an
`ImportError`/`TypeError` and no warning beforehand. `opama_storefront`'s
`router.py` carries a comment at `_generate_catalog` flagging this cross-repo
consumer — keep that in mind (in either repo) when touching either side.

## Status

New module (not a relocation) added 2026-06-13 alongside the Pokémon TCG
extraction, and pushed to
[`opama-oss-shopify`](https://github.com/GeneralOperationsDirector/opama-oss-shopify)
(`main`, single-commit snapshot — no prior history). Loaded by the host
opama instance via `PLUGIN_PATHS` and the `opama_<id>` naming convention; see
the host repo's `external_plugins/README.md`.

`pyproject.toml` documents this package's shape as a standalone install
(`opama-shopify`) — not yet exercised by the host's loader, which uses
directory discovery rather than `pip install`.
