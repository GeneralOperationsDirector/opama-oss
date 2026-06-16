#!/usr/bin/env bash
# opama — launcher script for Mac and Linux
# Usage: ./opama.sh [command]

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}→${NC} $*"; }
success() { echo -e "${GREEN}✓${NC} $*"; }
warn()    { echo -e "${YELLOW}⚠${NC}  $*"; }
error()   { echo -e "${RED}✗${NC} $*" >&2; }
header()  { echo -e "\n${BOLD}${BLUE}$*${NC}\n"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Helpers ───────────────────────────────────────────────────────────────────

# Read KEY from .env, falling back to a default — keeps backup/restore working
# when someone customises POSTGRES_USER/POSTGRES_DB.
env_value() {
    local key="$1" default="$2" value=""
    value=$(grep -E "^${key}=" .env 2>/dev/null | head -1 | cut -d= -f2-)
    echo "${value:-$default}"
}

lower() { echo "$*" | tr '[:upper:]' '[:lower:]'; }

open_browser() {
    local url="$1"
    if command -v open &>/dev/null; then open "$url"          # macOS
    elif command -v xdg-open &>/dev/null; then xdg-open "$url"  # Linux
    fi
}

check_docker() {
    if ! command -v docker &>/dev/null; then
        error "Docker is not installed."
        echo ""
        echo "  Mac (recommended): https://orbstack.dev"
        echo "  Mac (alternative): https://docs.docker.com/desktop/install/mac-install/"
        echo "  Linux:             https://docs.docker.com/engine/install/"
        echo ""
        exit 1
    fi
    if ! docker info &>/dev/null 2>&1; then
        error "Docker is not running. Please start Docker Desktop (or OrbStack) and try again."
        exit 1
    fi
}

wait_healthy() {
    local service="$1" max_wait="${2:-90}" interval=3 elapsed=0
    info "Waiting for $service..."
    while [[ $elapsed -lt $max_wait ]]; do
        local health
        health=$(docker inspect --format='{{.State.Health.Status}}' "opama-${service}" 2>/dev/null || echo "missing")
        if [[ "$health" == "healthy" ]]; then
            success "$service ready"
            return 0
        fi
        sleep $interval
        elapsed=$((elapsed + interval))
        echo -n "."
    done
    echo ""
    warn "$service did not become healthy within ${max_wait}s — run: ./opama.sh logs $service"
}

# ── Commands ──────────────────────────────────────────────────────────────────

cmd_setup() {
    header "OPAMA First-Time Setup"

    if ! command -v docker &>/dev/null; then
        warn "Docker is not installed yet — install it first, then re-run setup."
        echo ""
        echo "  Mac (recommended): https://orbstack.dev"
        echo "  Mac (alternative): https://docs.docker.com/desktop/install/mac-install/"
        echo "  Linux:             https://docs.docker.com/engine/install/"
        echo ""
        exit 1
    fi

    if [[ -f .env.local ]]; then
        warn ".env.local already exists."
        read -rp "Overwrite it? [y/N] " ow
        [[ "$(lower "$ow")" != "y" ]] && { info "Keeping existing .env.local"; return; }
    fi

    echo "Enter your configuration values. Press Enter to accept defaults or skip optional fields."
    echo ""

    # Postgres password — only used container-to-container; users never type it
    # again, so auto-generating is the right default.
    read -rsp "Postgres password (press Enter to auto-generate): " pg_pass
    echo ""
    if [[ -z "$pg_pass" ]]; then
        if command -v openssl >/dev/null 2>&1; then
            pg_pass="$(openssl rand -hex 16)"
        else
            pg_pass="$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')"
        fi
        info "Generated a random Postgres password (saved in .env)."
    fi

    echo ""
    echo "Authentication: 'local' needs no external accounts (recommended for self-hosting)."
    echo "Choose 'firebase' only if you have a Firebase project for multi-tenant auth."
    read -rp "Auth provider [local/firebase] (default: local): " auth_provider
    auth_provider="$(lower "${auth_provider:-local}")"
    fb_project=""; fb_api_key=""; fb_sa_path=""; local_auth_secret=""
    if [[ "$auth_provider" == "firebase" ]]; then
        echo "Get these from your Firebase project settings."
        read -rp "Firebase Project ID (required, e.g. my-app-abc12): " fb_project
        while [[ -z "$fb_project" ]]; do
            warn "Firebase Project ID cannot be empty."
            read -rp "Firebase Project ID: " fb_project
        done
        read -rp "Firebase Web API Key (required): " fb_api_key
        while [[ -z "$fb_api_key" ]]; do
            warn "Firebase Web API Key cannot be empty."
            read -rp "Firebase Web API Key: " fb_api_key
        done
        read -rp "Firebase service account JSON path (optional — press Enter to skip): " fb_sa_path
    else
        auth_provider="local"
        if command -v openssl >/dev/null 2>&1; then
            local_auth_secret="$(openssl rand -hex 32)"
        else
            local_auth_secret="$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
        fi
        info "Generated LOCAL_AUTH_SECRET automatically."
    fi

    echo ""
    echo "AI chat & suggestions (optional — press Enter to skip):"
    echo "  openai    — hosted, needs an OpenAI API key"
    echo "  anthropic — hosted, needs an Anthropic API key"
    echo "  ollama    — free, fully local (requires Ollama: https://ollama.ai)"
    read -rp "AI provider [openai/anthropic/ollama]: " ai_provider
    ai_provider="$(lower "$ai_provider")"
    openai_key=""; anthropic_key=""
    case "$ai_provider" in
        openai)    read -rp "OpenAI API key: " openai_key ;;
        anthropic) read -rp "Anthropic API key: " anthropic_key ;;
        ollama|"") ;;
        *) warn "Unknown provider '$ai_provider' — skipping AI setup. Edit AI_PROVIDER in .env.local later."
           ai_provider="" ;;
    esac

    echo ""
    echo "Storefront website integration (optional — only needed if you connect an"
    echo "external shop site; you can configure it later, see USERGUIDE.md §7):"
    read -rp "Website export key (Enter to skip): " export_key

    echo ""
    read -rp "Ollama URL [http://host.docker.internal:11434]: " ollama_url
    ollama_url="${ollama_url:-http://host.docker.internal:11434}"

    # Write .env (Docker Compose reads this for POSTGRES_PASSWORD)
    cat > .env << EOF
