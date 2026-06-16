# opama User Guide

This guide covers **using** opama day to day — the Dashboard, Collections,
Portfolio, optional modules, and the Storefront. For installing and running
opama, see [README.md](README.md).

If you're an AI assistant looking for codebase/architecture documentation
instead, see [CLAUDE.md](CLAUDE.md).

## Contents

1. [First Login](#1-first-login)
2. [Your Asset Hub (Dashboard)](#2-your-asset-hub-dashboard)
3. [Building Collections](#3-building-collections)
4. [Portfolio](#4-portfolio)
5. [Optional Modules: Pokémon TCG & Card Grader](#5-optional-modules-pokémon-tcg--card-grader)
6. [Modules — Enabling Features](#6-modules--enabling-features)
7. [Storefront — Selling Online](#7-storefront--selling-online)
8. [Account & Security](#8-account--security)
9. [System & Maintenance](#9-system--maintenance)
10. [Getting Help](#10-getting-help)

---

## 1. First Login

opama supports two account systems, chosen by your administrator:

- **Local accounts** (the default for self-hosted installs) — sign in with a
  username. New self-hosted accounts can be **passwordless** for low-friction
  setup; you'll be prompted to set a password before the instance is exposed
  beyond your local machine (see [Account & Security](#8-account--security)).
- **Firebase accounts** — email/password or social sign-in, used for hosted
  multi-tenant deployments.

Click **Login** in the top-right of the header bar to sign in or create an
account. Until you're signed in, you can browse the Dashboard and template
gallery, but nothing is saved.

---

## 2. Your Asset Hub (Dashboard)

The Dashboard ("Home" in the nav) is your starting point:

- **Your Collections** — one card per category you've added items to (e.g.
  "Watches", "Art", "Trading Cards"), showing item counts and estimated
  value. A **Start a Collection** card opens the template picker.
- **Your Modules** — appears only if you've enabled optional feature modules
  like Pokémon TCG or Card Grader (see [§6](#6-modules--enabling-features)).
  Hidden entirely if none are enabled.
- **Popular Collection Types** — quick-start templates (stocks, crypto,
  watches, guitars, sneakers, sports cards, comics, wine, coins, art, vinyl,
  bonds…). Clicking one jumps straight into Collections with that category
  pre-selected.

---

## 3. Building Collections

Collections track **any** physical or digital asset — not just trading
cards.

1. From the Dashboard, click **Start a Collection** or a template tile.
2. Pick a template (or start from scratch) — this sets the category and a
   default emoji/icon.
3. Add items: name, condition, quantity, purchase price, estimated value,
   tags, and any custom fields relevant to that asset class.
4. **Images** — once an item is saved, open it for editing to upload a front
   image and (optionally) a back image. opama generates a thumbnail
   automatically; the card grid uses thumbnails to keep things fast.
5. Click any image to open the full-size lightbox — use arrow keys or the
   on-screen controls to step through front/back and between items.

Items can later be marked **Listed on Website** to appear in the Storefront
module (see [§7](#7-storefront--selling-online)).

---

## 4. Portfolio

The Portfolio module (if enabled) aggregates the value of everything you
own:

- Total estimated value, unrealized gain/loss vs. purchase price
- Allocation breakdown by category
- Historical snapshots over time (charted)

Snapshots are taken automatically; you can also trigger one manually from the
Portfolio page.

---

## 5. Optional Modules: Pokémon TCG & Card Grader

These are specialized modules, off by default in a fresh self-hosted install.
Enable them from the **Modules** page (see [§6](#6-modules--enabling-features)).

### Pokémon TCG

Full catalog browsing, inventory tracking, deck building, wishlists/trade
lists, and AI-assisted deck suggestions (chat + heuristic recommendations).

### Card Grader

Upload a scan of a card to get a PSA-equivalent grade estimate:

1. Go to **Card Grader** → upload a clear, well-lit photo of the card
   (front; back is optional but improves identification).
2. opama analyzes centering, corners, surface, and edges, and attempts to
   identify the card (number/name) using local vision models or OCR.
3. Review the result — correct the identification if needed (your correction
   helps opama track identification accuracy over time).
4. **Transfer** the result into your Pokémon inventory or a Collections item,
   or download a shareable PNG report.

---

## 6. Modules — Enabling Features

The **Modules** page (puzzle-piece icon in the nav) is opama's plugin store.

- **Marketplace tab** — built-in modules (Pokémon TCG, Card Grader,
  Portfolio, Storefront, AI Assistant, Showcase, eBay Marketplace, …) plus
  any community modules. Click **Enable** on a module; changes take effect
  after a restart (a banner will prompt you).
- **Installed tab** — modules currently active, including any **Pip
  Modules** installed from PyPI-style packages.
- **Install from URL** — admins can install a community module by pointing
  at its `plugin.yaml` manifest URL.
- **Premium / locked modules** show a lock icon if your license tier doesn't
  include them.

Only admin accounts can enable/disable or install modules.

---

## 7. Storefront — Selling Online

The Storefront module turns your Collections into a public online shop. It
publishes a `catalog.json` file (item names, prices, images, descriptions) to
**your own website** — opama itself doesn't host the storefront's visual
design, it just keeps the data feed up to date.

### What you'll need

- A website that can serve a JSON file and images to the public — e.g. a
  static site on Cloudflare Pages / GitHub Pages / Netlify, or any server you
  control.
- A way for that site to reach **this opama instance's images** over the
  internet (see "Image URLs" below).
- *(Optional)* A checkout flow on your site (e.g. Stripe) that can call back
  into opama when an item sells, so it shows up in the **Sales** tab
  automatically.

If you're starting from scratch and don't yet have a storefront site, talk to
your administrator about a starter template — Phase C of the open-source
roadmap covers a generic, themeable storefront template.

### Step-by-step setup

Open **Storefront → Settings**:

1. **Shop Identity**
   - **Shop Name** — your brand/site name, shown in the Storefront header.
   - **Public Shop URL** — the buyer-facing URL of your shop (used for the
     "Visit shop" link).

2. **Image URLs**
   - **API Base URL** — the publicly reachable root of *this opama API*.
     Item images are stored as relative paths (e.g. `/uploads/assets/42.jpg`);
     this setting turns them into absolute URLs your website can load
     (`https://api.yourdomain.com/uploads/assets/42.jpg`).
   - **This is the step most people get stuck on.** If you're running opama
     locally and don't yet have a public domain, use a tunnel:
     - `ngrok http 6000` — gives you a temporary HTTPS URL
     - `cloudflared tunnel --url http://localhost:6000` — Cloudflare Tunnel
     - Same LAN: `http://192.168.x.x:6000` if your site and opama run on the
       same network
   - **Without this set, item images will appear broken on your site** — the
     catalog data will still publish correctly, just without working image
     URLs.

3. **Choose a publish method** — pick one (or more):
   - **GitHub Publishing** *(recommended for static sites)* — opama commits
     `catalog.json` directly to your site's GitHub repo via the GitHub API.
     If your site is on Cloudflare Pages or similar, a push triggers an
     automatic deploy (~60 seconds to live).
     1. Create a [fine-grained GitHub Personal Access Token](https://github.com/settings/tokens?type=beta)
        scoped to **only your storefront repo**, with **Contents:
        Read and write** permission.
     2. Enter the repo (`owner/repo`) and the file path where your site
        expects the catalog (e.g. `public/collectibles/catalog.json`).
     3. Save — the token is encrypted at rest and never shown again (only
        the last 4 characters, as a hint).
   - **Catalog File Path** — write `catalog.json` to a path inside the opama
     backend container (e.g. `/app/uploads/catalog.json`, which is then
     reachable at `http://localhost:6000/uploads/catalog.json`). Useful if
     your site reads from a shared volume.
   - **Webhook URL** — opama POSTs the full catalog JSON array to an HTTP
     endpoint of your choice on every publish.

4. Save settings — a green checkmark confirms a publish target is configured.

### Day-to-day use

- **Listings tab** — every item marked "Listed on Website" appears here.
  Inline-edit price, shipping cost, URL slug, and marketplace links (eBay,
  Facebook, Kijiji, Craigslist).
- **Publish tab** — preview the generated `catalog.json`, then click
  **Publish**. On success you'll see a direct link to the GitHub commit (if
  using GitHub publishing).
- **Sales tab** — sold items with revenue totals and a platform breakdown.
  Populated automatically when your site's checkout flow calls opama's sale
  webhook (`POST /assets/website-listings/{slug}/sold`, authenticated with
  the `WEBSITE_EXPORT_KEY` your administrator configured).

### Troubleshooting

| Symptom | Likely cause |
|---|---|
| Images broken on my site | **API Base URL** not set, or not publicly reachable — check it loads in a browser from outside your network |
| Publish fails with a GitHub error | Token expired/missing `contents:write`, or repo/file path typo'd |
| Items don't appear after publish | Confirm the item is marked "Listed on Website" and has a price set |
| Sales never show up | Your site's checkout isn't calling the sale webhook, or `WEBSITE_EXPORT_KEY` doesn't match |

---

## 8. Account & Security

Open the **Profile** page (person icon) to:

- View/update your display name and email
- **Set a password** — local accounts can start passwordless for convenience.
  If opama detects your instance is reachable from outside `localhost` (a
  non-loopback `CORS_ORIGINS`), you'll see a banner nudging you to set a
  password, escalating to a blocking "Secure this instance" prompt until you
  do.

**Before exposing opama to the internet:**
- Set a password on every local account
- Use HTTPS (terminate TLS at a reverse proxy)
- Rotate any secrets that may have been committed during development

---

## 9. System & Maintenance

The **⚙ gear icon** in the header opens the System panel:

- API uptime and version
- Upload storage used on disk
- Your data counts (inventory, decks, collections, grading results)
- Copy-ready backup/update commands

For command-line maintenance (backups, restores, updates), see the
[Launcher commands](README.md#launcher-commands) section of the README:

```bash
./opama.sh backup     # back up the database to ./backups/
./opama.sh restore    # restore from a backup
./opama.sh update     # pull latest code and rebuild
```

---

## 10. Getting Help

- **API docs** — `http://localhost:6000/docs` (interactive Swagger UI)
- **Building your own module?** — see
  [docs/MODULE_DEVELOPMENT.md](docs/MODULE_DEVELOPMENT.md)
- **Issues / feature requests** — your project's GitHub Issues page
