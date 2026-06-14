# opama — Open Personal Asset Management

A self-hosted platform for cataloguing, valuing, and selling the things you collect — watches, art, wine, trading cards, coins, anything. Modular by design: every feature is a plugin, and you can build your own.

<!-- TODO: add dashboard screenshot/GIF here before announcing -->

> 📖 **Using opama?** See [USERGUIDE.md](USERGUIDE.md) for a walkthrough of Collections, Portfolio, and Storefront setup.
> 🔌 **Building a module?** See [docs/MODULE_DEVELOPMENT.md](docs/MODULE_DEVELOPMENT.md).

The built-in **Storefront** module connects opama to your own e-commerce site: list items, set prices, publish a `catalog.json` to your site's GitHub repo in one click (auto-deploys via Cloudflare Pages), and have Stripe sales written back to opama automatically.

---

## Features

| Module | Description |
|---|---|
| **Dashboard** | Per-category collection cards, portfolio value, quick actions |
| **Collections** | Template-based tracking for any asset class (watches, art, wine, cards, coins…). Front + back images, portrait thumbnails, lightbox viewer. |
| **Portfolio** | Aggregated valuation, unrealized gain/loss, historical snapshots, allocation charts |
| **Storefront** | List items for sale, manage prices and marketplace links, publish `catalog.json` to GitHub (auto-deploys via Cloudflare Pages), view sales history |
| **Card Grader** | Upload a scan → OpenCV grades centering, corners, surface, edges → PSA-scale estimate + downloadable report |
| **Pokémon TCG** | Catalog browsing, inventory, deck building, wishlists, trade lists |
| **Showcase** | Public or private display pages for card collections |
| **Marketplace** | eBay listing search with optional affiliate integration |
| **AI Suggestions** | RAG-backed deck building assistant (OpenAI, Anthropic, or local Ollama + Chroma) |

---

## Tech Stack

**Backend**
- Python 3.11 · FastAPI · SQLModel · Alembic
- PostgreSQL (Docker) · Redis
- Pluggable auth — local username/password accounts by default (zero external setup), optional Firebase
- OpenCV + Pillow — deterministic card grading pipeline; thumbnail generation
- Ollama (local vision models) + Tesseract OCR — card identification
- OpenAI GPT-4o-mini · Chromadb · FlagEmbedding — AI/RAG deck suggestions

**Frontend**
- React 19 · TypeScript 5 · Vite 7
- Tailwind CSS 4 · Recharts · Lucide icons · Motion

**Infrastructure**
- Docker Compose (Postgres 16 + Redis 7 + backend + frontend)
- Uploaded files persisted in `uploads/` (volume-mounted)

---

## Quick Start

### Prerequisite

