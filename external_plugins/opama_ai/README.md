# opama AI Assistant (`opama_ai`)

Deck-building suggestions and a RAG-backed chat assistant. Two independent
sub-routers are combined into one plugin entry point (`router.py`):
`suggest_router.py` (mounted at `/suggest`) and `chat_router.py`
(self-prefixed at `/ai`).

- Plugin id: `ai` (premium tier), manifest: `plugin.yaml`
- Models: none (`model_modules: []`) — reads existing Pokémon TCG tables
- `providers/` — pluggable LLM backends (OpenAI / Anthropic / Ollama),
  selected via `AI_PROVIDER`; `factory.get_provider()`
- `rag/` — retrieval pipeline: `retrieval.py` (Chromadb + FlagEmbedding),
  `rerank.py`, `cache.py` (Redis-backed JSON cache), `rag.py` (`_deck_context`,
  `build_query`, `retrieve_cards`, `compress_with_ollama`)
- `suggest/scoring.py` — heuristic card-suggestion scoring

## Endpoints

```
GET  /suggest/{deck_id}            # heuristic card suggestions for a deck
POST /suggest/ai                   # LLM-backed suggestions
POST /suggest/build_from_inventory # build a deck from owned inventory
POST /ai/chat                      # RAG deck chat
```

## Dependencies

Like `opama_grading` and `opama_portfolio`, this plugin imports from core
(`services.*`) and from the sibling `opama_pokemon_tcg` external plugin — it
is **not** a zero-dependency relocation like `opama_marketplace`. It has the
**heaviest cross-plugin dependency** in opama — it hard imports Pokémon TCG
models at module level:

- `opama_pokemon_tcg.decks.models.{Deck, DeckCard}`
- `opama_pokemon_tcg.catalog.models.{Card, CardFeatures, Set}`
- `opama_pokemon_tcg.inventory.models.InventoryItem`
- `services.shared.database.get_session`

`plugin.yaml` declares `requires: [auth, decks, catalog, inventory]` —
`catalog` and `inventory` are listed directly (not just transitively via
`decks`) because `suggest_router.py` and `rag/rag.py` hard-import them too,
mirroring why `opama_grading` and `opama_portfolio` list `catalog` directly.
If `opama_pokemon_tcg` isn't on `PLUGIN_PATHS`, `opama_ai.suggest_router`
fails to import — `app/plugin_loader.py`'s `load_plugins()` catches this,
logs `⚠️ Skipping plugin 'ai': ...`, and the rest of the app starts normally
(the OSS test stack, which has no `opama_pokemon_tcg`, exercises this path).

This works at runtime because `discover_plugins()` adds every `PLUGIN_PATHS`
root (including `external_plugins/`) to `sys.path` once, so
`opama_pokemon_tcg.*` imports resolve like any other installed package. As a
separate repo with no shared CI, a `opama_pokemon_tcg.{catalog,decks,inventory}`
schema change would break this plugin at the next restart with no warning
beforehand.

## Status

Relocated from `services/ai/` (full history preserved via `git mv`) on
2026-06-14, following the same pattern as the Pokémon TCG, Shopify,
Storefront, Card Grader, and Portfolio extractions. Pushed as a
single-commit snapshot to
`git@github.com:GeneralOperationsDirector/opama-oss-ai-assistant.git`
`main`.

Development happens here, in the `opama` monorepo — the mirror repo is
kept in sync via `scripts/sync_oss_module.sh ai` (see
`external_plugins/README.md`).

`pyproject.toml` documents this package's shape as a standalone install
(`opama-ai`) — not yet exercised by the host's loader, which uses directory
discovery rather than `pip install`.
