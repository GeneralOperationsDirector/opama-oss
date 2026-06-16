# Testing Guide - Pokémon TCG API

Comprehensive guide for testing your local services.

---

## 🚀 Quick Start

### Prerequisites

Make sure your backend is running:

```bash
# In one terminal
uvicorn app.main:app --reload --port 8008

# Or use the start script
./start-local.sh
```

### Run All Tests

```bash
./run-tests.sh
```

That's it! The script will:
1. Check if backend is running
2. Install test dependencies
3. Run all tests
4. Show results

---

## 📋 Test Suites

### 1. Health & Basic API Tests (`test_api_health.py`)

**What it tests:**
- API is accessible
- Health endpoint works
- API documentation is available
- CORS headers are correct
- Response times are reasonable

**Run:**
```bash
./run-tests.sh quick
# Or directly:
pytest tests/test_api_health.py -v
```

**Example output:**
```
✅ test_health_endpoint - PASSED
✅ test_api_docs_available - PASSED
✅ test_openapi_json - PASSED
✅ test_cors_headers - PASSED
✅ test_health_check_performance - PASSED
```

---

### 2. Cards API Tests (`test_cards_api.py`)

**What it tests:**
- Listing cards
- Getting specific cards
- Searching cards
- Listing sets
- Filtering by set
- Data integrity

**Run:**
```bash
./run-tests.sh cards
# Or:
pytest tests/test_cards_api.py -v
```

**Test coverage:**
- ✅ `GET /cards` - List cards with pagination
- ✅ `GET /cards/{card_id}` - Get specific card
- ✅ `GET /cards/search` - Search functionality
- ✅ `GET /cards/sets` - List all sets
- ✅ Data validation and error handling

---

### 3. Inventory API Tests (`test_inventory_api.py`)

**What it tests:**
- Getting user inventory
- Adding items to inventory
- Inventory with card details
- CSV export
- Validation and errors

**Run:**
```bash
./run-tests.sh inventory
# Or:
pytest tests/test_inventory_api.py -v
```

**Test coverage:**
- ✅ `GET /inventory/{user_id}` - Get inventory
- ✅ `GET /inventory/{user_id}/with_cards` - Inventory with card data
- ✅ `POST /inventory` - Add inventory items
- ✅ `GET /inventory/{user_id}/export.csv` - CSV export
- ✅ Validation (invalid cards, missing fields)

---

### 4. Decks API Tests (`test_decks_api.py`)

**What it tests:**
- Creating decks
- Listing user decks
- Getting deck details
- Adding cards to decks
- Validation

**Run:**
```bash
./run-tests.sh decks
# Or:
pytest tests/test_decks_api.py -v
```

**Test coverage:**
- ✅ `GET /decks?user_id={id}` - List user decks
- ✅ `POST /decks` - Create deck
- ✅ `GET /decks/{deck_id}` - Get deck with cards
- ✅ `POST /decks/{deck_id}/cards` - Add cards
- ✅ Validation (missing fields, invalid IDs)

---

### 5. Integration Tests (`test_integration.py`)

**What it tests:**
- Complete user workflows
- Multi-step operations
- Data consistency across endpoints
- Real-world usage scenarios

**Run:**
```bash
./run-tests.sh integration
# Or:
pytest tests/test_integration.py -v
```

**Workflows tested:**
- ✅ Browse cards → Add to inventory → Verify
- ✅ Create deck → Add cards → Verify
- ✅ Search cards → Filter by set → Get details
- ✅ Data consistency (inventory/deck references valid cards)

---

## 🛠️ Test Commands

### Basic Commands

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_cards_api.py -v

# Run specific test
pytest tests/test_cards_api.py::TestCardsEndpoints::test_list_cards -v

# Run tests matching pattern
pytest tests/ -k "card" -v
```

### Advanced Commands

```bash
# Run tests in parallel (faster)
pytest tests/ -n auto

# Stop on first failure
pytest tests/ -x

# Show local variables on failure
pytest tests/ -l

# Run only failed tests from last run
pytest --lf

# Generate coverage report
pytest tests/ --cov=app --cov-report=html
```

### Using the Test Runner Script

```bash
# Quick health checks
./run-tests.sh quick

# Specific test suite
./run-tests.sh cards
./run-tests.sh inventory
./run-tests.sh decks
./run-tests.sh integration

# All tests
./run-tests.sh all

# With coverage report
./run-tests.sh coverage
```

---

## 📊 Coverage Reports

### Generate HTML Coverage Report

```bash
pytest tests/ --cov=app --cov-report=html
```

Then open `htmlcov/index.html` in your browser:

```bash
xdg-open htmlcov/index.html
```

### Coverage in Terminal

```bash
pytest tests/ --cov=app --cov-report=term
```

**Target coverage:** >80% for production

---

## 🎯 Test Organization

```
tests/
├── conftest.py              # Pytest configuration & fixtures
├── requirements.txt         # Test dependencies
├── test_api_health.py       # Health & performance tests
├── test_cards_api.py        # Card endpoints tests
├── test_inventory_api.py    # Inventory endpoints tests
├── test_decks_api.py        # Deck endpoints tests
└── test_integration.py      # End-to-end workflow tests
```

---

## 🔧 Fixtures Available

Defined in `conftest.py`:

```python
# Automatic - runs before all tests
check_api_running()  # Verifies backend is running

