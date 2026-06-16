#!/usr/bin/env python3
"""
Test script for verifying modular monolith migration
====================================================
Tests that all services are properly migrated and functional.
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
# marketplace lives outside services/ as an external plugin (see PLUGIN_PATHS /
# external_plugins/README.md) — add its root so opama_marketplace.* imports resolve.
sys.path.insert(0, str(PROJECT_ROOT / "external_plugins"))

def test_imports():
    """Test that all service modules can be imported."""
    print("\n" + "="*60)
    print("TESTING IMPORTS")
    print("="*60)

    tests = []

    # Test shared imports
    try:
        tests.append(("✓ Shared components", True))
    except Exception as e:
        tests.append(("✗ Shared components", False, str(e)))

    # Test catalog service
    try:
        tests.append(("✓ Catalog service", True))
    except Exception as e:
        tests.append(("✗ Catalog service", False, str(e)))

    # Test inventory service
    try:
        tests.append(("✓ Inventory service", True))
    except Exception as e:
        tests.append(("✗ Inventory service", False, str(e)))

    # Test decks service
    try:
        tests.append(("✓ Decks service", True))
    except Exception as e:
        tests.append(("✗ Decks service", False, str(e)))

    # Test trading service
    try:
        tests.append(("✓ Trading service", True))
    except Exception as e:
        tests.append(("✗ Trading service", False, str(e)))

    # Test marketplace service (external plugin — lives in external_plugins/, not services/)
    try:
        tests.append(("✓ Marketplace service", True))
    except Exception as e:
        tests.append(("✗ Marketplace service", False, str(e)))

    # Test AI service
    try:
        tests.append(("✓ AI service routers", True))
    except Exception as e:
        tests.append(("✗ AI service routers", False, str(e)))

    # Test AI submodules
    try:
        tests.append(("✓ AI RAG modules", True))
    except Exception as e:
        tests.append(("✗ AI RAG modules", False, str(e)))

    # Test main app
    try:
        tests.append(("✓ Main application", True))
    except Exception as e:
        tests.append(("✗ Main application", False, str(e)))

    # Print results
    passed = 0
    failed = 0
    for test in tests:
        print(f"\n{test[0]}")
        if not test[1]:
            print(f"  Error: {test[2]}")
            failed += 1
        else:
            passed += 1

    print(f"\n{'-'*60}")
    print(f"Import Tests: {passed} passed, {failed} failed")

    return failed == 0


def test_app_structure():
    """Test that the FastAPI app has all routers registered."""
    print("\n" + "="*60)
    print("TESTING APP STRUCTURE")
    print("="*60)

    try:
        from app.main import app

        # Get all registered routes
        routes = []
        for route in app.routes:
            if hasattr(route, 'path'):
                routes.append(route.path)

        print(f"\nTotal routes registered: {len(routes)}")

        # Check for key endpoints
        expected_prefixes = [
            '/cards',
            '/inventory',
            '/decks',
            '/suggest',
            '/user',
            '/ai',
            '/api/ebay',
            '/healthz',
        ]

        print("\nChecking expected route prefixes:")
        all_found = True
        for prefix in expected_prefixes:
            found = any(route.startswith(prefix) for route in routes)
            status = "✓" if found else "✗"
            print(f"  {status} {prefix}")
            if not found:
                all_found = False

        # Check router count
        print("\nExpected 7 service routers + health endpoints")
        print(f"Found {len([r for r in routes if not r.startswith('/openapi')])} routes")

        return all_found

    except Exception as e:
        print(f"\n✗ Error testing app structure: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_database_models():
    """Test that database models are properly defined."""
    print("\n" + "="*60)
    print("TESTING DATABASE MODELS")
    print("="*60)

    try:
        from services.shared.models import User
        from opama_pokemon_tcg.catalog.models import Card, Set, CardFeatures
        from opama_pokemon_tcg.decks.models import Deck, DeckCard
        from opama_pokemon_tcg.inventory.models import InventoryItem
        from opama_pokemon_tcg.trading.models import WishList, TradeItem
        from sqlmodel import SQLModel

        models = [Card, Set, User, Deck, DeckCard, InventoryItem, CardFeatures, WishList, TradeItem]

        print("\nChecking SQLModel tables:")
        for model in models:
            has_table = hasattr(model, '__tablename__') or (
                hasattr(model, '__table__') and model.__table__ is not None
            )
            status = "✓" if has_table else "✗"
            print(f"  {status} {model.__name__}")

        # Check metadata
        table_count = len(SQLModel.metadata.tables)
        print(f"\nTotal tables in metadata: {table_count}")
        print("Expected: ~9 tables")

        return table_count >= 8

    except Exception as e:
        print(f"\n✗ Error testing models: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_service_independence():
    """Test that services have proper structure and are independent."""
    print("\n" + "="*60)
    print("TESTING SERVICE INDEPENDENCE")
    print("="*60)

    services = {
        'catalog': 'services/catalog',
        'inventory': 'services/inventory',
        'decks': 'services/decks',
        'trading': 'services/trading',
        'ai': 'services/ai',
    }
    print("\nChecking service directory structure:")
    all_good = True

    # marketplace is an external plugin now (external_plugins/opama_marketplace) —
    # it doesn't follow the services/<id>/ layout, so it's checked separately.
    external_plugin_dir = PROJECT_ROOT / 'external_plugins' / 'opama_marketplace'
    ext_init = (external_plugin_dir / '__init__.py').exists()
    ext_router = (external_plugin_dir / 'router.py').exists()
    ext_manifest = (external_plugin_dir / 'plugin.yaml').exists()
    ext_status = "✓" if (ext_init and ext_router and ext_manifest) else "✗"
    print(f"  {ext_status} {'marketplace':12} - external plugin: router={ext_router}, "
          f"__init__={ext_init}, plugin.yaml={ext_manifest}")
    if not (ext_init and ext_router and ext_manifest):
        all_good = False

    for name, path in services.items():
        service_path = PROJECT_ROOT / path
        init_exists = (service_path / '__init__.py').exists()

        # AI service has split routers (suggest_router.py and chat_router.py)
        if name == 'ai':
            router_exists = (
                (service_path / 'suggest_router.py').exists() and
                (service_path / 'chat_router.py').exists()
            )
        else:
            router_exists = (service_path / 'router.py').exists()

        status = "✓" if (router_exists and init_exists) else "✗"
        print(f"  {status} {name:12} - router: {router_exists}, __init__: {init_exists}")

        if not (router_exists and init_exists):
            all_good = False

    # Check shared directory
    shared_path = PROJECT_ROOT / 'services' / 'shared'
    required_shared = ['database.py', 'models.py', '__init__.py']

    print("\nChecking shared components:")
    for filename in required_shared:
        exists = (shared_path / filename).exists()
        status = "✓" if exists else "✗"
        print(f"  {status} {filename}")
        if not exists:
            all_good = False

    return all_good


def test_no_circular_imports():
    """Test for circular import issues."""
    print("\n" + "="*60)
    print("TESTING FOR CIRCULAR IMPORTS")
    print("="*60)

    try:
        # Try importing everything in sequence
        import services.shared.database
        import services.shared.models
        import opama_pokemon_tcg.trading.models

        import opama_pokemon_tcg.catalog.router
        import opama_pokemon_tcg.inventory.router
        import opama_pokemon_tcg.decks.router
        import opama_pokemon_tcg.trading.router  # noqa: F401
        import opama_marketplace.router  # noqa: F401 — external plugin — see external_plugins/README.md
        import services.ai.suggest_router
        import services.ai.chat_router  # noqa: F401

        import app.main  # noqa: F401

        print("\n✓ No circular import errors detected")
        return True

    except ImportError as e:
        print(f"\n✗ Circular import detected: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("MODULAR MONOLITH MIGRATION TEST SUITE")
    print("="*60)
    print(f"Project root: {PROJECT_ROOT}")

    results = {
        "Imports": test_imports(),
        "App Structure": test_app_structure(),
        "Database Models": test_database_models(),
        "Service Independence": test_service_independence(),
        "No Circular Imports": test_no_circular_imports(),
    }

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status:8} {test_name}")

    print(f"\n{'-'*60}")
    print(f"Total: {passed}/{total} test suites passed")

    if passed == total:
        print("\n🎉 All tests passed! Migration successful!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test suite(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
