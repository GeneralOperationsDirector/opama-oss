# Opama Glossary — the project vocabulary

A small, consistent vocabulary is what makes a codebase feel both **branded** and
**simple** (think WordPress: "themes", "plugins", "hooks" — a handful of words,
used everywhere). opama has historically used several words for the same idea;
this page is the single source of truth for the terms we use **in docs, UI
strings, and new code**.

> This is a **lexicon, not a rename**. Existing directory and symbol names
> (`services/`, `external_plugins/`, `custom_assets`, …) stay as-is — renaming
> them would add churn, not remove it. The win is talking about things one way.
> When you write a UI label, a doc, a comment, or a new symbol, reach for the
> word in the left column below.

---

## The core terms

### Opama Core
The domain-agnostic **base engine**: the app shell and module loader, auth +
**Organizations**, shared models/DB, RLS, storage, the marketplace/loader. Core
knows nothing about Pokémon, real estate, or any specific asset class — it's a
general personal-asset-management engine that other things are built on.

Lives in: `app/`, `services/shared/`, `services/auth/`, the plugin loader.

### Opama Module
A **unit of functionality** mounted on Core — portfolio, grading, storefront,
inventory, the Pokémon TCG catalog, etc. This is the one word for the thing the
code variously calls *service*, *plugin*, and *feature*.

- Built-in modules live in `services/<name>/`; optional/premium ones in
  `external_plugins/opama_<name>/`; their UI in `opama-ui/src/features/<name>/`.
  Those locations are implementation detail — **the word is "module".**
- Every module declares a **tier** (`core | free | premium | enterprise`) in its
  `plugin.yaml` / manifest.

### Opama Edition
A **curated, domain-specific solution built on Core**: a chosen set of Modules +
collection templates + branding/theme, tailored for one audience. This is the
"customized solution" layer of the product.

- **Opama Pokémon Edition** — the flagship: collectors, traders, and card-shop
  owners (the `pokemon_tcg`, `grading`, `storefront`, `portfolio` modules + TCG
  templates).
- The plain general-PAM build is effectively the **base edition**.
- (We say **Edition**, not "vertical" or "build" — keep it consistent.)

### Collection
The user-facing name for a **set of tracked items** of any asset class. This is
what users see and what docs/UI say.

- Internal code names stay: model `CustomAsset`, package `custom_assets`, routes
  under `/assets`, frontend `features/custom-assets/`. Don't rename them — but in
  **UI text and docs, it's a "Collection".**

### Organization (Org)
The **tenancy + billing + data-ownership boundary**. A solo user is an
"org-of-one"; a shop is an Org with staff Memberships. Entitlements (plan/tier)
live on the Org. (Already consistent across the code — recorded here for
completeness.)

---

## Quick mapping (legacy term → Opama term)

| You see / might write | Use instead |
|---|---|
| service, plugin, feature (a unit of functionality) | **Module** |
| vertical, build, flavor (a domain solution) | **Edition** |
| custom asset, item, holding (in UI/docs) | **Collection** (item *within* a Collection) |
| tenant, account (the ownership boundary) | **Organization / Org** |
| the engine, the platform, the framework | **Opama Core** |

---

## How to use this

- **New code / symbols:** prefer the Opama term when naming a new concept. Don't
  rename existing ones just to match — link this glossary in the PR instead.
- **UI strings & docs:** always the Opama term ("Collection", "Module",
  "Pokémon Edition").
- **Don't invent synonyms.** If a concept isn't here and you need a word for it,
  add it here first so it stays a vocabulary of one.

Related: [ARCHITECTURE.md](../ARCHITECTURE.md),
[docs/MODULE_DEVELOPMENT.md](MODULE_DEVELOPMENT.md) (building a Module).
