# CLAUDE.md — opama

AI assistant guide for the opama codebase.

## Project Overview

**opama — Open Personal Asset Management**
Full-stack personal asset management platform. Started as a Pokémon TCG collection manager; now supports any asset class. Sell items online via the built-in Storefront module, which publishes to any static storefront site.

- **Backend:** FastAPI + SQLModel + PostgreSQL + Alembic (Python 3.11+)
- **Frontend:** React 19 + TypeScript 5.8 + Vite 7 + Tailwind CSS 4
- **Auth:** Firebase Admin SDK (token verified server-side on every request)
- **AI/ML:** OpenCV card grading, Ollama local vision models, Tesseract OCR, Chromadb + FlagEmbedding RAG, pluggable LLM providers (OpenAI/Anthropic/Ollama) via `external_plugins/opama_ai/providers/`
- **External APIs:** Pokémon TCG API, eBay Browse API, GitHub Contents API; LLM provider selected via `AI_PROVIDER` (OpenAI GPT-4o-mini default, Anthropic Claude, or local Ollama)

**Running:** Docker Compose locally. API at `http://localhost:6000`, UI at `http://localhost:5173`.

**Vocabulary:** [docs/GLOSSARY.md](docs/GLOSSARY.md) is the source of truth for
project terms — **Opama Core** (the base engine), **Module** (a unit of
functionality; the one word for service/plugin/feature), **Edition** (a
domain-specific solution built on Core — *Opama Pokémon Edition* is the
flagship), **Collection**, **Organization**. Use these terms in docs, UI strings,
and new code (it's a lexicon, not a rename — existing symbols stay).

**Other docs:** [USERGUIDE.md](USERGUIDE.md) (end-user walkthrough) and
[docs/MODULE_DEVELOPMENT.md](docs/MODULE_DEVELOPMENT.md) (building a new
module/plugin — manifest schema, settings/secrets pattern, distribution
channels).

---

## Architecture

### Directory Structure

```
opama/
├── app/
│   └── main.py                  # FastAPI app, middleware, router registration, startup
├── services/                    # Domain services (modular monolith)
│   ├── shared/                  # Cross-cutting: database engine, SQLModel table definitions
│   │   ├── database.py          # engine, get_session, init_db, ensure_indexes
│   │   └── models*.py           # Card, Set, User, Inventory, Deck, Portfolio, Showcase…
│   ├── auth/                    # Firebase token verification, get_current_user dependency
│   ├── catalog/                 # GET /cards, /cards/sets — Pokémon TCG catalog
│   ├── inventory/               # GET/POST/PATCH/DELETE /inventory
│   ├── decks/                   # GET/POST/PATCH/DELETE /decks
│   ├── trading/                 # Wishlist & trade list
│   ├── ai/                      # /suggest, /ai/chat (RAG pipeline)
│   ├── portfolio/               # Portfolio valuation & snapshots
│   ├── showcase/                # Public card showcases
│   ├── grading/                 # Card grading: OpenCV analysis, identification, report PNG
│   ├── custom_assets/           # Personal collections (any asset class)
│   ├── storefront/              # Storefront: listings, sales, publish, GitHub integration
│   └── integrations/            # OpenClaw integration
├── opama-ui/src/
│   ├── OpamaApp.tsx           # App shell, global state, module routing
│   ├── features/                # Feature modules
│   │   ├── dashboard/           # DashboardView — module cards, per-category collections
│   │   ├── catalog/             # Pokémon card catalog & search
│   │   ├── inventory/           # Pokémon inventory management
│   │   ├── decks/               # Deck building
│   │   ├── grading/             # Card grading upload & results
│   │   ├── custom-assets/       # Collections (CustomAssetsModule, AssetForm, AssetCard, ImageLightbox)
│   │   ├── collections/         # Collection templates (templates.ts, TemplatePicker)
│   │   ├── storefront/          # Storefront module (ListingsTab, SalesTab, PublishTab, SettingsTab)
│   │   ├── portfolio/           # Portfolio valuation charts
│   │   └── trading/             # Wishlist & trade list
│   ├── shared/                  # Shared atoms: CardTile, ConfirmModal, HeaderBar, atoms/*
│   └── lib/                     # api.ts, firebase.ts, images.ts
├── uploads/                     # Persisted user uploads (gitignored)
│   ├── grading/                 # Card scan images: {result_id}.jpg
│   └── assets/                  # Collection images: {id}.{ext}, {id}_thumb.jpg, {id}_back.{ext}, {id}_back_thumb.jpg
└── scripts/                     # Utility scripts (import, ingest, backup, thumbnail backfill)
```

### Key Architectural Points

**Auth:** Every protected endpoint depends on `get_current_user` from `services/auth/middleware.py`. This verifies the Firebase ID token (cached 5 min) and returns the `User` row. There is no demo/bypass mode — `user_id` query params were removed from deck endpoints.

**Ownership:** Endpoints that mutate user data call `_assert_owner()` helpers that raise `403` if the resource belongs to a different user. Pattern established in `services/custom_assets/router.py` and `services/decks/router.py`.

**Static file serving:** `/uploads` is served via FastAPI `StaticFiles`. Uploaded filenames are always `{integer_id}.{ext}` — no user-controlled filenames, no path traversal risk.

**Frontend routing:** `OpamaApp.tsx` holds the active module state. `DashboardView` renders per-category collection cards dynamically by fetching `/assets/summary` — each category the user has items in becomes its own module card.

**Collection templates → navigation:** Dashboard passes `templateId` or `"category:Name"` via `onSelectModule("custom", undefined, id)`. `CustomAssetsModule` handles both: template IDs navigate using the template's category; `"category:X"` strings directly set `selectedCategory`.

**Nav modules:** The top nav (`HeaderBar.tsx`) shows Home, Collections, Portfolio, Storefront. Pokémon TCG and Grader are accessible from the Dashboard cards but removed from the top nav to save space. Labels show only on `lg:` screens; icons always show.

---

## Backend Conventions

### Always use dependency injection for DB sessions

```python
from services.shared.database import get_session
from services.auth.middleware import get_current_user

@router.get("/things")
def list_things(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    return session.exec(select(Thing).where(Thing.user_id == current_user.id)).all()
```

Never create `Session(engine)` directly in route handlers.

### Static routes before dynamic routes

```python
@router.get("/summary")          # static — must come before /{asset_id}
@router.get("/website-listings") # static
@router.get("/{asset_id}")       # dynamic — always last
```

### Commit/refresh after writes

```python
session.add(item)
session.commit()
session.refresh(item)   # populates item.id and server defaults
return item
```

### FK-safe deletes

When deleting a parent row that has FK-constrained children, flush the child deletes first:

```python
for f in fields:
    session.delete(f)
session.flush()       # send DELETE statements for children before parent
session.delete(asset)
session.commit()
```

SQLAlchemy's unit-of-work does not guarantee delete ordering — skipping `flush()` causes `ForeignKeyViolation` errors.

### Merge-on-duplicate (Inventory)

Uniqueness key: `(user_id, card_id, condition, is_holo, is_reverse_holo, is_alt_art)`.
Check for existing row first; if found, increment quantity instead of inserting.
See `services/inventory/router.py`.

### File uploads

All upload endpoints validate content-type and enforce size limits before writing:
- Grading scans: 20 MB max (`external_plugins/opama_grading/router.py`)
- Asset images: 10 MB max (`services/custom_assets/router.py`)

Files are written to `/app/uploads/{domain}/{id}.{ext}`. Never use user-supplied filenames.

Image upload endpoints also generate a 300 px-wide JPEG thumbnail alongside the full image using Pillow (`_make_thumbnail()` in `services/custom_assets/router.py`).

---

## Frontend Conventions

### API client

Always use `api<T>()` from `lib/api.ts` — it attaches the Firebase auth token, handles retries, and surfaces errors.

For file uploads (multipart), use `fetch` directly with `FormData` and attach the token manually:
```typescript
const token = await auth.currentUser?.getIdToken();
const res = await fetch(`${API_BASE}/assets/${assetId}/image`, {
  method: "POST",
  headers: token ? { Authorization: `Bearer ${token}` } : {},
  body: fd,
});
```

### Image URLs

Uploaded images are stored as relative paths (`/uploads/assets/5.jpg`). Always resolve them before rendering:
```typescript
src={url.startsWith("/") ? `${API_BASE}${url}` : url}
```

For collection card grids, prefer `image_thumb_url` over `image_url` to reduce browser load. Fall back to `image_url` if thumb is null (e.g. pre-thumbnail items):
```typescript
const src = asset.image_thumb_url || asset.image_url;
```

### Toast notifications

Components receive `onToast: (msg: string, type?: "success" | "error" | "info") => void` as a prop. Always call it on success and on catch — never swallow errors silently.

### Collection module navigation

To navigate to Collections filtered by category:
```typescript
// Template-based (uses template.id to set selectedCategory via template.category)
onSelectModule("custom", undefined, "art")

// Direct category (no template needed)
onSelectModule("custom", undefined, "category:Art")
```

### Tailwind CSS class scanning

Tailwind v4's JIT scanner reads class names from source files. Classes inside helper functions that return template literals may not be reliably detected. Always inline className strings directly on JSX elements rather than building them in helper functions.

---

## Card Grading Service

**Location:** `external_plugins/opama_grading/` (external plugin, id `grading`, premium tier)

### Pipeline

1. **Rectification** (`analyzer.py`) — 7 edge-detection strategies + `minAreaRect` fallback to perspective-correct the card. Confidence: `high` (found boundary) or `low` (fallback to full image).
2. **Centering** — gradient-based inner printed border detection on horizontal/vertical profiles.
3. **Corners** — Sobel 90th-percentile gradient on 10% corner patches (upscaled 2×). Rubric: 75/60/45/32/22/14/8 → PSA 10–4.
4. **Surface** — directional top-hat (H vs V). Holo cards have symmetric energy; scratches are asymmetric. Discount: `symmetry × 0.85`. Threshold: >35% = minor wear, >55% = likely scratched.
5. **Edges** — std deviation of 6px edge strips (skipping outermost 3px to avoid warp fill artifacts).
6. **Grade** — weighted: centering 35%, corners 35%, surface 20%, edges 10%.

### Identification

`identifier.py` tries three providers in order:
1. Ollama full-image vision (models from `OLLAMA_VISION_MODELS` env var)
2. Ollama region-crop (bottom-right corner, 3× upscaled)
3. Tesseract OCR

Fusion: card number from region-crop > tesseract > full-image; name from full-image. Results stored as `IdentificationAttempt` rows — user corrections during transfer become ground truth for per-provider accuracy stats.

### Endpoints

```
POST /grading/analyze              # Upload scan → grade + identification
POST /grading/{id}/transfer        # Save to inventory or custom asset collection
GET  /grading/{id}/report.png      # Download PNG grading report (auth required)
POST /grading/{id}/feedback        # Submit accuracy feedback
GET  /grading/history              # Past grading results
GET  /grading/feedback/stats       # Aggregated accuracy stats
GET  /grading/provider-stats       # Per-provider identification accuracy
```

### Report generation

`report.py` generates a 860×520 landscape PNG using Pillow. Corner dots appear in the sub-label slot of the Corners row (not to the right of the score bar). Fonts: DejaVu Sans (available via `tesseract-ocr` apt package in Docker).

---

## Custom Assets / Collections

**Location:** `services/custom_assets/`, `opama-ui/src/features/custom-assets/`

### Model fields of note

Core: `name`, `category`, `condition`, `quantity`, `purchase_price`, `estimated_value`, `tags`, `custom_fields` (separate table).

Images: `image_url`, `image_thumb_url`, `back_image_url`, `back_image_thumb_url`.

Marketplace links (dedicated columns, not custom fields): `marketplace_ebay`, `marketplace_facebook`, `marketplace_kijiji`, `marketplace_craigslist`.

Website listing: `listed_on_website`, `listing_price_cad`, `shipping_price_cad`, `website_slug`.

Sale recording (set by the storefront webhook): `sale_price_cad`, `sale_date`, `sale_platform`.

### Image upload

- `POST /assets/{asset_id}/image` — front image. JPEG/PNG/WebP, 10 MB max.
- `POST /assets/{asset_id}/back-image` — back image. Same constraints.

Both endpoints:
1. Write the full-resolution file as `{id}.{ext}` / `{id}_back.{ext}`
2. Generate a 300 px-wide JPEG thumbnail as `{id}_thumb.jpg` / `{id}_back_thumb.jpg`
3. Update `image_url` + `image_thumb_url` (or `back_*` variants) on the asset

Upload only available when editing (needs an existing ID); new items use the URL field.

### Thumbnail backfill

Run `scripts/backfill_asset_thumbnails.py` to generate thumbnails for images that predate the thumbnail feature. The script reads `ASSET_UPLOADS_PATH` from the environment (defaults to `<repo>/uploads/assets`) and writes `{id}_thumb.jpg` files alongside existing images.

### Image display (frontend)

- **Card grid:** `aspect-[2/3]` portrait container, uses `image_thumb_url` (falls back to `image_url`).
- **Detail view:** front + back images side-by-side (or single if only one). Click any image to open `ImageLightbox` with prev/next navigation.
- **Lightbox:** `opama-ui/src/features/custom-assets/ImageLightbox.tsx` — keyboard: Escape closes, arrow keys navigate.

### Collection templates

`opama-ui/src/features/collections/templates.ts` defines 40+ templates (`TEMPLATES` array). Two lookup maps are exported:
- `TEMPLATE_MAP`: `id → template`
- `CATEGORY_TO_TEMPLATE`: `category.toLowerCase() → template` (used by dashboard for emoji + navigation)

---

## Storefront Module

**Location:** `external_plugins/opama_storefront/`, `opama-ui/src/features/storefront/`

The Storefront module provides end-to-end management of items listed for sale on an external website, with GitHub API publishing that triggers automatic Cloudflare Pages deployment.

### Model

`StorefrontSettings` — one row per user. Stores:
- Shop identity: `site_name`, `site_url`, `public_api_url`
- Publish targets: `catalog_path` (filesystem), `webhook_url` (HTTP POST)
- GitHub: `github_token`, `github_repo`, `github_file_path`, `github_commit_message`
- `last_published_at`

The GitHub token is **never returned in API responses**. The `StorefrontSettingsOut` schema returns `github_token_set: bool` and `github_token_hint` (last 4 chars) only. Submitting an empty token on `PUT /storefront/settings` preserves the existing value.

### Publish flow

`POST /storefront/publish` runs these steps in order, stopping at the first success:

1. **GitHub** — if `github_token`, `github_repo`, `github_file_path` are set: GET current file SHA, PUT with base64 content → Cloudflare auto-deploys on push (~60 seconds)
2. **File path** — write `catalog.json` to the configured absolute path inside the container
3. **Webhook** — POST the catalog JSON array to the configured URL

Returns `PublishResult` including `github_commit_url` when a GitHub commit was made.

### Catalog entry format

Each entry follows the storefront `catalog.json` schema:
```python
{
  "id":          website_slug or str(asset.id),
  "title":       asset.name,
  "category":    _category_slug(asset.category),  # normalized slug
  "condition":   asset.condition or "",
  "description": asset.description or "",
  "priceCad":    asset.listing_price_cad or 0.0,
  "shippingCad": asset.shipping_price_cad or 0.0,
  "images":      [absolute_front_url, absolute_back_url],  # uses public_api_url
  "sold":        bool(asset.sale_date),
  "marketplaceLinks": { "ebay": ..., "facebook": ..., "kijiji": ..., "craigslist": ... },
}
```

### Endpoints

```
GET    /storefront/settings           # 404 if not configured yet
PUT    /storefront/settings           # upsert; empty github_token preserves existing
GET    /storefront/listings           # all listed_on_website=true assets + catalog preview
PATCH  /storefront/listings/{id}      # quick-edit price, shipping, slug, marketplace links
GET    /storefront/sales              # sold assets with revenue totals and platform breakdown
GET    /storefront/publish/preview    # generate catalog without pushing
POST   /storefront/publish            # generate + push to GitHub / file / webhook
```

---

## Storefront Site Integration

The Storefront module integrates opama with an external static e-commerce site (any GitHub-hosted site that reads a `catalog.json` — e.g. a Cloudflare Pages shop).

### Full publish flow (Storefront module)

```
opama Storefront → POST /storefront/publish
  → GitHub Contents API (PUT catalog.json to repo)
  → Cloudflare Pages detects push → deploys live site (~60 s)
  → buyer purchases → Stripe checkout session (dynamic line items)
  → Stripe webhook → Cloudflare Worker → POST /assets/website-listings/{slug}/sold
  → CustomAsset.sale_price_cad / sale_date / sale_platform set
  → appears in Storefront → Sales tab
```

No Stripe products need to be pre-created. The Cloudflare Worker builds ephemeral line items from `catalog.json` at checkout time using `title`, `priceCad`, `shippingCad`, and `images[0]`.

### Export key (legacy / webhook fallback)

`X-Export-Key` header — value from `WEBSITE_EXPORT_KEY` env var. Compared using `hmac.compare_digest` (constant-time). Used by:
- `GET /assets/website-listings` — pull endpoint for the storefront site's admin tool
- `POST /assets/website-listings/{slug}/sold` — Stripe webhook (called by Cloudflare Worker)

### Image URLs for listings

`public_api_url` in `StorefrontSettings` (or `PUBLIC_API_URL` env var as fallback) is prepended to relative `/uploads/…` paths so the shop can load them. Must be publicly reachable. For local dev, use ngrok or Cloudflare Tunnel.

### Category mapping

`_category_slug()` normalises free-text categories to storefront catalog slugs: "Trading Card/Cards" → `trading-cards`, "Comic/Comic Book" → `comics`, "Coin/Coins" → `coins`, "Jewelry/Jewellery" → `jewelry`, else lowercased+hyphenated.

---

## Security

### What's in place

- Pluggable auth: `AUTH_PROVIDER` env var selects `local` (username/password, OSS self-hosted default — zero external setup) or `firebase` (cloud/multi-tenant). See `services/auth/providers/`.
- Firebase token verified server-side on every protected request (`services/auth/middleware.py`). Token cache TTL: 5 min.
- Local accounts may be passwordless for low-friction self-hosted use. `GET /auth/config` reports `instance_exposed: true` whenever `CORS_ORIGINS` names a non-loopback origin; the frontend (`AuthGuardrail.tsx`) escalates from a dismissible banner nudge to a "Secure this instance" modal (with session-scoped snooze) until a password is set via `POST /auth/set-password`.
- All deck endpoints require auth; ownership checked via `_assert_deck_owner()`.
- All custom asset endpoints require auth; ownership checked via `_assert_owner()`.
- Rate limiting: 100/min global (slowapi), 10/min on `/grading/analyze`.
- File uploads: content-type validated, size capped (10–20 MB), integer-only filenames.
- Export key: `hmac.compare_digest` constant-time comparison.
- GitHub token: stored in DB, never returned in API responses (hint only).
- Security headers middleware: `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Content-Security-Policy`.
- CORS: localhost origins by default; override with `CORS_ORIGINS` env var.

### Still to address before production

- Set `PUBLIC_API_URL` and `CORS_ORIGINS` for production domain.
- HTTPS only — terminate TLS at reverse proxy.

(Resolved earlier items, kept for history: `/inventory/backup/db` and `/debug/db-info` were removed from the live code; no `.env` file was ever committed.)

---

## Development

### Start everything

```bash
cd <repo-root>
docker compose up -d
# UI: http://localhost:5173
# API: http://localhost:6000
# API docs: http://localhost:6000/docs
```

### After code changes

```bash
# Backend (Python) — requires rebuild:
docker compose up -d --no-deps --force-recreate backend

# Frontend (React/TS) — hot-reloads via volume mount, no rebuild needed.
# If Vite module cache is stale (export not found errors):
docker restart opama-frontend
```

### Environment variables (`.env.local`)

```bash
# Database
DATABASE_URL=postgresql://opama_user:opama_dev_pass@localhost:5433/opama_dev

# Firebase
FIREBASE_PROJECT_ID=your-firebase-project
FIREBASE_SERVICE_ACCOUNT_KEY=/path/to/service-account.json  # optional
FIREBASE_WEB_API_KEY=...

# Ollama (card identification + optional chat provider)
OLLAMA_URL=http://host.docker.internal:11434
OLLAMA_VISION_MODELS=minicpm-v:latest,llama3.2-vision:11b,llava:7b
OLLAMA_MODEL=llama3.2

# AI provider for /ai/chat, /suggest/chat, /suggest/ai (openai | anthropic | ollama)
AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...  # only needed when AI_PROVIDER=anthropic

# eBay
EBAY_ENV=SANDBOX
EBAY_CLIENT_ID=...
EBAY_CLIENT_SECRET=...

# Storefront website export (Stripe webhook auth)
WEBSITE_EXPORT_KEY=...
PUBLIC_API_URL=https://api.your-domain.com  # needed for absolute image URLs in listings

# Redis
REDIS_HOST=redis

# Misc
CORS_ORIGINS=http://localhost:5173  # comma-separated for production
```

---

## API Quick Reference

### Cards & Catalog
```
GET  /cards                  # List/search cards (?q=, ?set_id=, ?limit=, ?offset=)
GET  /cards/sets             # All sets
GET  /cards/{card_id}        # Single card
GET  /cards/export.ndjson    # Streaming export
```

### Inventory
```
GET    /inventory            # List inventory (auth user)
POST   /inventory            # Add item (merge-on-duplicate)
PATCH  /inventory/{id}       # Update quantity/condition
DELETE /inventory/{id}       # Remove item
```

### Decks (all endpoints require auth + ownership)
```
GET    /decks                         # List user's decks
POST   /decks                         # Create deck
GET    /decks/{id}                    # Get deck + cards
PATCH  /decks/{id}                    # Rename / update format
DELETE /decks/{id}                    # Delete deck + cards
POST   /decks/{id}/cards              # Add card (idempotent)
PATCH  /decks/{id}/cards/{card_id}    # Update quantity/role
DELETE /decks/{id}/cards/{card_id}    # Remove card
```

### Collections
```
GET    /assets                              # List (auth user, ?category=, ?q=)
GET    /assets/summary                      # Portfolio totals + per-category breakdown
GET    /assets/categories                   # Distinct categories
POST   /assets                              # Create item
GET    /assets/{id}                         # Get item
PATCH  /assets/{id}                         # Update item
DELETE /assets/{id}                         # Delete item (also removes uploaded images)
POST   /assets/{id}/image                   # Upload front image + auto-thumbnail
POST   /assets/{id}/back-image              # Upload back image + auto-thumbnail
GET    /assets/website-listings             # storefront export (X-Export-Key)
POST   /assets/website-listings/{slug}/sold # Record sale (X-Export-Key, called by Stripe webhook)
```

### Storefront
```
GET    /storefront/settings            # Get settings (404 if not configured)
PUT    /storefront/settings            # Upsert settings
GET    /storefront/listings            # Active listings with catalog preview
PATCH  /storefront/listings/{id}       # Quick-edit price/shipping/slug/marketplace links
GET    /storefront/sales               # Sold items + revenue summary
GET    /storefront/publish/preview     # Preview catalog without publishing
POST   /storefront/publish             # Publish: GitHub → file path → webhook (first success wins)
```

### Card Grading
```
POST /grading/analyze         # Upload scan → grade + identification (10/min rate limit)
POST /grading/{id}/transfer   # Transfer to inventory or collection
GET  /grading/{id}/report.png # Download PNG report
POST /grading/{id}/feedback   # Submit accuracy feedback
GET  /grading/history         # Past results
GET  /grading/feedback/stats  # Accuracy statistics
GET  /grading/provider-stats  # Per-provider identification accuracy
```

### AI & Suggestions
```
GET  /suggest/{deck_id}   # Heuristic card suggestions
POST /ai/chat             # RAG deck chat
```

### Utility
```
GET /healthz              # Health probe
GET /docs                 # OpenAPI / Swagger UI
```

---

## Quick Start Checklist

When starting work on this codebase:

- [ ] `docker ps | grep opama` — confirm backend, frontend, postgres, redis are running
- [ ] If not: `docker compose up -d` from the repo root
- [ ] Check `.env.local` for required API keys
- [ ] **Backend changes** → `docker compose up -d --no-deps --force-recreate backend`
- [ ] **Frontend changes** → hot-reload via volume mount; `docker restart opama-frontend` if stale
- [ ] Test at `http://localhost:5173` + `http://localhost:6000/docs`
- [ ] Commit: `feat/fix/chore/docs: short summary`
