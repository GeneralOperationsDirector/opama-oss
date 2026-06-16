# Integrations (`services/integrations`)

External data integrations — currently the OpenClaw API, a generic
read/write surface over a user's assets, inventory, and portfolio for
external tools/agents.

- Plugin id: `integrations` (**core** tier), manifest: `plugin.yaml`
- Mounted at `/integrations/openclaw` (`router.py`)
- Models: none (`model_modules: []`) — reads/writes
  `services.shared.models.GenericAsset` and other core tables directly

## Endpoints

```
GET    /integrations/openclaw/assets
POST   /integrations/openclaw/assets
GET    /integrations/openclaw/assets/{asset_id}
DELETE /integrations/openclaw/assets/{asset_id}
GET    /integrations/openclaw/catalog/search
GET    /integrations/openclaw/inventory
POST   /integrations/openclaw/inventory
GET    /integrations/openclaw/portfolio
POST   /integrations/openclaw/describe
POST   /integrations/openclaw/identify
POST   /integrations/openclaw/listings/draft
POST   /integrations/openclaw/receipt
```

## Dependencies

- `services.shared.database.get_session`
- `services.shared.models.{User, GenericAsset}`

## Status

Core, in-tree. Not a repo-split candidate.
