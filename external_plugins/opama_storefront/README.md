# opama Storefront (`opama_storefront`)

Manages items a user lists for sale on an external static shop site:
shop settings (including a GitHub token, stored encrypted), listing/sales
views, and the publish flow (`catalog.json` → GitHub Contents API →
filesystem path → webhook, first success wins).

- Plugin id: `storefront` (premium tier), manifest: `plugin.yaml`
- Mounted at `/storefront` (`router.py`)
- Models: `StorefrontSettings` — one row per user (shop identity, publish
  targets, encrypted GitHub token)

## Dependencies

Unlike `opama_marketplace` — the repo-split reference shape, which
deliberately imports nothing from `services.*`/`app.*` — `opama_storefront`
has a **heavier core-dependency footprint** than `opama_shopify` or
`opama_pokemon_tcg`, since it's the module that owns the storefront catalog
itself:

- `services.custom_assets.models.{CustomAsset, CustomAssetField}` — listings
  are assets with `listed_on_website=true`
- `services.custom_assets.router._category_slug()` — normalizes free-text
  categories into catalog slugs; a **private** helper imported cross-repo.
  `services/custom_assets/router.py` carries a comment at `_category_slug`
  flagging this consumer — keep that in mind (in either repo) when touching
  either side.
- `services.shared.database.get_session`, `services.shared.models.User`,
  `services.shared.audit.write_audit_log`
- `services.auth.middleware.get_current_user`
- `app.secrets` (`encrypt_secret`/`decrypt_secret_safe`/`secret_hint`) — the
  GitHub token is stored encrypted and never returned, only a hint
- `app.network_validators.assert_public_url` — guards the webhook/file-path
  publish targets against SSRF

This works at runtime because `discover_plugins()` adds every `PLUGIN_PATHS`
root (including `external_plugins/`) to `sys.path` once, so
`opama_storefront.router` can `import services.*`/`app.*` exactly like a
core service's own router. As with `opama_shopify`/`opama_pokemon_tcg`, this
plugin now lives in a **separate repo** (`opama-oss-storefront`) with no
shared CI — if opama core renames or changes any of the above, this plugin
breaks at the next restart with an `ImportError`/`TypeError` and no warning
beforehand.

### Plugin-to-plugin: `opama_shopify`

`opama_shopify` (also an external plugin) depends on **this** plugin:

- `from opama_storefront.models import StorefrontSettings`
- `from opama_storefront.router import _generate_catalog` — a **private**
  helper that builds the catalog entries Shopify syncs. `router.py` carries
  a comment at `_generate_catalog` flagging this cross-repo consumer — keep
  its signature/return shape stable, or update `opama_shopify` in lockstep.

## Status

Relocated from `services/storefront/` (full history preserved via `git mv`)
on 2026-06-13, following the same pattern as the Pokémon TCG and Shopify
extractions, and pushed to
[`opama-oss-storefront`](https://github.com/GeneralOperationsDirector/opama-oss-storefront)
(`main`, single-commit snapshot — no prior history). Loaded by the host
opama instance via `PLUGIN_PATHS` and the `opama_<id>` naming convention; see
the host repo's `external_plugins/README.md`.

Development happens here, in the `opama` monorepo — the mirror repo is
kept in sync via `scripts/sync_oss_module.sh storefront` (see
`external_plugins/README.md`).

`pyproject.toml` documents this package's shape as a standalone install
(`opama-storefront`) — not yet exercised by the host's loader, which uses
directory discovery rather than `pip install`.