POSTGRES_DB=opama_dev
POSTGRES_USER=opama_user
POSTGRES_PASSWORD=${pg_pass}
EOF

    # Write .env.local (app config)
    cat > .env.local << EOF
# OPAMA configuration — generated by ./opama.sh setup on $(date +%Y-%m-%d)
# Keep this file private. Never commit it to git.

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL=postgresql://opama_user:${pg_pass}@postgres:5432/opama_dev
POSTGRES_DB=opama_dev
POSTGRES_USER=opama_user
POSTGRES_PASSWORD=${pg_pass}

# ── Authentication ────────────────────────────────────────────────────────────
# "local" = username/password accounts, no external services needed.
# "firebase" = Firebase-backed accounts (requires the FIREBASE_* values below).
AUTH_PROVIDER=${auth_provider}
LOCAL_AUTH_SECRET=${local_auth_secret}
FIREBASE_PROJECT_ID=${fb_project}
FIREBASE_WEB_API_KEY=${fb_api_key}
FIREBASE_SERVICE_ACCOUNT_KEY=${fb_sa_path}

# ── Local AI (card grading identification) ────────────────────────────────────
# Requires Ollama installed: https://ollama.ai
OLLAMA_URL=${ollama_url}
OLLAMA_VISION_MODELS=minicpm-v:latest,llama3.2-vision:11b,llava:7b

# ── AI chat & suggestions (optional) ──────────────────────────────────────────
# Provider for /ai/chat and deck suggestions: openai | anthropic | ollama.
# Empty falls back to openai (which needs OPENAI_API_KEY set to work).
AI_PROVIDER=${ai_provider}
OPENAI_API_KEY=${openai_key}
ANTHROPIC_API_KEY=${anthropic_key}

# ── Redis ─────────────────────────────────────────────────────────────────────
REDIS_HOST=redis

