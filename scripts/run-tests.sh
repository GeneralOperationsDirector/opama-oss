#!/bin/bash
# Test runner script for Pokémon TCG API

set -e

echo "🧪 Pokémon TCG API Test Suite"
echo "=============================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Change to project root directory
cd "$(dirname "$0")/.."

# Check if backend is running
echo "🔍 Checking if backend is running..."
if curl -s http://localhost:8008/healthz > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Backend is running${NC}"
else
    echo -e "${RED}❌ Backend is not running${NC}"
    echo ""
    echo "Please start the backend first:"
    echo "  uvicorn app.main:app --reload --port 8008"
    echo ""
    echo "Or use the start script:"
    echo "  ./start-local.sh"
    exit 1
fi

# Install test dependencies if needed
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}⚠️  No virtual environment found${NC}"
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

echo "📦 Installing test dependencies..."
pip install -q -r tests/requirements.txt

echo ""
echo "🚀 Running tests..."
echo ""

# Parse command line arguments
TEST_TYPE="${1:-all}"

case "$TEST_TYPE" in
    "quick")
        echo "Running quick tests (health & basic API)..."
        pytest tests/test_api_health.py -v
        ;;
    "cards")
        echo "Running card API tests..."
        pytest tests/test_cards_api.py -v
        ;;
    "inventory")
        echo "Running inventory API tests..."
        pytest tests/test_inventory_api.py -v
        ;;
    "decks")
        echo "Running deck API tests..."
        pytest tests/test_decks_api.py -v
        ;;
    "integration")
        echo "Running integration tests..."
        pytest tests/test_integration.py -v
        ;;
    "all")
        echo "Running all tests..."
        pytest tests/ -v
        ;;
    "coverage")
        echo "Running tests with coverage report..."
        pytest tests/ -v --cov=app --cov-report=html --cov-report=term
        echo ""
        echo "📊 Coverage report generated: htmlcov/index.html"
        ;;
    *)
        echo "Unknown test type: $TEST_TYPE"
        echo ""
        echo "Usage: $0 [test-type]"
        echo ""
        echo "Test types:"
        echo "  quick       - Run quick health checks"
        echo "  cards       - Run card API tests"
        echo "  inventory   - Run inventory API tests"
        echo "  decks       - Run deck API tests"
        echo "  integration - Run integration tests"
        echo "  all         - Run all tests (default)"
        echo "  coverage    - Run with coverage report"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}✅ Tests complete!${NC}"
