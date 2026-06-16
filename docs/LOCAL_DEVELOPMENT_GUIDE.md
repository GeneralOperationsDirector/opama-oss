# Local Development Setup Guide

**Goal:** Get the Pokémon TCG app running smoothly on your local machine

---

## Quick Start (5 Minutes)

### 1. Fix Port Configuration

Your backend is running on port **8000** but frontend expects **8008**. Let's standardize on **8008**:

**Option A: Update backend port (Recommended)**

```bash
# Stop the current backend
pkill -f "uvicorn app.main:app"

# Start on port 8008 instead
cd /home/god/Desktop/pokemon/pokemon
source .venv/bin/activate  # If using venv
uvicorn app.main:app --reload --port 8008
```

**Option B: Update frontend config**

```bash
# Edit opama-ui/.env.local
# Change: VITE_API_BASE=http://localhost:8008
# To:     VITE_API_BASE=http://localhost:8000
```

### 2. Verify Services

After fixing the port, verify both services:

```bash
# Test backend
curl http://localhost:8008/healthz
# Expected: {"status":"healthy"}

# Test API
curl http://localhost:8008/cards?limit=1
# Expected: JSON array with 1 card

# Test frontend
open http://localhost:5173
# Or: xdg-open http://localhost:5173
```

---

## Current Status

✅ **What's Working:**
- Backend (uvicorn) is running
- Frontend (vite) is running
- Database exists (data.db - 8.9MB)

⚠️ **What Needs Fixing:**
- Port mismatch (8000 vs 8008)
- No .venv detected (might be running in system Python)
- Exposed API key in .env.local (security issue)

---

## Complete Setup from Scratch

If you need to restart fresh or set up on a new machine:

### Step 1: Python Backend Setup

```bash
cd /home/god/Desktop/pokemon/pokemon

# Create virtual environment (if not exists)
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env.local for local secrets
cat > .env.local << 'EOF'
# Database (SQLite for local dev)
DATABASE_URL=sqlite:///./data.db

# OpenAI (IMPORTANT: Get your own key, don't commit this file)
OPENAI_API_KEY=your-key-here

# eBay (optional)
EBAY_ENV=SANDBOX
EBAY_CLIENT_ID=
EBAY_CLIENT_SECRET=

# Redis (optional for local dev)
REDIS_HOST=localhost
REDIS_PORT=6379

# Chroma/RAG (optional)
CHROMA_PATH=var/chroma
OLLAMA_URL=http://localhost:11434
EOF

# Verify .env.local is gitignored
grep -q ".env.local" .gitignore && echo "✅ .env.local is ignored" || echo "⚠️  Add .env.local to .gitignore!"

# Start backend
uvicorn app.main:app --reload --port 8008
```

**Expected output:**
```
INFO:     Uvicorn running on http://127.0.0.1:8008 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

**Test it:**
```bash
# In another terminal
curl http://localhost:8008/healthz
curl http://localhost:8008/cards?limit=3
curl http://localhost:8008/cards/sets
```

### Step 2: React Frontend Setup

```bash
cd /home/god/Desktop/pokemon/pokemon/opama-ui

# Install dependencies (if not done)
npm install

# Create .env.local for frontend
cat > .env.local << 'EOF'
# Backend API
VITE_API_BASE=http://localhost:8008

# eBay affiliate settings (optional)
VITE_EPN_CAMPAIGN_ID=5339123026
VITE_EPN_CUSTOM_ID=optional-segment
VITE_EPN_MARKET=CA
VITE_USE_EBAY_API=0

# Image path (if using local images)
VITE_IMAGE_BASE=/img
EOF

# Start frontend dev server
npm run dev
```

**Expected output:**
```
  VITE v7.1.2  ready in 450 ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
  ➜  press h + enter to show help
```

**Open in browser:**
```bash
xdg-open http://localhost:5173
# Or manually visit: http://localhost:5173
```

---

## Development Workflow

### Daily Workflow

**Terminal 1: Backend**
```bash
cd /home/god/Desktop/pokemon/pokemon
source .venv/bin/activate
uvicorn app.main:app --reload --port 8008
```

**Terminal 2: Frontend**
```bash
cd /home/god/Desktop/pokemon/pokemon/opama-ui
npm run dev
```

**Terminal 3: Commands/Testing**
```bash
# Run scripts, test API, etc.
cd /home/god/Desktop/pokemon/pokemon
source .venv/bin/activate
python scripts/some_script.py
```

### Making Changes

**Backend changes:**
1. Edit files in `app/` directory
2. Uvicorn auto-reloads (watch the terminal)
3. Test via `curl` or browser

**Frontend changes:**
1. Edit files in `opama-ui/src/`
2. Vite hot-reloads (instant in browser)
3. Check browser console for errors

**Database changes:**
1. Edit `app/models.py`
2. Restart uvicorn (SQLModel auto-creates tables)
3. For existing tables, may need to delete `data.db` and re-import data

### Testing API Endpoints

**Using curl:**
```bash
# List cards
curl http://localhost:8008/cards?limit=5

