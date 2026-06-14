# opama.ps1 — Windows launcher for OPAMA
# Usage: .\opama.ps1 [command] [args]
# Requires: PowerShell 5.1+ and Docker Desktop

param(
    [string]$Command = "help",
    [string]$Arg = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# ── Helpers ───────────────────────────────────────────────────────────────────
function Info($msg)    { Write-Host "-> $msg" -ForegroundColor Cyan }
function Success($msg) { Write-Host "OK $msg" -ForegroundColor Green }
function Warn($msg)    { Write-Host "!  $msg" -ForegroundColor Yellow }
function Err($msg)     { Write-Host "X  $msg" -ForegroundColor Red }
function Header($msg)  { Write-Host "`n== $msg ==`n" -ForegroundColor Blue }

function Open-Browser($url) { Start-Process $url }

# Read KEY from .env, falling back to a default — keeps backup/restore working
# when someone customises POSTGRES_USER/POSTGRES_DB.
function Env-Value($key, $default) {
    if (Test-Path ".env") {
        $line = Select-String -Path ".env" -Pattern "^$key=" | Select-Object -First 1
        if ($line) {
            $value = $line.Line.Substring($key.Length + 1)
            if ($value) { return $value }
        }
    }
    return $default
}

function Check-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Err "Docker is not installed."
        Write-Host "  Download Docker Desktop: https://docs.docker.com/desktop/install/windows-install/"
        exit 1
    }
    try {
        docker info 2>&1 | Out-Null
    } catch {
        Err "Docker is not running. Please start Docker Desktop."
        exit 1
    }
}

function Wait-Healthy($service, $maxWait = 90) {
    Info "Waiting for $service..."
    $elapsed = 0
    while ($elapsed -lt $maxWait) {
        try {
            $health = docker inspect --format='{{.State.Health.Status}}' "opama-$service" 2>$null
            if ($health -eq "healthy") { Success "$service ready"; return }
        } catch {}
        Start-Sleep 3
        $elapsed += 3
        Write-Host -NoNewline "."
    }
    Write-Host ""
    Warn "$service did not become healthy in ${maxWait}s — run: .\opama.ps1 logs $service"
}

# ── Commands ──────────────────────────────────────────────────────────────────

