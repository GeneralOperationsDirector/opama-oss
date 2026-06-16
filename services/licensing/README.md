# License (`services/licensing`)

A thin read-only endpoint reporting this instance's license status — tier,
entitled modules, customer, and expiry.

- Plugin id: `licensing` (**core** tier), manifest: `plugin.yaml`
- Mounted at `/license` (`router.py`)
- Models: none

## Endpoints

```
GET /license   # LicenseStatus: { valid, tier, modules, customer, expires_at, message }
```

## Dependencies

- `app.license.get_license()` — RS256 license verification. The public key
  lives in `app/license.py`; the private signing key is **not** in this repo.
  `LicenseInfo.allows_plugin` (used elsewhere, e.g. `plugin_store`'s download
  token minting) is part of the same module.

This router is intentionally minimal — it's a read-only status surface over
`app/license.py`'s verification logic, which the rest of the app (notably
`plugin_store`) calls directly.

## Status

Core, in-tree. Not a repo-split candidate — license verification is core
platform logic.