# Get a specific card
curl http://localhost:8008/cards/sv10-1

# Get sets
curl http://localhost:8008/cards/sets

# Search cards
curl "http://localhost:8008/cards/search?q=pikachu&limit=10"

# Get user inventory (user 1)
curl http://localhost:8008/inventory/1

# Create a deck (POST request)
curl -X POST http://localhost:8008/decks \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 1,
    "name": "My Pikachu Deck",
    "format": "standard"
  }'
```

**Using the OpenAPI docs (easier):**
1. Go to http://localhost:8008/docs
2. Expand any endpoint
3. Click "Try it out"
4. Fill in parameters
5. Click "Execute"

---

## Common Issues & Solutions

### Issue 1: Port Already in Use

**Error:** `Address already in use`

**Solution:**
```bash
# Find what's using the port
sudo lsof -i :8008
# Or
sudo ss -tlnp | grep 8008

# Kill the process
kill -9 <PID>

# Or if it's uvicorn:
pkill -f uvicorn
```

### Issue 2: Module Not Found

**Error:** `ModuleNotFoundError: No module named 'fastapi'`

**Solution:**
```bash
# Make sure you're in the virtual environment
source .venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt

# Verify installation
pip list | grep fastapi
```

### Issue 3: Database Locked

**Error:** `database is locked`

**Solution:**
```bash
# Stop all processes using the database
pkill -f uvicorn

# Check for WAL files
ls -la data.db*

# Remove WAL files if safe (backup first!)
cp data.db data.db.backup
rm data.db-wal data.db-shm

# Restart backend
uvicorn app.main:app --reload --port 8008
```

### Issue 4: Frontend Can't Connect to Backend

**Error:** Network error, CORS error, or 404

**Check:**
1. Backend is running: `curl http://localhost:8008/healthz`
2. Port matches: Check `opama-ui/.env.local` → `VITE_API_BASE`
3. CORS is configured: Check `app/main.py` allows `http://localhost:5173`

**Fix CORS (if needed):**
```python
# app/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Frontend dev server
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Issue 5: No Cards in Database

**Error:** API returns empty arrays

**Solution:**
```bash
# Import card data
cd /home/god/Desktop/pokemon/pokemon
source .venv/bin/activate
python scripts/import_cards.py data/

# Check database
sqlite3 data.db "SELECT COUNT(*) FROM card;"
sqlite3 data.db "SELECT COUNT(*) FROM set;"
```

### Issue 6: Frontend Shows "Cannot read property..."

**Error:** React errors about undefined properties

**Check:**
1. Backend is returning data: `curl http://localhost:8008/cards?limit=1`
2. API client is configured: Check `opama-ui/src/lib/api.ts`
3. Browser console for detailed errors

**Debug:**
```typescript
// Add console.log to api.ts
export async function api<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${endpoint}`
  console.log('API Request:', url)
  const response = await fetch(url, options)
  const data = await response.json()
  console.log('API Response:', data)
  return data
}
```

---

## Optional Services

### Redis (for caching, Celery)

**Install:**
```bash
# Ubuntu/Debian
sudo apt install redis-server

# macOS
brew install redis

# Start
redis-server

# Or as service
sudo systemctl start redis
```

**Test:**
```bash
redis-cli ping
# Expected: PONG
```

### PostgreSQL (for production-like setup)

**Install:**
```bash
# Ubuntu/Debian
sudo apt install postgresql

# macOS
brew install postgresql
```

**Setup:**
```bash
# Create database
sudo -u postgres createdb pokemon_tcg
sudo -u postgres createuser pokemon_user
sudo -u postgres psql -c "ALTER USER pokemon_user WITH PASSWORD 'pokemon_pass';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE pokemon_tcg TO pokemon_user;"

# Update .env.local
# DATABASE_URL=postgresql://pokemon_user:pokemon_pass@localhost:5432/pokemon_tcg
```

### Ollama (for local AI embeddings)

**Install:**
```bash
# Download from https://ollama.ai/download
# Or:
curl -fsSL https://ollama.ai/install.sh | sh

# Pull model
ollama pull llama3.1:8b-instruct
ollama pull nomic-embed-text

