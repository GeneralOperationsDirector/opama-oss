#!/bin/bash
# Quick start script for local development

set -e

echo "🚀 Starting Pokémon TCG App (Local Development)"
echo "================================================"

# Change to project root directory
cd "$(dirname "$0")/.."

# Check if database exists
if [ ! -f "data.db" ]; then
    echo "⚠️  Warning: data.db not found!"
    echo "You may need to import card data:"
    echo "  python scripts/import_cards.py data/"
fi

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    echo "📦 Activating virtual environment..."
    source .venv/bin/activate
fi

# Check dependencies
echo "🔍 Checking dependencies..."
python3 -c "import fastapi, uvicorn, sqlmodel" 2>/dev/null || {
    echo "⚠️  Missing dependencies! Installing..."
    pip install -r requirements.txt
}

# Kill any existing uvicorn processes
echo "🧹 Cleaning up old processes..."
pkill -f "uvicorn app.main:app" 2>/dev/null || true
sleep 1

# Clear Python bytecode cache
echo "🗑️  Clearing Python cache..."
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true

# Start backend
echo ""
echo "🔧 Starting Backend (FastAPI)..."
echo "   URL: http://localhost:8008"
echo "   Docs: http://localhost:8008/docs"
echo ""
uvicorn app.main:app --reload --port 8008 --host 0.0.0.0 &
BACKEND_PID=$!

# Wait for backend to start
echo "⏳ Waiting for backend to start..."
for i in {1..10}; do
    if curl -s http://localhost:8008/healthz >/dev/null 2>&1; then
        echo "✅ Backend is ready!"
        break
    fi
    sleep 1
    if [ $i -eq 10 ]; then
        echo "❌ Backend failed to start. Check the logs above."
        kill $BACKEND_PID 2>/dev/null || true
        exit 1
    fi
done

# Start frontend
echo ""
echo "🎨 Starting Frontend (React + Vite)..."
echo "   URL: http://localhost:5173"
echo ""
cd opama-ui

# Install frontend dependencies if needed
if [ ! -d "node_modules" ]; then
    echo "📦 Installing frontend dependencies..."
    npm install
fi

npm run dev

# Cleanup on exit
trap "echo ''; echo '🛑 Shutting down...'; kill $BACKEND_PID 2>/dev/null || true" EXIT
