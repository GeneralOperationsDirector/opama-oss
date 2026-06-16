# Shared (`services/shared`)

Cross-cutting library every plugin imports from — the database engine,
core SQLModel table definitions, and small generic-persistence helpers that
let plugins store data without their own migrations.

- **Not a plugin** — no `plugin.yaml`, nothing to load/enable/disable. Always
  present; imported directly by core and external plugins alike.

## Contents

- **`database.py`** — `engine`, `get_session` (FastAPI dependency, injected
  via `Depends`), `init_db()`, `get_backend()` (`"postgres"` vs
  `"firestore_local"`), `ensure_indexes()`.
- **`models.py`** — `User`, `LocalCredential` (local-auth password hash),
  `GenericAsset` (used by `services/integrations`).
- **`models_security.py`** — `UserSecret` (encrypted per-user secrets, see
  `user_secrets.py`), `AuditLog` (append-only privileged-action trail, see
  `audit.py` and `services/system`'s `/system/audit`).
- **`models_plugin_data.py`** — `PluginData`, a single generic
  `(plugin_id, entity_type, entity_id)` JSON-blob table.
- **`plugin_data.py`** — typed helpers over `PluginData`:
  `get_plugin_data`/`set_plugin_data`/`clear_plugin_data` (per-entity),
  `get_user_plugin_data`/`set_user_plugin_data` (per-user, `entity_id=0`),
  `get_instance_plugin_data`/`set_instance_plugin_data` (instance-wide,
  `entity_id=0`).
- **`user_secrets.py`** — typed helpers over `UserSecret`:
  `get_user_secret`/`set_user_secret`/`delete_user_secret`/
  `user_secret_status` (returns `(is_set, hint)` — never the secret itself).
- **`audit.py`** — `write_audit_log(...)`, called from auth, custom_assets,
  plugin_store, storefront, etc.
- **`rate_limit.py`** — `rate_limit(limit_string)` slowapi helper.

## Why this exists for the plugin system

`PluginData`/`UserSecret` are the mechanism by which **dynamically-installed
(`type: local`) or pip entry-point plugins** — which cannot declare
`model_modules` (no new tables at install time, see
`external_plugins/README.md`) — still persist settings, secrets, and
per-entity extension fields. These two tables exist on every opama instance
regardless of `ENABLED_PLUGINS`. See
[`docs/MODULE_DEVELOPMENT.md` §4(A)](../../docs/MODULE_DEVELOPMENT.md#4-settings--secrets).

## Status

Core, in-tree. Not a repo-split candidate — every plugin (in-tree or
external) depends on this package being importable as `services.shared.*`.
