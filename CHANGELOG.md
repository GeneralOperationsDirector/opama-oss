# Changelog

All notable changes to opama are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed
- **BREAKING:** GitHub publishing moved out of Storefront into its own
  `github_publish` module. `/storefront/settings` no longer returns/accepts
  `github_token`, `github_repo`, `github_file_path`, or
  `github_commit_message`; `POST /storefront/settings/test-github` is
  removed. Configure GitHub publishing via the new
  `GET/PUT /integrations/github/settings` and `POST /integrations/github/test`
  endpoints. Existing settings are migrated automatically by the Alembic
  migration.

## [0.1.0] — 2026-06-15

First public release.

### Added
- Collections: template-based tracking for any asset class, front/back images
  with auto-thumbnails, lightbox viewer, per-category dashboard cards
- Portfolio: aggregated valuation, gain/loss, historical snapshots
- Storefront: listings management, one-click `catalog.json` publish to GitHub
  (Cloudflare Pages auto-deploy), Stripe sale write-back, sales dashboard
- Card grading: OpenCV pipeline (centering / corners / surface / edges),
  PSA-scale estimate, PNG report, AI-assisted card identification
- Pokémon TCG module: catalog, inventory, decks, wishlists, trade lists
- Plugin system: in-tree services, external plugin dirs (`PLUGIN_PATHS`),
  marketplace local installs, and pip-distributed modules, with a Plugin Store
  UI and a `registry.json`-driven module catalog
- Pluggable auth: local username/password (default, zero setup) or Firebase
- Pluggable LLM providers: OpenAI, Anthropic, or local Ollama
- Docker Compose stack with `opama.sh` / `opama.ps1` launcher and setup wizard
- `scripts/seed_demo.py` (`./opama.sh seed-demo`) to populate a sample collection

[Unreleased]: https://github.com/GeneralOperationsDirector/opama-oss/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/GeneralOperationsDirector/opama-oss/releases/tag/v0.1.0
