#!/usr/bin/env bash
# Stop script for Docker development environment
# Compatible with Ubuntu and modern Docker installations

set -e

cd "$(dirname "$0")/.."

echo "🛑 Stopping opama Docker services..."
echo ""

# Detect which docker compose command to use
DOCKER_COMPOSE=""
if command -v docker &> /dev/null; then
    if docker compose version &> /dev/null; then
        DOCKER_COMPOSE="docker compose"
    elif command -v docker-compose &> /dev/null; then
        DOCKER_COMPOSE="docker-compose"
    else
        echo "❌ Docker Compose not found."
        exit 1
    fi
else
    echo "❌ Docker not found."
    exit 1
fi

$DOCKER_COMPOSE -f docker-compose.dev.yml down

echo ""
echo "✅ Services stopped successfully!"
echo ""
echo "📝 Additional options:"
echo "   Remove volumes (⚠️  deletes data): $DOCKER_COMPOSE -f docker-compose.dev.yml down -v"
echo "   Remove images:                     $DOCKER_COMPOSE -f docker-compose.dev.yml down --rmi all"
echo ""