function Cmd-Setup {
    Header "OPAMA First-Time Setup"

    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Warn "Docker is not installed yet. Install Docker Desktop first:"
        Write-Host "  https://docs.docker.com/desktop/install/windows-install/"
        exit 1
    }

    if (Test-Path ".env.local") {
        $ow = Read-Host ".env.local already exists. Overwrite? [y/N]"
        if ($ow -ne "y") { Info "Keeping existing .env.local"; return }
    }

    Write-Host "Enter your configuration values. Press Enter to skip optional fields."
    Write-Host ""

    # Postgres password — only used container-to-container; users never type it
    # again, so auto-generating is the right default.
    $pgPass = Read-Host "Postgres password (press Enter to auto-generate)"
    if (-not $pgPass) {
        $bytes = New-Object byte[] 16
        [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
        $pgPass = ($bytes | ForEach-Object { $_.ToString("x2") }) -join ""
        Info "Generated a random Postgres password (saved in .env)."
    }

    Write-Host ""
    Write-Host "Authentication: 'local' needs no external accounts (recommended for self-hosting)."
    Write-Host "Choose 'firebase' only if you have a Firebase project for multi-tenant auth."
    $authProvider = Read-Host "Auth provider [local/firebase] (default: local)"
    if (-not $authProvider) { $authProvider = "local" }
    $fbProject = ""; $fbApiKey = ""; $fbSaPath = ""; $localAuthSecret = ""
    if ($authProvider -eq "firebase") {
        Write-Host "Firebase credentials — find these in your Firebase project settings."
        while (-not $fbProject) { $fbProject = Read-Host "Firebase Project ID (required)" }
        while (-not $fbApiKey) { $fbApiKey = Read-Host "Firebase Web API Key (required)" }
        $fbSaPath = Read-Host "Firebase service account JSON path (optional)"
    } else {
        $authProvider = "local"
        $bytes = New-Object byte[] 32
        [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
        $localAuthSecret = ($bytes | ForEach-Object { $_.ToString("x2") }) -join ""
        Info "Generated LOCAL_AUTH_SECRET automatically."
    }

    Write-Host ""
    Write-Host "AI chat & suggestions (optional — press Enter to skip):"
    Write-Host "  openai    — hosted, needs an OpenAI API key"
    Write-Host "  anthropic — hosted, needs an Anthropic API key"
    Write-Host "  ollama    — free, fully local (requires Ollama: https://ollama.ai)"
    $aiProvider = (Read-Host "AI provider [openai/anthropic/ollama]").ToLower()
    $openaiKey = ""; $anthropicKey = ""
    switch ($aiProvider) {
        "openai"    { $openaiKey = Read-Host "OpenAI API key" }
        "anthropic" { $anthropicKey = Read-Host "Anthropic API key" }
        "ollama"    { }
        ""          { }
        default     {
            Warn "Unknown provider '$aiProvider' — skipping AI setup. Edit AI_PROVIDER in .env.local later."
            $aiProvider = ""
        }
    }

    Write-Host ""
    Write-Host "Storefront website integration (optional — only needed if you connect an"
    Write-Host "external shop site; you can configure it later, see USERGUIDE.md section 7):"
    $exportKey = Read-Host "Website export key (Enter to skip)"

    Write-Host ""
    $ollamaUrl = Read-Host "Ollama URL [http://host.docker.internal:11434]"
    if (-not $ollamaUrl) { $ollamaUrl = "http://host.docker.internal:11434" }

    $date = Get-Date -Format "yyyy-MM-dd"

    @"
POSTGRES_DB=opama_dev
POSTGRES_USER=opama_user
POSTGRES_PASSWORD=$pgPass
"@ | Set-Content ".env" -Encoding UTF8

    @"
# OPAMA configuration — generated by .\opama.ps1 setup on $date
# Keep this file private. Never commit it to git.

# Database
DATABASE_URL=postgresql://opama_user:${pgPass}@postgres:5432/opama_dev
POSTGRES_DB=opama_dev
POSTGRES_USER=opama_user
POSTGRES_PASSWORD=$pgPass

# Authentication ("local" = no external services; "firebase" = Firebase-backed)
AUTH_PROVIDER=$authProvider
LOCAL_AUTH_SECRET=$localAuthSecret
FIREBASE_PROJECT_ID=$fbProject
FIREBASE_WEB_API_KEY=$fbApiKey
FIREBASE_SERVICE_ACCOUNT_KEY=$fbSaPath

# Local AI (card grading — requires Ollama: https://ollama.ai)
OLLAMA_URL=$ollamaUrl
OLLAMA_VISION_MODELS=minicpm-v:latest,llama3.2-vision:11b,llava:7b

# AI chat & suggestions (optional): openai | anthropic | ollama.
# Empty falls back to openai (which needs OPENAI_API_KEY set to work).
AI_PROVIDER=$aiProvider
OPENAI_API_KEY=$openaiKey
ANTHROPIC_API_KEY=$anthropicKey

# Redis
REDIS_HOST=redis

# Storefront website integration (optional)
WEBSITE_EXPORT_KEY=$exportKey
PUBLIC_API_URL=
"@ | Set-Content ".env.local" -Encoding UTF8

    Write-Host ""
    Success ".env and .env.local created."
    Write-Host ""
    Info "Next step: .\opama.ps1 start"
}

function Cmd-Start {
    Check-Docker
    Header "Starting OPAMA"

    if (-not (Test-Path ".env.local")) {
        Warn ".env.local not found — running setup first."
        Write-Host ""
        Cmd-Setup
        Write-Host ""
    }

    if (-not (docker images -q opama-backend 2>$null)) {
        Info "First start: building the backend image (downloads several GB of"
        Info "ML dependencies). One-time only — expect 10-30 minutes."
    }

    Info "Starting containers..."
    docker compose up -d

    Wait-Healthy "postgres" 60
    Wait-Healthy "backend" 180

    Write-Host ""
    Success "OPAMA is running!"
    Write-Host ""
    Write-Host "  Dashboard: http://localhost:5173"
    Write-Host "  API docs:  http://localhost:6000/docs"
    Write-Host ""

    Start-Sleep 2
    Open-Browser "http://localhost:5173"
}

function Cmd-Stop {
    Check-Docker
    Header "Stopping OPAMA"
    docker compose down
    Success "All containers stopped."
}

function Cmd-Logs {
    Check-Docker
    if ($Arg) { docker compose logs -f $Arg }
    else { docker compose logs -f }
}

function Cmd-Status {
    Check-Docker
    Header "OPAMA Status"
    docker compose ps
    Write-Host ""
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:6000/healthz" -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) { Success "API responding at http://localhost:6000" }
    } catch { Warn "API not responding (stopped or still starting)" }
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:5173" -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) { Success "Frontend responding at http://localhost:5173" }
    } catch { Warn "Frontend not responding" }
}

