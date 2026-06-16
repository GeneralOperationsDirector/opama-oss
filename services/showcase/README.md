# Card Showcases (`services/showcase`)

Curated public and private showcases of Pokémon TCG cards — a user picks
cards from their catalog/inventory into a named, shareable collection.

- Plugin id: `showcase` (premium tier), manifest: `plugin.yaml`
- Mounted at `/showcases` (`router.py`)
- Models (`models.py`): `Showcase`, `ShowcaseCard`

## Endpoints

```
GET    /showcases                              # list (auth user)
POST   /showcases                              # create
GET    /showcases/{showcase_id}                # get (own or public)
PATCH  /showcases/{showcase_id}                # rename / toggle public
DELETE /showcases/{showcase_id}
GET    /showcases/public/{user_id}             # public showcases for a user
POST   /showcases/{showcase_id}/cards          # add a card
PATCH  /showcases/{showcase_id}/cards/{card_item_id}
DELETE /showcases/{showcase_id}/cards/{card_item_id}
```

## Dependencies

- `services.shared.database.get_session`, `services.shared.models.User`
- `services.auth.middleware.{get_current_user, get_optional_user}`
- **Hard import** `opama_pokemon_tcg.catalog.models.Card` — showcase entries
  reference catalog cards. `plugin.yaml` declares `requires: [auth, catalog]`
  (`catalog` being the `opama_pokemon_tcg` sub-plugin).

If `opama_pokemon_tcg` isn't on `PLUGIN_PATHS`, `services.showcase.router`
fails to import; `load_plugins()` logs and skips it (see
`external_plugins/opama_ai/README.md` for the same pattern).

## Status

Still in `services/`. Not yet relocated — tightly coupled to
`opama_pokemon_tcg.catalog`, so a future repo-split would likely ship this
alongside it.
