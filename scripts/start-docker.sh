#!/usr/bin/env bash
# Quick start script for Docker development environment
# Compatible with Ubuntu and modern Docker installations

set -e

cd "$(dirname "$0")/.."

echo "🐳 opama - Docker Development Setup"
echo "=========================================="
echo ""

# Detect which docker compose command to use
DOCKER_COMPOSE=""
if command -v docker &> /dev/null; then
    if docker compose version &> /dev/null; then
        DOCKER_COMPOSE="docker compose"
        echo "✅ Using Docker Compose V2 (plugin)"
    elif command -v docker-compose &> /dev/null; then
        DOCKER_COMPOSE="docker-compose"
        echo "✅ Using Docker Compose V1 (standalone)"
    else
        echo "❌ Docker Compose not found. Please install Docker Compose."
        echo "   Ubuntu: sudo apt-get update && sudo apt-get install docker-compose-plugin"
        echo "   Or: https://docs.docker.com/compose/install/"
        exit 1
    fi
else
    echo "❌ Docker not found. Please install Docker first."
    echo "   Ubuntu: curl -fsSL https://get.docker.com | sudo sh"
    echo "   Or: https://docs.docker.com/engine/install/ubuntu/"
    exit 1
fi

# Check if curl is available for health checks
if ! command -v curl &> /dev/null; then
    echo "⚠️  curl not found. Installing..."
    if command -v apt-get &> /dev/null; then
        sudo apt-get update && sudo apt-get install -y curl
    else
        echo "❌ Please install curl manually"
        exit 1
    fi
fi

# Check if .env.local exists
if [ ! -f .env.local ]; then
    echo "⚠️  .env.local not found. Creating from example..."
    if [ -f .env.local.example ]; then
        cp .env.local.example .env.local
        echo "✅ Created .env.local - Please edit it with your API keys"
        echo "   Edit: OPENAI_API_KEY, EBAY_CLIENT_ID, etc."
        exit 1
    else
        echo "❌ .env.local.example not found. Creating basic template..."
        cat > .env.local << 'EOF'
# OpenAI
OPENAI_API_KEY=sk-your-key-here

# eBay
EBAY_ENV=SANDBOX
EBAY_CLIENT_ID=
EBAY_CLIENT_SECRET=

# Ollama (if using local LLM)
OLLAMA_URL=http://host.docker.internal:11434

# Optional: Enable reranking
RERANK_ENABLED=true
RERANKER_MODEL=BAAI/bge-reranker-v2-m3
EOF
        echo "✅ Created .env.local - Please edit it with your API keys"
        exit 1
    fi
fi

# Load environment variables
export $(cat .env.local | grep -v '^#' | grep -v '^$' | xargs)

echo "📦 Building Docker images..."
$DOCKER_COMPOSE -f docker-compose.dev.yml build

echo ""
echo "🚀 Starting services..."
$DOCKER_COMPOSE -f docker-compose.dev.yml up -d

echo ""
echo "⏳ Waiting for services to be healthy..."
sleep 5

# Check if backend is healthy
echo "🏥 Checking backend health..."
for i in {1..30}; do
    if curl -sf http://localhost:8008/healthz > /dev/null 2>&1; then
        echo "✅ Backend is healthy!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ Backend health check failed. Check logs with:"
        echo "   $DOCKER_COMPOSE -f docker-compose.dev.yml logs backend"
        exit 1
    fi
    echo "   Waiting... ($i/30)"
    sleep 2
done

echo ""
echo "✅ All services started successfully!"
echo ""
echo "📊 Service Status:"
$DOCKER_COMPOSE -f docker-compose.dev.yml ps
echo ""
echo "🌐 Available endpoints:"
echo "   Backend API:  http://localhost:8008"
echo "   API Docs:     http://localhost:8008/docs"
echo "   Health Check: http://localhost:8008/healthz"
echo "   Redis:        localhost:6379"
echo ""
echo "📝 Useful commands:"
echo "   View logs:    $DOCKER_COMPOSE -f docker-compose.dev.yml logs -f"
echo "   Stop:         $DOCKER_COMPOSE -f docker-compose.dev.yml down"
echo "   Restart:      $DOCKER_COMPOSE -f docker-compose.dev.yml restart backend"
echo ""
echo "🎨 To start the frontend:"
echo "   cd opama-ui"
echo "   npm install"
echo "   npm run dev"
echo ""
echo "   Then open: http://localhost:5173"
echo ""