# Start server (runs automatically as service)
ollama serve
```

**Test:**
```bash
curl http://localhost:11434/api/tags
```

---

## Project Structure Quick Reference

```
pokemon/
├── app/                          # Backend (FastAPI)
│   ├── main.py                  # Entry point, CORS, middleware
│   ├── database.py              # DB session management
│   ├── models.py                # SQLModel schemas
│   ├── routers/                 # API endpoints
│   │   ├── cards.py             # /cards endpoints
│   │   ├── inventory.py         # /inventory endpoints
│   │   ├── decks.py             # /decks endpoints
│   │   └── ...
│   ├── services/                # Business logic
│   └── ai/                      # RAG pipeline
├── opama-ui/                   # Frontend (React)
│   ├── src/
│   │   ├── OpamaApp.tsx       # Main app component
│   │   ├── features/            # Feature modules
│   │   │   ├── catalog/         # Card browsing
│   │   │   ├── inventory/       # Inventory management
│   │   │   ├── decks/           # Deck building
│   │   │   └── ...
│   │   ├── shared/              # Reusable components
│   │   └── lib/                 # Utilities
│   │       ├── api.ts           # API client
│   │       └── images.ts        # Image URL helpers
│   └── package.json
├── data.db                       # SQLite database
├── requirements.txt              # Python dependencies
└── .env.local                    # Local secrets (not committed)
```

---

## Environment Variables Reference

### Backend (.env.local)

```bash
# Database
DATABASE_URL=sqlite:///./data.db  # Local SQLite
# DATABASE_URL=postgresql://user:pass@localhost:5432/pokemon_tcg  # PostgreSQL

# OpenAI (for AI features)
OPENAI_API_KEY=sk-proj-...  # Get from https://platform.openai.com/api-keys

# eBay (optional)
EBAY_ENV=SANDBOX
EBAY_CLIENT_ID=
EBAY_CLIENT_SECRET=

# Redis (optional)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# Chroma/RAG (optional)
CHROMA_PATH=var/chroma
OLLAMA_URL=http://localhost:11434
OLLAMA_COMPRESS_MODEL=llama3.1:8b-instruct
RERANK_ENABLED=true
```

### Frontend (opama-ui/.env.local)

```bash
# Backend API URL
VITE_API_BASE=http://localhost:8008

# eBay affiliate (optional)
VITE_EPN_CAMPAIGN_ID=5339123026
VITE_EPN_CUSTOM_ID=optional-segment
VITE_EPN_MARKET=CA
VITE_USE_EBAY_API=0

# Images (if serving locally)
VITE_IMAGE_BASE=/img
```

---

## Useful Commands Cheatsheet

```bash
# Backend
uvicorn app.main:app --reload --port 8008           # Start dev server
pkill -f uvicorn                                     # Stop server
pip freeze > requirements.txt                        # Update dependencies
python scripts/import_cards.py data/                # Import card data
sqlite3 data.db "SELECT COUNT(*) FROM card;"        # Count cards

# Frontend
npm run dev                                          # Start dev server
npm run build                                        # Production build
npm run lint                                         # Lint code
npm run preview                                      # Preview production build

# Database
sqlite3 data.db                                      # Open SQLite CLI
sqlite3 data.db .schema                             # Show schema
sqlite3 data.db "SELECT * FROM set LIMIT 10;"       # Query sets
sqlite3 data.db ".backup data.db.backup"            # Backup database

# Git
git status                                           # Check status
git diff                                             # See changes
git add .                                            # Stage all changes
git commit -m "Description"                          # Commit
git push                                             # Push to remote

# Logs/Debugging
tail -f logs/app.log                                # Watch logs (if logging to file)
journalctl -f -u uvicorn                            # Watch systemd logs
```

---

## Next Steps

Once you have the app running locally:

1. **Play with it!** Add cards to inventory, build decks, try features
2. **Fix the API key issue** - rotate your OpenAI key (see PROJECT_REVIEW_AND_RECOMMENDATIONS.md)
3. **Add authentication** - see FIREBASE_AUTH_INTEGRATION.md
4. **Write tests** - start with critical paths
5. **Set up CI/CD** - automate testing and deployment

---

## Getting Help

**Check logs:**
- Backend: Watch the terminal running uvicorn
- Frontend: Browser console (F12 → Console)
- Database: `sqlite3 data.db` for direct queries

**Common log locations:**
- Uvicorn: stdout/stderr (terminal)
- Vite: stdout/stderr (terminal)
- Browser: F12 → Console, Network tab

**Documentation:**
- FastAPI: https://fastapi.tiangolo.com/
- React: https://react.dev/
- SQLModel: https://sqlmodel.tiangolo.com/
- Vite: https://vite.dev/

**OpenAPI Docs (when backend is running):**
- http://localhost:8008/docs (Swagger UI)
- http://localhost:8008/redoc (ReDoc)

---

## Summary

**To get running right now:**

```bash
# Terminal 1: Backend
cd /home/god/Desktop/pokemon/pokemon
source .venv/bin/activate  # If you have a venv
uvicorn app.main:app --reload --port 8008

# Terminal 2: Frontend
cd /home/god/Desktop/pokemon/pokemon/opama-ui
npm run dev

# Browser
# Visit: http://localhost:5173
```

**Verify it works:**
1. Frontend loads in browser
2. You can browse cards
3. You can add cards to inventory
4. You can create decks

**If anything doesn't work, check this guide's "Common Issues" section.**