# Use in tests
def test_example(api_base, test_user_id, sample_card):
    # api_base = "http://localhost:8008"
    # test_user_id = 1
    # sample_card = {...}  # A real card from database
    pass
```

---

## ✍️ Writing New Tests

### Template for API Test

```python
import pytest
import requests

API_BASE = "http://localhost:8008"

class TestMyFeature:
    """Test my new feature"""

    def test_my_endpoint(self):
        """Test description"""
        # Arrange
        payload = {"key": "value"}

        # Act
        response = requests.post(
            f"{API_BASE}/my-endpoint",
            json=payload,
            timeout=5
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["key"] == "value"
```

### Template for Integration Test

```python
def test_my_workflow(api_base, test_user_id):
    """
    User story: User does X, then Y, then Z

    Steps:
    1. Do X
    2. Do Y
    3. Verify Z
    """
    # Step 1: Do X
    response1 = requests.get(f"{api_base}/endpoint1")
    assert response1.status_code == 200

    # Step 2: Do Y
    result1 = response1.json()
    response2 = requests.post(
        f"{api_base}/endpoint2",
        json={"data": result1["id"]}
    )
    assert response2.status_code == 200

    # Step 3: Verify Z
    response3 = requests.get(f"{api_base}/endpoint3")
    assert response3.status_code == 200
    # ... assertions
```

---

## 🐛 Debugging Failed Tests

### Show More Detail

```bash
# Full traceback
pytest tests/ -v --tb=long

# Show print statements
pytest tests/ -v -s

# Show local variables on failure
pytest tests/ -v -l
```

### Debug Specific Test

```bash
# Run with Python debugger
pytest tests/test_cards_api.py::test_list_cards --pdb
```

### Check API Manually

```bash
# Health check
curl http://localhost:8008/healthz

# Test endpoint
curl http://localhost:8008/cards?limit=1 | jq

# Check logs
# Look at terminal running uvicorn
```

---

## 📈 CI/CD Integration

### GitHub Actions Example

```yaml
# .github/workflows/tests.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r tests/requirements.txt

      - name: Start backend
        run: |
          uvicorn app.main:app --port 8008 &
          sleep 5

      - name: Run tests
        run: pytest tests/ -v --cov=app
```

---

## 🎨 Test Best Practices

### DO ✅

1. **Test one thing per test**
   ```python
   def test_create_deck():
       """Test creating a deck"""
       # Just test deck creation
   ```

2. **Use descriptive test names**
   ```python
   def test_add_inventory_with_invalid_card_returns_404():
       # Clear what it tests
   ```

3. **Use arrange-act-assert pattern**
   ```python
   def test_example():
       # Arrange
       payload = {...}

       # Act
       response = requests.post(url, json=payload)

       # Assert
       assert response.status_code == 200
   ```

4. **Clean up test data** (if needed)
   ```python
   def test_create_deck():
       deck_id = create_deck()  # Create
       # ... test ...
       delete_deck(deck_id)  # Clean up
   ```

### DON'T ❌

1. **Don't test implementation details** - test behavior
2. **Don't have tests depend on each other** - each test should be independent
3. **Don't skip cleanup** - avoid polluting the database
4. **Don't test third-party code** - test YOUR code

---

## 📊 Test Metrics

### Current Coverage (Run to update)

```bash
./run-tests.sh coverage
```

### Expected Results

**Fast tests** (<1s each):
- Health checks
- Basic API calls
- Card listing

**Medium tests** (1-3s each):
- Inventory operations
- Deck creation
- Search queries

**Slow tests** (>3s):
- Integration tests
- Multi-step workflows

**Total runtime:** ~30-60 seconds for all tests

---

## 🚨 Common Issues

### Issue: "Backend not running"

**Error:**
```
❌ API not running at http://localhost:8008
```

**Fix:**
```bash
# Start backend first
uvicorn app.main:app --reload --port 8008

# Or
./start-local.sh
```

### Issue: "No module named 'pytest'"

**Fix:**
```bash
pip install -r tests/requirements.txt
```

### Issue: Tests failing randomly

**Possible causes:**
- Database locked (multiple processes)
- Port already in use
- Stale test data

**Fix:**
```bash
# Stop all processes
pkill -f uvicorn

# Remove lock files
rm data.db-wal data.db-shm

# Restart backend
uvicorn app.main:app --reload --port 8008

# Run tests again
./run-tests.sh
```

---

## 🎯 Next Steps

### Short Term
1. Run all tests: `./run-tests.sh`
2. Review coverage: `./run-tests.sh coverage`
3. Fix any failing tests
4. Add tests for new features

### Long Term
1. Achieve >80% test coverage
2. Add performance benchmarks
3. Add load testing (locust, k6)
4. Integrate with CI/CD
5. Add frontend tests (Vitest)

---

## 📚 Resources

**Pytest Documentation:**
- https://docs.pytest.org/

**HTTP Testing:**
- https://docs.python-requests.org/

**Coverage.py:**
- https://coverage.readthedocs.io/

**Best Practices:**
- https://testdriven.io/blog/testing-best-practices/

---

## Summary

**To run tests:**

```bash
# Make sure backend is running
./start-local.sh  # In one terminal

# Run tests
./run-tests.sh    # In another terminal
```

**Test categories:**
- ✅ Health & performance
- ✅ Cards API
- ✅ Inventory API
- ✅ Decks API
- ✅ Integration workflows

**Coverage goal:** >80%

Happy testing! 🧪✨
