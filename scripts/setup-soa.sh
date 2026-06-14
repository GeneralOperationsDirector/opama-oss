#!/bin/bash
# SOA Infrastructure Setup Script
# ================================
# This script sets up the complete SOA infrastructure

set -e  # Exit on error

cd "$(dirname "$0")/.."

echo "======================================================================"
echo "opama - SOA Infrastructure Setup"
echo "======================================================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check prerequisites
echo "📋 Checking prerequisites..."
echo ""

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}✗ Docker not found${NC}"
    echo "  Please install Docker: https://docs.docker.com/get-docker/"
    exit 1
fi
echo -e "${GREEN}✓ Docker installed${NC}"

# Check Docker Compose
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}✗ Docker Compose not found${NC}"
    echo "  Please install Docker Compose"
    exit 1
fi
echo -e "${GREEN}✓ Docker Compose installed${NC}"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗ Python 3 not found${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python 3 installed${NC}"

# Check SQLite database exists
if [ ! -f "data.db" ]; then
    echo -e "${RED}✗ data.db not found${NC}"
    echo "  Please ensure your SQLite database exists at ./data.db"
    exit 1
fi
echo -e "${GREEN}✓ SQLite database found ($(du -h data.db | cut -f1))${NC}"

echo ""
echo "======================================================================"
echo "Step 1: Starting PostgreSQL and Redis"
echo "======================================================================"
echo ""

# Start infrastructure services
echo "Starting PostgreSQL and Redis containers..."
docker-compose up -d postgres redis

echo ""
echo "Waiting for services to be healthy (30 seconds)..."
sleep 5

# Check if services are running
for i in {1..25}; do
    if docker-compose ps postgres | grep -q "healthy"; then
        echo -e "${GREEN}✓ PostgreSQL is healthy${NC}"
        break
    fi
    echo -n "."
    sleep 1
done

echo ""
for i in {1..25}; do
    if docker-compose ps redis | grep -q "healthy"; then
        echo -e "${GREEN}✓ Redis is healthy${NC}"
        break
    fi
    echo -n "."
    sleep 1
done

echo ""
echo "======================================================================"
echo "Step 2: Running Database Migration (SQLite → PostgreSQL)"
echo "======================================================================"
echo ""

# Set database URL for migration
export DATABASE_URL="postgresql://opama_user:opama_pass@localhost:5433/opama_dev"

echo "Migrating data from SQLite to PostgreSQL..."
echo ""

python3 scripts/migrate_to_postgres.py

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✓ Migration completed successfully!${NC}"
else
    echo ""
    echo -e "${RED}✗ Migration failed${NC}"
    echo "  Check the error messages above"
    exit 1
fi

echo ""
echo "======================================================================"
echo "Step 3: Starting All Microservices"
echo "======================================================================"
echo ""

echo "Starting all SOA services..."
docker-compose up -d

echo ""
echo "Waiting for services to start (10 seconds)..."
sleep 10

echo ""
echo "======================================================================"
echo "Step 4: Checking Service Health"
echo "======================================================================"
echo ""

# Function to check service health
check_health() {
    local service_name=$1
    local port=$2

    if curl -sf http://localhost:$port/healthz > /dev/null 2>&1; then
        echo -e "${GREEN}✓ $service_name (port $port)${NC}"
        return 0
    else
        echo -e "${RED}✗ $service_name (port $port) - not responding${NC}"
        return 1
    fi
}

echo "Checking service health endpoints..."
echo ""

check_health "API Gateway" 8000
check_health "Catalog Service" 8001
check_health "Inventory Service" 8002
check_health "Decks Service" 8003
check_health "Trading Service" 8004
check_health "AI Service" 8005
check_health "Marketplace Service" 8006

echo ""
echo "======================================================================"
echo "Setup Complete!"
echo "======================================================================"
echo ""
echo -e "${GREEN}✓ PostgreSQL running on port 5432${NC}"
echo -e "${GREEN}✓ Redis running on port 6379${NC}"
echo -e "${GREEN}✓ API Gateway running on port 8000${NC}"
echo -e "${GREEN}✓ 6 Microservices running (ports 8001-8006)${NC}"
echo ""
echo "📖 API Documentation:"
echo "  Gateway:      http://localhost:8000/healthz"
echo "  Catalog:      http://localhost:8001/docs"
echo "  Inventory:    http://localhost:8002/docs"
echo "  Decks:        http://localhost:8003/docs"
echo "  Trading:      http://localhost:8004/docs"
echo "  AI:           http://localhost:8005/docs"
echo "  Marketplace:  http://localhost:8006/docs"
echo ""
echo "🚀 Next Steps:"
echo "  1. Update frontend to use API Gateway"
echo "     - Edit opama-ui/.env.local"
echo "     - Set: VITE_API_BASE=http://localhost:8000"
echo ""
echo "  2. Start frontend:"
echo "     cd opama-ui"
echo "     npm run dev"
echo ""
echo "  3. View logs:"
echo "     docker-compose logs -f"
echo ""
echo "  4. Stop all services:"
echo "     docker-compose down"
echo ""
echo "======================================================================"
