# Collections / Custom Assets (`services/custom_assets`)

Manage any type of personal asset or collectible — the whitelabel core of
opama. Every "Collection" the user creates (watches, guitars, wine,
sneakers, art, …) is a `CustomAsset` row; this is the module that made opama
generic beyond Pokémon TCG.

- Plugin id: `custom_assets` (**core** tier, always available), manifest:
  `plugin.yaml`
- Mounted at `/assets` (`router.py`)
- Models (`models.py`): `CustomAsset`, `CustomAssetField` (per-item custom
  key/value fields, separate table)

## Endpoints

```
GET    /assets                              # list (auth user, ?category=, ?q=)
GET    /assets/summary                      # portfolio totals + per-category breakdown
GET    /assets/categories                   # distinct categories
POST   /assets                              # create item
GET    /assets/{asset_id}                   # get item
PATCH  /assets/{asset_id}                   # update item
DELETE /assets/{asset_id}                   # delete item (also removes uploaded images)
POST   /assets/{asset_id}/image             # upload front image + auto-thumbnail
POST   /assets/{asset_id}/back-image        # upload back image + auto-thumbnail
GET    /assets/website-listings             # storefront export (X-Export-Key)
POST   /assets/website-listings/{website_slug}/sold  # record sale (X-Export-Key)
```

## Dependencies

- `services.shared.database.get_session`, `services.shared.models.User`
- `services.auth.middleware.get_current_user`
- `Pillow` for thumbnail generation (`_make_thumbnail()`)

### Cross-repo consumers — this is the most depended-on core module

Several **external plugins** import directly from this module, so renaming or
changing the shape of `CustomAsset`/`CustomAssetField` or the helpers below
breaks them at the next restart with no warning beforehand:

- `opama_storefront` (separate repo `opama-oss-storefront`) —
  `CustomAsset`/`CustomAssetField` (listings are assets with
  `listed_on_website=true`), and the **private** helper `_category_slug()`
  (normalizes free-text categories to catalog slugs). `_category_slug` carries
  a breadcrumb comment flagging this consumer.
- `opama_grading` (`external_plugins/opama_grading/`) — `CustomAsset`, for
  `/grading/{id}/transfer` into a collection; `CardGradeResult.asset_id` keeps
  a real DB foreign key to `customasset.id`.
- `services/system/router.py` — counts the current user's `CustomAsset` rows
  for `/system/info`.

## Status

Core, in-tree, always loaded (`tier: core`). Not a repo-split candidate — this
module is part of opama's open-source core.
