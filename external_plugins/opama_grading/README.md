# opama Card Grader (`opama_grading`)

AI-powered card grading: an uploaded scan is perspective-corrected with
OpenCV, scored on centering/corners/surface/edges, identified via Ollama
vision models (full-image, then region-crop) and Tesseract OCR, and rendered
as a PNG report. Results can be transferred into an inventory item or a
custom-asset collection entry.

- Plugin id: `grading` (premium tier), manifest: `plugin.yaml`
- Mounted at `/grading` (`router.py`)
- Models: `CardGradeResult`, `IdentificationAttempt`, `GradeFeedback`
- Pipeline: `analyzer.py` (rectify/centering/corners/surface/edges),
  `identifier.py` (Ollama + Tesseract fusion), `report.py` (Pillow PNG report)

## Dependencies

Like `opama_storefront`, this plugin imports from core (`services.*`) and
from the sibling `opama_pokemon_tcg` external plugin — it is **not** a
zero-dependency relocation like `opama_marketplace`:

- `services.custom_assets.models.CustomAsset` — `/grading/{id}/transfer` can
  save a result as a new collection item, and `CardGradeResult.asset_id` has
  a real DB foreign key to `customasset.id` (kept, since `custom_assets` is
  core and always present)
- `services.shared.database.get_session`, `services.shared.models.User`
- `services.auth.middleware.get_current_user`
- `opama_pokemon_tcg.catalog.models.Card` — **hard import** in `router.py`,
  used for catalog search/lookup during identification and for
  `/grading/{id}/transfer` into Pokémon inventory. Unlike `CardGradeResult`'s
  `card_id`/`inventory_item_id` fields (deliberately soft references, no DB
  FK — see `models.py`), this is a real Python-level dependency: if
  `opama_pokemon_tcg` isn't installed, `opama_grading.router` fails to import
  and the plugin won't load. `requires: [auth, custom_assets, catalog]`
  in `plugin.yaml` reflects this (`catalog` is the `opama_pokemon_tcg`
  sub-plugin that provides `Card`).

This works at runtime because `discover_plugins()` adds every `PLUGIN_PATHS`
root (including `external_plugins/`) to `sys.path` once, so both
`opama_pokemon_tcg.*` and `services.*`/`opama_storefront`-style imports
resolve like any other installed package. As a separate repo with no shared
CI, a core-side rename of `CustomAsset` or a `opama_pokemon_tcg.catalog`
schema change would break this plugin at the next restart with no warning
beforehand.

`services/system/router.py`'s `/system/info` endpoint counts each user's
grading results for the status panel; it imports `CardGradeResult` inside a
`try/except ImportError` (mirroring how it already handles optional
`opama_pokemon_tcg` models) so core-only deployments without this plugin
still start cleanly.

## Status

Relocated from `services/grading/` (full history preserved via `git mv`) on
2026-06-13, following the same pattern as the Pokémon TCG, Shopify, and
Storefront extractions. Pushed as a single-commit snapshot to
`git@github.com:GeneralOperationsDirector/opama-oss-card-grader.git` `main`.

`pyproject.toml` documents this package's shape as a standalone install
(`opama-grading`) — not yet exercised by the host's loader, which uses
directory discovery rather than `pip install`.
