# System Panel (`services/system`)

Diagnostics, health info, and per-user storage/data stats for the in-app
status panel, plus the admin-only audit log viewer.

- Plugin id: `system` (**core** tier), manifest: `plugin.yaml`
- Mounted at `/system` (`router.py`)
- Models: none (`model_modules: []`)

## Endpoints

```
GET /system/info    # uptime, api/python version, uploads size, per-user data counts
GET /system/audit   # admin-only: paginated AuditLog (plugin installs, secret/settings
                     # changes, publishes, ...)
```

## Dependencies

- `services.shared.database.get_session`, `services.shared.models.User`
- `services.shared.models_security.AuditLog`
- `services.auth.middleware.{get_current_user, require_admin}`
- `services.custom_assets.models.CustomAsset` — counts collection items

### Optional cross-plugin imports (the reference pattern)

`/system/info` reports per-user counts for inventory, decks, and grading
results — all owned by **optional external plugins**. This router is the
reference example for guarding such imports so core-only deployments (e.g.
the OSS test stack, no `PLUGIN_PATHS`) still start cleanly:

```python
try:
    from opama_pokemon_tcg.inventory.models import InventoryItem
    from opama_pokemon_tcg.decks.models import Deck
except ImportError:
    InventoryItem = None
    Deck = None

try:
    from opama_grading.models import CardGradeResult
except ImportError:
    CardGradeResult = None
```

Each count is skipped (returns `0`) when the corresponding model is `None`.

## Status

Core, in-tree. Not a repo-split candidate.
