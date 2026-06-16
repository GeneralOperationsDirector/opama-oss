#!/bin/bash
# SOA Infrastructure Verification Script
# ========================================
# Tests all services and endpoints

echo "======================================================================"
echo "opama - SOA Infrastructure Verification"
echo "======================================================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Test counter
PASSED=0
FAILED=0

# Test function
test_endpoint() {
    local name=$1
    local url=$2
    local expected_pattern=$3

    echo -n "Testing $name... "

    response=$(curl -sf "$url" 2>&1)
    if [ $? -eq 0 ]; then
        if [ -z "$expected_pattern" ] || echo "$response" | grep -q "$expected_pattern"; then
            echo -e "${GREEN}✓ PASS${NC}"
            ((PASSED++))
        else
            echo -e "${RED}✗ FAIL (unexpected response)${NC}"
            ((FAILED++))
        fi
    else
        echo -e "${RED}✗ FAIL (no response)${NC}"
        ((FAILED++))
    fi
}

echo "======================================================================"
echo "1. Testing Service Health Checks"
echo "======================================================================"
echo ""

test_endpoint "Gateway health" "http://localhost:8000/healthz" "OK"
test_endpoint "Catalog health" "http://localhost:8001/healthz" "healthy"
test_endpoint "Inventory health" "http://localhost:8002/healthz" "healthy"
test_endpoint "Decks health" "http://localhost:8003/healthz" "healthy"
test_endpoint "Trading health" "http://localhost:8004/healthz" "healthy"
test_endpoint "AI health" "http://localhost:8005/healthz" "healthy"
test_endpoint "Marketplace health" "http://localhost:8006/healthz" "healthy"

echo ""
echo "======================================================================"
echo "2. Testing API Gateway Routing"
echo "======================================================================"
echo ""

test_endpoint "Gateway -> Catalog (sets)" "http://localhost:8000/cards/sets" ""
test_endpoint "Gateway -> Catalog (cards)" "http://localhost:8000/cards?limit=1" ""

echo ""
echo "======================================================================"
echo "3. Testing Direct Service Endpoints"
echo "======================================================================"
echo ""

test_endpoint "Catalog: List sets" "http://localhost:8001/cards/sets" ""
test_endpoint "Catalog: List cards" "http://localhost:8001/cards?limit=1" ""

echo ""
echo "======================================================================"
echo "4. Testing Database Connectivity"
echo "======================================================================"
echo ""

# Test if we can fetch data (means DB is connected)
cards_response=$(curl -sf "http://localhost:8001/cards?limit=1" 2>&1)
if echo "$cards_response" | grep -q "id"; then
    echo -e "${GREEN}✓ Database connectivity working${NC}"
    ((PASSED++))

    # Count cards
    cards_count=$(curl -sf "http://localhost:8001/cards?limit=1000" 2>&1 | grep -o '"id"' | wc -l)
    echo "  Found $cards_count cards in database"
else
    echo -e "${RED}✗ Database connectivity issue${NC}"
    ((FAILED++))
fi

echo ""
echo "======================================================================"
echo "Test Results"
echo "======================================================================"
echo ""
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    echo ""
    echo "🎉 SOA infrastructure is working correctly!"
    echo ""
    echo "Next steps:"
    echo "  1. Start the frontend: cd opama-ui && npm run dev"
    echo "  2. Open http://localhost:5173"
    echo "  3. Browse your card collection!"
    exit 0
else
    echo -e "${RED}✗ Some tests failed${NC}"
    echo ""
    echo "Troubleshooting:"
    echo "  1. Check service logs: docker-compose logs -f"
    echo "  2. Verify all containers are running: docker-compose ps"
    echo "  3. Restart services: docker-compose restart"
    exit 1
fi
