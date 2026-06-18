"""
opama — FastAPI application entry point.

Wires up:
  - Core middleware (CORS, GZip, security headers)
  - Environment loading (.env then .env.local)
  - Plugin discovery and loading (services/*/plugin.yaml)
  - Database initialization
  - Static file serving for uploads
  - Health check endpoint

Plugin loading is controlled by the ENABLED_PLUGINS environment variable:
  ENABLED_PLUGINS=           → all plugins load (default)
  ENABLED_PLUGINS=catalog,inventory,decks  → only those plugins load

Auth is always loaded; it is not part of the plugin system because it
provides the get_current_user dependency that all other plugins depend on.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# --- Environment loading -------------------------------------------------
# Must happen before any service module reads os.getenv().
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / ".env.local", override=True)

# --- Core models (always loaded) ----------------------------------------
# These must be imported before init_db() / create_all() so SQLModel
# registers the table definitions. Pokémon-specific and other premium-tier
# models live in their owning plugin packages and are imported below via
# load_plugin_models() (see each plugin's `model_modules` manifest entry).
from services.shared.database import engine, init_db, get_backend
from services.shared.models_security import UserSecret, AuditLog, ApiToken  # noqa: F401
from services.shared.models_plugin_data import PluginData  # noqa: F401

# --- Auth (always loaded) -----------------------------------------------
from services.auth import router as auth_router, init_firebase_admin
from services.billing.router import router as billing_router

# --- Plugin loader -------------------------------------------------------
from app.plugin_loader import discover_plugins, resolve_enabled, load_plugin_models, load_plugin_tools, load_plugins, load_dynamic_plugins, record_loaded_ids
from app.version import CORE_VERSION

# Discover and filter plugins before creating the app so router
# registration happens at module level (same as the old hardcoded imports).
_all_plugins = discover_plugins()
_enabled_plugins = resolve_enabled(_all_plugins)

# Import plugin-owned model modules so SQLModel sees them before create_all().
load_plugin_models(_enabled_plugins)

# --- App -----------------------------------------------------------------
app = FastAPI(
    title="opama API",
    version=CORE_VERSION,
    description="Open Personal Asset Management — plugin-based API",
)

# --- Rate limiting -------------------------------------------------------
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- Security headers ----------------------------------------------------
_CSP = "; ".join([
    "default-src 'self'",
    # Firebase auth SDK needs Google APIs + inline scripts from Vite
    "script-src 'self' 'unsafe-inline' https://apis.google.com https://*.firebaseapp.com",
    "style-src 'self' 'unsafe-inline'",
    # Card images come from external CDNs; data: and blob: for upload previews
    "img-src 'self' data: blob: https:",
    # Firebase realtime + auth endpoints
    (
        "connect-src 'self' "
        "https://*.googleapis.com "
        "https://*.firebaseio.com "
        "wss://*.firebaseio.com "
        "https://identitytoolkit.googleapis.com "
        "https://securetoken.googleapis.com"
    ),
    "frame-src https://*.firebaseapp.com",
    "frame-ancestors 'none'",
])


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Content-Security-Policy"] = _CSP
    return response

# --- CORS ----------------------------------------------------------------
import os as _os
_cors_origins_env = _os.getenv("CORS_ORIGINS", "")
_cors_origins = (
    [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
    if _cors_origins_env
    else [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.add_middleware(GZipMiddleware, minimum_size=1024)

# --- Routers -------------------------------------------------------------
# Auth is always registered — every other plugin depends on it.
app.include_router(auth_router, prefix="/auth", tags=["auth"])

# Pool billing webhook — always mounted, inert until STRIPE_WEBHOOK_SECRET is set.
# Flips Organization.plan_* columns read by services.auth.entitlements.require_tier.
app.include_router(billing_router, prefix="/billing", tags=["billing"])

# Plugin routers are registered dynamically based on ENABLED_PLUGINS.
_static_loaded = list(load_plugins(_enabled_plugins))
for _loaded in _static_loaded:
    app.include_router(
        _loaded.router,
        prefix=_loaded.manifest.api_prefix or "",
        tags=_loaded.manifest.tags or [],
    )
record_loaded_ids(_static_loaded)
load_plugin_tools([l.manifest for l in _static_loaded])

# --- Static files --------------------------------------------------------
_default_uploads = Path(__file__).resolve().parents[1] / "uploads"
_uploads_dir = Path(os.getenv("UPLOADS_PATH", str(_default_uploads)))
_uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_uploads_dir)), name="uploads")

# Root for downloaded type=local plugin packages (app/plugin_installer.py).
# Created at boot — same pattern as _uploads_dir — so the first install has
# somewhere to extract into without a manual mkdir on bare-metal deploys.
from app.plugin_installer import DYNAMIC_PLUGINS_ROOT
DYNAMIC_PLUGINS_ROOT.mkdir(parents=True, exist_ok=True)


# --- Lifecycle -----------------------------------------------------------
@app.on_event("startup")
def _startup() -> None:
    import logging
    from sqlmodel import Session
    log = logging.getLogger("uvicorn.error")

    loaded_ids = [l.manifest.id for l in _static_loaded]
    log.info(f"🔌 Loaded plugins: {', '.join(loaded_ids) if loaded_ids else '(none)'}")

    skipped_ids = [p.id for p in _enabled_plugins if p.id not in loaded_ids]
    if skipped_ids:
        log.warning(f"⚠️  Enabled but failed to load (see earlier errors): {', '.join(skipped_ids)}")

    if get_backend() == "firestore_local":
        log.info("✅ Using Firestore-local mock storage — skipping SQLite init")
    else:
        init_db()
        log.info("🗄️  Database initialised")

        # Fast-start: seed the bundled Pokémon TCG catalog snapshot on a
        # fresh, empty database. No-op if Set already has rows (including
        # one populated via POST /cards/sync/trigger before this runs).
        if "catalog" in loaded_ids:
            from opama_pokemon_tcg.catalog.seed import seed_baseline_catalog

            with Session(engine) as _session:
                _seeded = seed_baseline_catalog(_session)
            if _seeded:
                log.info(f"🌱 Seeded baseline Pokémon TCG catalog: {_seeded[0]} sets, {_seeded[1]} cards")

        # Load remote plugins persisted in the dynamic_plugins table.
        # These were installed via POST /plugin-store/install and become
        # active after the restart that triggers this startup event.
        with Session(engine) as _session:
            _dynamic = load_dynamic_plugins(_session)
        for _loaded in _dynamic:
            app.include_router(
                _loaded.router,
                prefix=_loaded.manifest.api_prefix or "",
                tags=_loaded.manifest.tags or [],
            )
        if _dynamic:
            record_loaded_ids(_dynamic)
            load_plugin_tools([p.manifest for p in _dynamic])
            log.info(f"🧩 Dynamic plugins activated: {[p.manifest.id for p in _dynamic]}")

    if get_backend() != "firestore_local":
        init_firebase_admin()
        log.info("✅ Firebase Admin initialised")
    else:
        log.info("⚠️  Firebase not initialised (mock storage mode)")


# --- Health & diagnostics ------------------------------------------------
@app.get("/healthz", tags=["health"])
def healthz():
    """Basic liveness probe."""
    return {"ok": True}


@app.get("/plugins", tags=["system"])
def list_plugins():
    """Return metadata for all enabled plugins."""
    return [
        {
            "id": p.id,
            "name": p.name,
            "version": p.version,
            "tier": p.tier,
            "description": p.description,
            "icon": p.icon,
        }
        for p in _enabled_plugins
    ]