function Cmd-Backup {
    Check-Docker
    Header "Backing Up Database"

    $backupDir = Join-Path $ScriptDir "backups"
    if (-not (Test-Path $backupDir)) { New-Item -ItemType Directory $backupDir | Out-Null }

    $filename = "opama-backup-$(Get-Date -Format 'yyyyMMdd-HHmmss').sql"
    $filepath = Join-Path $backupDir $filename

    $pgUser = Env-Value "POSTGRES_USER" "opama_user"
    $pgDb = Env-Value "POSTGRES_DB" "opama_dev"

    Info "Dumping database..."
    # cmd /c redirection writes raw bytes — PowerShell pipelines would add a
    # UTF-8 BOM and re-encode the dump, which breaks psql on restore.
    # --clean --if-exists makes restores work on a non-empty database.
    cmd /c "docker compose exec -T postgres pg_dump --clean --if-exists -U $pgUser $pgDb > `"$filepath`""
    if ($LASTEXITCODE -eq 0 -and (Get-Item $filepath -ErrorAction SilentlyContinue).Length -gt 0) {
        $size = [math]::Round((Get-Item $filepath).Length / 1KB, 1)
        Success "Saved: backups\$filename ($size KB)"
        Info "Note: uploaded images live in .\uploads\ — include that folder in your own backups."
    } else {
        Err "Backup failed — is postgres running? (.\opama.ps1 status)"
        Remove-Item $filepath -ErrorAction SilentlyContinue
        exit 1
    }

    # Keep 10 most recent
    $files = Get-ChildItem "$backupDir\*.sql" | Sort-Object LastWriteTime -Descending
    if ($files.Count -gt 10) {
        Info "Pruning old backups (keeping 10 most recent)..."
        $files | Select-Object -Skip 10 | Remove-Item
    }
}

function Cmd-Restore {
    Check-Docker
    $file = $Arg
    if (-not $file) {
        Write-Host "Available backups:"
        Get-ChildItem "backups\*.sql" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            ForEach-Object { Write-Host "  $($_.Name)" }
        Write-Host ""
        $file = Read-Host "Enter backup filename (from backups\)"
        $file = "backups\$file"
    }
    if (-not (Test-Path $file)) { Err "File not found: $file"; exit 1 }

    Warn "This will REPLACE the current database with $file"
    $confirm = Read-Host "Are you sure? [y/N]"
    if ($confirm -ne "y") { Info "Cancelled."; return }

    Info "Restoring from $file ..."
    $pgUser = Env-Value "POSTGRES_USER" "opama_user"
    $pgDb = Env-Value "POSTGRES_DB" "opama_dev"
    cmd /c "docker compose exec -T postgres psql -U $pgUser -d $pgDb < `"$file`""
    Success "Database restored."
}

function Cmd-Update {
    Check-Docker
    Header "Updating OPAMA"
    Info "Pulling latest code..."
    git pull
    Info "Rebuilding backend (cached layers reused — fast unless dependencies changed)..."
    docker compose build backend
    Info "Restarting services..."
    docker compose up -d --no-deps --force-recreate backend
    docker restart opama-frontend 2>$null
    Write-Host ""
    Success "Update complete."
    Write-Host ""
    Cmd-Status
}

function Cmd-SeedDemo {
    Check-Docker
    Header "Seeding Demo Data"
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { $python = Get-Command py -ErrorAction SilentlyContinue }
    if (-not $python) {
        Err "Python 3 is required for this command: https://www.python.org/downloads/"
        exit 1
    }
    & $python.Source (Join-Path $ScriptDir "scripts\seed_demo.py")
}

function Cmd-Help {
    Write-Host ""
    Write-Host "OPAMA -- Open Personal Asset Management" -ForegroundColor Blue
    Write-Host ""
    Write-Host "Usage: .\opama.ps1 <command> [args]"
    Write-Host ""
    Write-Host "Commands:"
    @(
        "  setup       First-time setup wizard -- creates .env and .env.local",
        "  start       Start all services and open the dashboard",
        "  stop        Stop all services",
        "  restart     Stop then start",
        "  status      Show container status and health",
        "  logs        Stream logs  (e.g. .\opama.ps1 logs backend)",
        "  backup      Back up the database to .\backups\",
        "  restore     Restore a database backup",
        "  update      Pull latest code and rebuild",
        "  seed-demo   Add a sample collection (demo account) to explore with",
        "  open        Open the dashboard in your browser",
        "  help        Show this message"
    ) | ForEach-Object { Write-Host $_ }
    Write-Host ""
}

# ── Dispatch ──────────────────────────────────────────────────────────────────
switch ($Command) {
    "setup"   { Cmd-Setup }
    "start"   { Cmd-Start }
    "stop"    { Cmd-Stop }
    "restart" { Cmd-Stop; Start-Sleep 1; Cmd-Start }
    "logs"    { Cmd-Logs }
    "status"  { Cmd-Status }
    "backup"  { Cmd-Backup }
    "restore" { Cmd-Restore }
    "update"  { Cmd-Update }
    "seed-demo" { Cmd-SeedDemo }
    "open"    { Open-Browser "http://localhost:5173" }
    "help"    { Cmd-Help }
    default   { Err "Unknown command: $Command"; Cmd-Help; exit 1 }
}