Install **Docker Desktop** (or [OrbStack](https://orbstack.dev) on Mac — lighter and faster).

- Mac: https://orbstack.dev *(recommended)* or https://docs.docker.com/desktop/install/mac-install/
- Windows: https://docs.docker.com/desktop/install/windows-install/

No other runtimes needed — Python, Node, and PostgreSQL all run inside Docker.

### 1. Clone

```bash
git clone git@github.com:GeneralOperationsDirector/opama-oss.git
cd opama-oss
```

### 2. First-time setup

**Mac / Linux:**
```bash
chmod +x opama.sh
./opama.sh setup
```

**Windows (PowerShell):**
```powershell
.\opama.ps1 setup
```

The setup wizard prompts for a Postgres password, your auth provider (**local** is the default and needs no external accounts — a signing secret is generated for you; choose **firebase** only for Firebase-backed auth), and optional API keys, then writes `.env` and `.env.local` automatically.

### 3. Start

```bash
./opama.sh start        # Mac/Linux — starts services and opens browser
.\opama.ps1 start       # Windows
```

- **Dashboard:** http://localhost:5173
- **API docs:** http://localhost:6000/docs

### Optional: demo data

To see the dashboard populated before adding your own items:

```bash
./opama.sh seed-demo        # or: python3 scripts/seed_demo.py
```

This creates a `demo` account with a small sample collection (watches, art,
cards, coins, vinyl) across several categories. Every item is tagged
`demo-seed` so it's easy to find and delete later.

### Launcher commands

```
./opama.sh setup            First-time configuration wizard
./opama.sh start            Start all services and open the dashboard
./opama.sh stop             Stop all services
./opama.sh restart          Stop then start
./opama.sh status           Show container health and API connectivity
./opama.sh logs             Stream logs  (./opama.sh logs backend)
./opama.sh backup           Back up the database to ./backups/
./opama.sh restore          Restore a database backup
./opama.sh update           Pull latest code and rebuild
./opama.sh seed-demo        Add a sample collection (demo account) to explore with
./opama.sh open             Open the dashboard in your browser
./opama.sh install-tray     Install the system tray icon (Linux)
./opama.sh uninstall-tray   Remove the system tray icon
```

The same commands work on Windows via `.\opama.ps1 <command>` (tray not supported on Windows).

---

## System Tray (Linux)

`opama-tray.py` is a lightweight GTK3 system tray app that gives one-click access to all common operations without opening a terminal.

### Install

```bash
./opama.sh install-tray
```

This installs the autostart entry (`~/.config/autostart/opama-tray.desktop`) and launches the tray immediately. It will auto-start on every login.

### Requirements

The tray uses the same AppIndicator3/Ayatana stack as other Linux tray apps. Install if missing:

```bash
sudo apt install python3-gi gir1.2-ayatanaappindicator3-0.1 python3-pil
```

GNOME users also need the AppIndicator extension enabled:

```bash
gnome-extensions enable ubuntu-appindicators@ubuntu.com
```

### Tray menu

| Item | Action |
|---|---|
| **Status: Running / Stopped** | Live health label — polls `/healthz` every 8 seconds |
| **Open Dashboard** | Opens `http://localhost:5173` in the browser |
| **Open API Docs** | Opens `http://localhost:6000/docs` |
| **Start** | `docker compose up -d` |
| **Stop** | `docker compose down` |
| **Restart** | Stop then start |
| **Back Up Database** | Saves to `./backups/` and sends a desktop notification |
| **Quit tray** | Exits the tray (does not stop the services) |

The icon shows an indigo circle with a **green dot** when the API is healthy and a **red dot** when stopped or unreachable.

### Remove

```bash
./opama.sh uninstall-tray
```

### Rebuilding after code changes (without the launcher)

```bash
# Backend (Python) — requires rebuild:
docker compose up -d --no-deps --force-recreate backend

# Frontend — hot-reloads via volume mount automatically.
# If Vite's module cache goes stale:
docker restart opama-frontend
```

---

## Project Structure

```
opama/
├── opama.sh                    # Launcher: setup / start / stop / backup / update (Mac/Linux)
├── opama.ps1                   # Launcher: same commands for Windows PowerShell
├── opama-tray.py               # System tray icon for Linux (GTK3 + AppIndicator3)
├── app/
│   └── main.py                 # FastAPI app, middleware, router registration, startup
├── services/                   # Domain service layer
│   ├── shared/                 #   SQLModel table definitions, database engine, auth middleware
│   ├── auth/                   #   Firebase token verification
│   ├── catalog/                #   Card/set catalog (GET /cards, /cards/sets)
│   ├── inventory/              #   Card inventory management
│   ├── decks/                  #   Deck building
│   ├── trading/                #   Wishlists and trade lists
│   ├── ai/                     #   RAG pipeline, chat router, suggest router
│   ├── portfolio/              #   Portfolio valuation & snapshots
│   ├── showcase/               #   Public collection pages
│   ├── grading/                #   OpenCV card grading, identification, PNG report
│   ├── custom_assets/          #   Collections — any asset class
│   ├── storefront/             #   Storefront management and GitHub publishing
│   ├── system/                 #   System info endpoint (uptime, data stats)
│   └── integrations/           #   OpenClaw integration
├── opama-ui/                 # React frontend
│   └── src/
│       ├── features/           #   Feature modules (dashboard, grading, custom-assets, storefront…)
│       ├── shared/             #   Shared components (HeaderBar, CardTile, atoms/)
│       └── OpamaApp.tsx      #   App shell and global state
├── uploads/                    # Persisted user uploads (gitignored)
│   ├── grading/                #   Card scan images
│   └── assets/                 #   Collection item images + thumbnails
├── backups/                    # Database backups from ./opama.sh backup (gitignored)
├── alembic/                    # Database migrations
├── scripts/                    # Import, ingest, backup, and migration utilities
├── docker-compose.yml
└── .env.example                # Environment variable template
```

---

## Environment Variables

Copy `.env.example` to `.env.local` and fill in your values. Key variables:

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | `postgresql://user:pass@host:port/db` |
| `POSTGRES_PASSWORD` | Yes (Docker) | Postgres password — also set in `.env` for Docker Compose |
| `AUTH_PROVIDER` | No (default `local`) | `local` (username/password, no external services) or `firebase` |
| `LOCAL_AUTH_SECRET` | When `local` | Signs local-account tokens — generate with `openssl rand -hex 32` |
| `FIREBASE_PROJECT_ID` | When `firebase` | Firebase project ID for auth |
| `FIREBASE_SERVICE_ACCOUNT_KEY` | When `firebase` | Path to Firebase service account JSON |
| `FIREBASE_WEB_API_KEY` | When `firebase` | Firebase Web API key (token verification fallback) |
| `OPENAI_API_KEY` | AI features | GPT-4o-mini for deck suggestions |
| `OLLAMA_URL` | Card grading | Local Ollama URL e.g. `http://host.docker.internal:11434` |
| `OLLAMA_VISION_MODELS` | Card grading | Comma-separated model list e.g. `minicpm-v:latest,llava:7b` |
| `EBAY_CLIENT_ID` / `EBAY_CLIENT_SECRET` | Marketplace | eBay Browse API credentials |
| `CORS_ORIGINS` | Production | Comma-separated allowed origins |
| `WEBSITE_EXPORT_KEY` | Storefront | Shared secret for `/assets/website-listings` (Stripe webhook) |
| `PUBLIC_API_URL` | Storefront | Absolute API URL for uploaded image links e.g. `https://api.yourdomain.com` |

See `.env.example` for the full list.

---

## Database Migrations

Migrations are managed with Alembic.

```bash
# Apply all pending migrations
alembic upgrade head

# Generate a migration after changing models
alembic revision --autogenerate -m "describe_the_change"

# Rollback one step
alembic downgrade -1
```

> **Note:** New migration files in `alembic/versions/` must include `import sqlmodel` if they use `sqlmodel.sql.sqltypes.AutoString`. This is a known quirk of Alembic's autogenerate with SQLModel.

---

## AI / RAG Pipeline

Deck suggestions use a hybrid retrieval pipeline:

```
User Query → Deck Context → Hybrid Retrieval → Cross-Encoder Rerank → GPT-4o-mini
                                ↓
                    Chroma (semantic, 0.7 weight)
                         +
                    FTS5 (keyword, 0.3 weight)
```

**One-time setup:**
```bash
# Requires Ollama running: ollama serve
EMBED_MODEL=nomic-embed-text python scripts/ingest_cards.py
```

**Environment:**
```bash
CHROMA_PATH=var/chroma
OLLAMA_URL=http://localhost:11434
RERANK_ENABLED=true
RERANKER_MODEL=BAAI/bge-reranker-v2-m3
```

---

## Image Assets

Card images (~4GB, ~19,000 files) are **not stored in this repository**. They are excluded via `.gitignore`. For local development, copy them into `opama-ui/public/img/` manually. For production, host them on a CDN (S3 + CloudFront, Cloudflare R2, etc.) and update the image URL builder in `opama-ui/src/lib/images.ts`.

Collection item images are uploaded by users and stored in `uploads/assets/`. Thumbnails (300 px wide JPEG) are generated automatically on upload and stored alongside originals as `{id}_thumb.jpg`.

---

## API Reference

Full interactive docs at `/docs` when the server is running.

**Core endpoints:**

```
# Catalog
GET  /cards/search?q=&set_id=&limit=&offset=
GET  /cards/{card_id}
GET  /cards/sets

# Inventory
GET  /inventory
POST /inventory          # merge-on-duplicate
PATCH/DELETE /inventory/{id}

# Decks (auth + ownership required)
GET    /decks
POST   /decks
GET    /decks/{id}
PATCH  /decks/{id}
DELETE /decks/{id}
POST   /decks/{id}/cards

# Collections
GET    /assets
POST   /assets
PATCH  /assets/{id}
DELETE /assets/{id}
POST   /assets/{id}/image       # upload front image (JPEG/PNG/WebP ≤10 MB), generates thumbnail
POST   /assets/{id}/back-image  # upload back image, generates thumbnail
GET    /assets/website-listings # storefront export (X-Export-Key)

# Storefront (auth required)
GET    /storefront/settings
PUT    /storefront/settings
GET    /storefront/listings
PATCH  /storefront/listings/{id}
GET    /storefront/sales
GET    /storefront/publish/preview
POST   /storefront/publish       # commit to GitHub + optional file/webhook targets

# Card Grading
POST /grading/analyze            # upload scan → grade + identification
POST /grading/{id}/transfer      # save to inventory or collection
GET  /grading/{id}/report.png    # download PNG report
GET  /grading/history

# AI
POST /ai/chat
GET  /suggest/{deck_id}

# Portfolio
GET  /portfolio/summary
POST /portfolio/snapshot

# System
GET  /system/info    # uptime, version, your data counts (auth required)

# Health & docs
GET  /healthz
GET  /docs
```

---

## Development Notes

- **Session management:** always use `Depends(get_session)` — never create sessions manually in route handlers.
- **Auth:** all endpoints except `/healthz` and public showcases require a bearer token in `Authorization: Bearer <token>` — issued by the local provider or Firebase, per `AUTH_PROVIDER`. Token cache TTL is 5 minutes.
- **Ownership checks:** deck and collection endpoints verify `resource.user_id == current_user.id` and raise `403` if mismatched.
- **FK-safe deletes:** when deleting a parent row that has child rows (e.g. `CustomAssetField`), call `session.flush()` after deleting children before deleting the parent — SQLAlchemy's unit-of-work doesn't guarantee delete order otherwise.
- **Inventory merges:** adding the same card twice increments quantity rather than creating a duplicate. Uniqueness key: `(user_id, card_id, condition, is_holo, is_reverse_holo, is_alt_art)`.
- **Static before dynamic routes:** keep `/summary`, `/website-listings` above `/{id}` in every router to avoid path conflicts.
- **Uploaded image URLs:** stored as `/uploads/assets/{id}.ext`. Resolve to full URL before rendering: `url.startsWith("/") ? \`${API_BASE}${url}\` : url`.

---

## In-App System Panel

The **⚙ gear icon** in the top-right header opens the System panel, which shows:

- API uptime and version
- Upload storage used on disk
- Your personal data counts (inventory, decks, collections, grading results)
- Copy-ready commands for backup and update

A **status dot** also appears in the header bar at all times — green when the API is reachable, pulsing red when offline. It polls `/healthz` every 30 seconds.

---

## Scripts

| Script | Purpose |
|---|---|
| `scripts/import_cards.py data/` | Bulk-import sets and cards from CSV |
| `scripts/ingest_cards.py` | Build Chroma vector index for AI search |
| `scripts/backup_db.py --verify --retain 10` | SQLite backup (dev only) |
| `scripts/backfill_asset_thumbnails.py` | Generate thumbnails for existing collection images that predate thumbnail support |

Database backups via the launcher are stored in `backups/` and auto-pruned to the 10 most recent.

To run the thumbnail backfill against a local database:
```bash
python3 scripts/backfill_asset_thumbnails.py
```

---

## Storefront Module

The **Storefront** module (`🛒` in the nav) manages the end-to-end pipeline for selling items on your website.

### Tabs

| Tab | Description |
|---|---|
| **Listings** | All `listed_on_website=true` assets. Inline edit: price, shipping, URL slug, marketplace links (eBay, Facebook, Kijiji, Craigslist). |
| **Sales** | Sold items with revenue totals and platform breakdown. Populated automatically when Stripe webhook fires. |
| **Publish** | Generate `catalog.json`, preview it, publish to GitHub / file path / webhook. Shows a direct link to the GitHub commit on success. |
| **Settings** | Shop name, public URL, API base URL, GitHub token + repo + file path, fallback file/webhook targets. |

### GitHub Publishing

Opama can commit `catalog.json` directly to your GitHub repository using the GitHub Contents API, which triggers an automatic Cloudflare Pages deploy (~60 seconds to live).

Configure in **Storefront → Settings → GitHub Publishing**:
1. Create a [fine-grained GitHub PAT](https://github.com/settings/tokens?type=beta) with **Contents: Read and write** on the target repo
2. Set the repository (`owner/repo`) and file path (`public/collectibles/catalog.json`)
3. Click **Publish** — the Publish tab shows a link to the commit

### Stripe / Cloudflare sale webhook

When a buyer completes checkout on your storefront site, your Stripe webhook handler (e.g. a Cloudflare Worker) calls:

```
POST /assets/website-listings/{website_slug}/sold
X-Export-Key: <WEBSITE_EXPORT_KEY>
{"sale_price_cad": 25.00, "sale_platform": "yourshop.com"}
```

This sets `sale_price_cad`, `sale_date`, and `sale_platform` on the `CustomAsset` and the sale appears in the **Sales** tab. No Stripe products need to be pre-created — the Worker builds ephemeral line items from `catalog.json` at checkout time.

---

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for dev-environment
setup, test instructions, and PR guidelines, and [ARCHITECTURE.md](ARCHITECTURE.md)
for a code tour of how the project is laid out. By participating you agree to the
[Code of Conduct](CODE_OF_CONDUCT.md). To report a security issue, see
[SECURITY.md](SECURITY.md) — please don't open a public issue.

## License

opama is open source under the [Apache License 2.0](LICENSE).