# ── Storefront website integration (optional) ───────────────────────────────
WEBSITE_EXPORT_KEY=${export_key}
# Set this to your public API domain when going live (needed for image URLs)
PUBLIC_API_URL=
EOF

    echo ""
    success ".env and .env.local created."
    echo ""
    info "Next step: ./opama.sh start"
}

cmd_start() {
    check_docker
    header "Starting OPAMA"

    if [[ ! -f .env.local ]]; then
        warn ".env.local not found — running setup first."
        echo ""
        cmd_setup
        echo ""
    fi

    if [[ -z "$(docker images -q opama-backend 2>/dev/null)" ]]; then
        info "First start: building the backend image (downloads several GB of"
        info "ML dependencies). One-time only — expect 10–30 minutes."
    fi

    info "Starting containers..."
    docker compose up -d

    wait_healthy "postgres" 60
    wait_healthy "backend" 180

    echo ""
    success "OPAMA is running!"
    echo ""
    echo -e "  ${BOLD}Dashboard:${NC}  http://localhost:5173"
    echo -e "  ${BOLD}API docs:${NC}   http://localhost:6000/docs"
    echo ""

    sleep 2
    open_browser "http://localhost:5173"
}

cmd_stop() {
    check_docker
    header "Stopping OPAMA"
    docker compose down
    success "All containers stopped."
}

cmd_restart() {
    cmd_stop
    echo ""
    cmd_start
}

cmd_logs() {
    check_docker
    local service="${1:-}"
    if [[ -n "$service" ]]; then
        docker compose logs -f "$service"
    else
        docker compose logs -f
    fi
}

cmd_status() {
    check_docker
    header "OPAMA Status"

    docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || docker compose ps

    echo ""
    if curl -sf --max-time 3 http://localhost:6000/healthz &>/dev/null; then
        success "API responding at http://localhost:6000"
    else
        warn "API not responding (stopped or still starting)"
    fi

    if curl -sf --max-time 3 http://localhost:5173 &>/dev/null; then
        success "Frontend responding at http://localhost:5173"
    else
        warn "Frontend not responding"
    fi
}

