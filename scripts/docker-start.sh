#!/bin/bash
# Quick start script for opama Docker deployment

set -e

cd "$(dirname "$0")/.."

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Pokémon TCG Application - Docker Start  ║${NC}"
echo -e "${BLUE}╔════════════════════════════════════════════╗${NC}"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}⚠️  Warning: .env file not found${NC}"
    echo -e "Creating .env from .env.docker.example..."
    cp .env.docker.example .env
    echo -e "${YELLOW}⚠️  Please edit .env with your API keys before continuing!${NC}"
    echo ""
    read -p "Press Enter to continue (after editing .env) or Ctrl+C to exit..."
fi

# Ask for deployment mode
echo -e "${GREEN}Select deployment mode:${NC}"
echo "  1) Development (Monolith + Frontend with hot-reload)"
echo "  2) Production (6 Microservices + API Gateway + Frontend)"
echo "  3) Infrastructure only (PostgreSQL + Redis)"
echo ""
read -p "Enter choice (1-3): " choice

case $choice in
    1)
        MODE="dev"
        echo -e "\n${GREEN}Starting Development Mode...${NC}\n"
        ;;
    2)
        MODE="prod"
        echo -e "\n${GREEN}Starting Production Mode...${NC}\n"
        ;;
    3)
        MODE="infrastructure"
        echo -e "\n${GREEN}Starting Infrastructure Only...${NC}\n"
        ;;
    *)
        echo -e "${YELLOW}Invalid choice. Defaulting to Development Mode.${NC}"
        MODE="dev"
        ;;
esac

# Check if running in detached mode
echo ""
read -p "Run in background (detached mode)? (y/N): " detached

if [[ $detached == "y" || $detached == "Y" ]]; then
    DETACHED_FLAG="-d"
    echo -e "${GREEN}Running in detached mode...${NC}"
else
    DETACHED_FLAG=""
    echo -e "${GREEN}Running in foreground (Ctrl+C to stop)...${NC}"
fi

echo ""

# Start Docker Compose
if [ "$MODE" == "infrastructure" ]; then
    docker compose up $DETACHED_FLAG postgres redis
else
    docker compose --profile $MODE up $DETACHED_FLAG
fi

# Show access info if detached
if [[ $detached == "y" || $detached == "Y" ]]; then
    echo ""
    echo -e "${GREEN}✅ Services started successfully!${NC}"
    echo ""
    if [ "$MODE" == "dev" ]; then
        echo -e "${BLUE}Access Points:${NC}"
        echo "  • Frontend: http://localhost:5173"
        echo "  • Backend API: http://localhost:8008"
        echo "  • API Docs: http://localhost:8008/docs"
        echo "  • PostgreSQL: localhost:5433"
        echo "  • Redis: localhost:6379"
    elif [ "$MODE" == "prod" ]; then
        echo -e "${BLUE}Access Points:${NC}"
        echo "  • Frontend: http://localhost:80"
        echo "  • API Gateway: http://localhost:8000"
        echo "  • Services: http://localhost:8001-8006"
        echo "  • PostgreSQL: localhost:5433"
        echo "  • Redis: localhost:6379"
    fi
    echo ""
    echo -e "${BLUE}Useful commands:${NC}"
    echo "  • View logs: docker compose logs -f"
    echo "  • Stop services: docker compose down"
    echo "  • View status: docker compose ps"
    echo ""
fi
