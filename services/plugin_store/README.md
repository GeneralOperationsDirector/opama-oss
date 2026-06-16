# Plugin Store (`services/plugin_store`)

The community plugin marketplace: browse the catalog, enable/disable
built-in modules, install remote/local plugins at runtime, and manage
pip-distributed plugins.

- Plugin id: `plugin_store` (**core** tier), manifest: `plugin.yaml`
- Mounted at `/plugin-store` (`router.py`)
- Models (`models.py`): `DynamicPlugin` — DB row per runtime-installed
  (`type: local`/`remote`) plugin, consumed by
  `app/plugin_loader.py`'s `load_dynamic_plugins()`

## Endpoints

```
GET    /plugin-store/marketplace          # catalog (registry.json-backed)
GET    /plugin-store/installed            # installed dynamic plugins
GET    /plugin-store/active-plugins       # { active, pending } — actually-loaded plugin IDs
GET    /plugin-store/public-key           # RS256 public key (plugin signing / download tokens)
POST   /plugin-store/install              # install a type=local/remote plugin (admin)
DELETE /plugin-store/{plugin_id}          # uninstall (admin)
POST   /plugin-store/enable/{module_id}   # enable a built-in module (writes enabled_overrides.json)
DELETE /plugin-store/enable/{module_id}   # disable a built-in module
POST   /plugin-store/restart              # restart the backend container (admin)
GET    /plugin-store/pip-modules          # list pip entry-point plugins
POST   /plugin-store/pip-install          # pip install a module (admin)
DELETE /plugin-store/pip-modules/{package}
```

## Dependencies

- `services.shared.database.get_session`, `services.shared.models.User`
- `services.shared.audit.write_audit_log`
- `services.auth.middleware.{get_current_user, require_admin}`
- `app.network_validators.assert_public_url` — SSRF guard on marketplace/
  download URLs
- `app.plugin_installer` / `app.plugin_signing` / `app.plugin_loader` — the
  runtime install, signature-verification, and dynamic-load machinery this
  router drives
- `app.license.LicenseInfo.allows_plugin` — entitlement check before minting
  a download token

## Status

Core, in-tree. Not a repo-split candidate — this module *is* part of the
platform's plugin infrastructure (`app/`).