cmd_backup() {
    check_docker
    header "Backing Up Database"

    local backup_dir="$SCRIPT_DIR/backups"
    mkdir -p "$backup_dir"

    local filename="opama-backup-$(date +%Y%m%d-%H%M%S).sql"
    local filepath="$backup_dir/$filename"

    info "Dumping database..."
    # --clean --if-exists makes restores work on a non-empty database
    if docker compose exec -T postgres pg_dump --clean --if-exists \
        -U "$(env_value POSTGRES_USER opama_user)" "$(env_value POSTGRES_DB opama_dev)" \
        > "$filepath" 2>/dev/null; then
        local size
        size=$(du -sh "$filepath" | cut -f1)
        success "Saved: backups/$filename ($size)"
        info "Note: uploaded images live in ./uploads/ — include that folder in your own backups."
    else
        error "Backup failed — is the postgres container running? (./opama.sh status)"
        rm -f "$filepath"
        exit 1
    fi

    # Keep only the 10 most recent backups
    local count
    count=$(ls "$backup_dir"/*.sql 2>/dev/null | wc -l | tr -d ' ')
    if [[ "$count" -gt 10 ]]; then
        info "Pruning old backups (keeping 10 most recent)..."
        ls -t "$backup_dir"/*.sql | tail -n +11 | xargs rm -f
    fi
}

cmd_restore() {
    check_docker
    local file="${1:-}"
    if [[ -z "$file" ]]; then
        echo "Available backups:"
        ls -lt backups/*.sql 2>/dev/null | awk '{print "  " $NF}' || echo "  (none)"
        echo ""
        read -rp "Enter backup filename (from backups/): " file
        file="backups/$file"
    fi

    if [[ ! -f "$file" ]]; then
        error "File not found: $file"
        exit 1
    fi

    warn "This will REPLACE the current database with $file"
    read -rp "Are you sure? [y/N] " confirm
    [[ "$(lower "$confirm")" != "y" ]] && { info "Cancelled."; return; }

    info "Restoring from $file ..."
    docker compose exec -T postgres psql \
        -U "$(env_value POSTGRES_USER opama_user)" \
        -d "$(env_value POSTGRES_DB opama_dev)" < "$file"
    success "Database restored."
}

cmd_update() {
    check_docker
    header "Updating OPAMA"

    info "Pulling latest code..."
    git pull

    info "Rebuilding backend (cached layers reused — fast unless dependencies changed)..."
    docker compose build backend

    info "Restarting services..."
    docker compose up -d --no-deps --force-recreate backend
    docker restart opama-frontend 2>/dev/null || true

    echo ""
    success "Update complete."
    echo ""
    cmd_status
}

cmd_open() {
    open_browser "http://localhost:5173"
}

cmd_seed_demo() {
    check_docker
    header "Seeding Demo Data"
    if ! command -v python3 &>/dev/null; then
        error "python3 is required for this command."
        exit 1
    fi
    python3 "$SCRIPT_DIR/scripts/seed_demo.py"
}

cmd_install_tray() {
    header "Installing OPAMA Tray"

    # Check deps
    if ! python3 -c "import gi" &>/dev/null; then
        error "python3-gi not found. Install with: sudo apt install python3-gi gir1.2-ayatanaappindicator3-0.1 python3-pil"
        exit 1
    fi

    local desktop_dir="$HOME/.config/autostart"
    mkdir -p "$desktop_dir"

    cat > "$desktop_dir/opama-tray.desktop" << EOF
[Desktop Entry]
Type=Application
Name=OPAMA Tray
Comment=OPAMA service status and controls
Exec=python3 ${SCRIPT_DIR}/opama-tray.py
Icon=${SCRIPT_DIR}/opama-logo.png
StartupNotify=false
X-GNOME-Autostart-enabled=true
EOF

    success "Autostart entry created: ~/.config/autostart/opama-tray.desktop"
    info "Starting tray now..."
    nohup python3 "$SCRIPT_DIR/opama-tray.py" &>/dev/null &
    success "Tray running. It will auto-start on next login."
}

cmd_uninstall_tray() {
    header "Removing OPAMA Tray"
    rm -f "$HOME/.config/autostart/opama-tray.desktop"
    pkill -f "opama-tray.py" 2>/dev/null || true
    success "Tray removed and stopped."
}

cmd_help() {
    echo ""
    echo -e "${BOLD}OPAMA — Open Personal Asset Management${NC}"
    echo ""
    echo "Usage: ./opama.sh <command> [args]"
    echo ""
    echo "Commands:"
    printf "  %-12s %s\n" "setup"    "First-time setup wizard — creates .env and .env.local"
    printf "  %-12s %s\n" "start"    "Start all services and open the dashboard"
    printf "  %-12s %s\n" "stop"     "Stop all services"
    printf "  %-12s %s\n" "restart"  "Stop then start"
    printf "  %-12s %s\n" "status"   "Show container status and health"
    printf "  %-12s %s\n" "logs"     "Stream logs  (e.g. ./opama.sh logs backend)"
    printf "  %-12s %s\n" "backup"   "Back up the database to ./backups/"
    printf "  %-12s %s\n" "restore"  "Restore a database backup"
    printf "  %-12s %s\n" "update"   "Pull latest code and rebuild"
    printf "  %-12s %s\n" "seed-demo" "Add a sample collection (demo account) to explore with"
    printf "  %-12s %s\n" "open"            "Open the dashboard in your browser"
    printf "  %-12s %s\n" "install-tray"   "Install system tray icon (Linux)"
    printf "  %-12s %s\n" "uninstall-tray" "Remove system tray icon"
    printf "  %-12s %s\n" "help"            "Show this message"
    echo ""
}

# ── Dispatch ──────────────────────────────────────────────────────────────────
case "${1:-help}" in
    setup)   cmd_setup ;;
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    restart) cmd_restart ;;
    logs)    cmd_logs "${2:-}" ;;
    status)  cmd_status ;;
    backup)  cmd_backup ;;
    restore) cmd_restore "${2:-}" ;;
    update)  cmd_update ;;
    seed-demo)       cmd_seed_demo ;;
    open)            cmd_open ;;
    install-tray)   cmd_install_tray ;;
    uninstall-tray) cmd_uninstall_tray ;;
    help|--help|-h) cmd_help ;;
    *)
        error "Unknown command: $1"
        cmd_help
        exit 1
        ;;
esac
