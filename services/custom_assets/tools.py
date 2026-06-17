"""
AI tools for Collections (services/custom_assets).

Each tool wraps an existing router function, calling it directly with
explicit `session=`/`current_user=` kwargs — the router functions take these
as `Depends(...)` *defaults*, so passing explicit values bypasses FastAPI's
DI cleanly. See docs/MODULE_DEVELOPMENT.md and
services/shared/tool_registry.py for how `TOOLS` is discovered.

4 read-only tools + 2 mutating tools (create/update an asset).
"""
from __future__ import annotations

from services.shared.llm import ToolSpec
from services.shared.tool_registry import ToolDefinition
from services.auth.org_context import resolve_org_context
from .router import create_asset, get_asset, list_assets, list_categories, portfolio_summary, update_asset
from .schemas import CustomAssetCreate, CustomAssetUpdate

# Categories with their own module (Vehicle Maintenance, Real Estate) are
# matched case-insensitively by those modules (see services/vehicles/router.py,
# services/real_estate/router.py), but Collections groups and filters by exact
# category string. Normalize to the canonical casing so AI-created items land
# in the same group as items created through the module's own "Add" flow.
_CANONICAL_CATEGORIES = {
    "vehicle": "Vehicle",
    "bicycle": "Bicycle",
    "real estate": "Real Estate",
}


def _normalize_category(category: str) -> str:
    return _CANONICAL_CATEGORIES.get(category.strip().lower(), category.strip())


def _list_assets(session, user, args):
    category = args.get("category")
    return list_assets(
        category=_normalize_category(category) if category else None,
        q=args.get("q"),
        limit=min(int(args.get("limit", 20)), 100),
        offset=0,
        session=session,
        ctx=resolve_org_context(user, session),
    )


def _get_asset(session, user, args):
    return get_asset(asset_id=int(args["asset_id"]), session=session, ctx=resolve_org_context(user, session))


def _get_collection_summary(session, user, args):
    return portfolio_summary(session=session, ctx=resolve_org_context(user, session))


def _list_asset_categories(session, user, args):
    return list_categories(session=session, ctx=resolve_org_context(user, session))


def _create_custom_asset(session, user, args):
    body = CustomAssetCreate(
        name=args["name"],
        category=_normalize_category(args["category"]),
        condition=args.get("condition"),
        quantity=args.get("quantity", 1),
        purchase_price=args.get("purchase_price"),
        estimated_value=args.get("estimated_value"),
        description=args.get("description"),
    )
    return create_asset(
        body=body, session=session, current_user=user, ctx=resolve_org_context(user, session)
    )


def _update_asset_value(session, user, args):
    body = CustomAssetUpdate(
        estimated_value=args.get("estimated_value"),
        condition=args.get("condition"),
        description=args.get("description"),
    )
    return update_asset(
        asset_id=int(args["asset_id"]), body=body, session=session, ctx=resolve_org_context(user, session)
    )


TOOLS = [
    ToolDefinition(
        spec=ToolSpec(
            name="list_assets",
            description="List the user's collection items (any asset class), optionally filtered by category or a search term.",
            parameters={
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Filter by exact category name"},
                    "q": {"type": "string", "description": "Search term matched against item name"},
                    "limit": {"type": "integer", "description": "Max items to return (default 20, max 100)", "default": 20},
                },
            },
        ),
        handler=_list_assets,
        mutating=False,
    ),
    ToolDefinition(
        spec=ToolSpec(
            name="get_asset",
            description="Get full details for one collection item by ID.",
            parameters={
                "type": "object",
                "properties": {"asset_id": {"type": "integer"}},
                "required": ["asset_id"],
            },
        ),
        handler=_get_asset,
        mutating=False,
    ),
    ToolDefinition(
        spec=ToolSpec(
            name="get_collection_summary",
            description="Get portfolio totals (cost, estimated value, unrealized gain) and a per-category breakdown across the user's whole collection.",
            parameters={"type": "object", "properties": {}},
        ),
        handler=_get_collection_summary,
        mutating=False,
    ),
    ToolDefinition(
        spec=ToolSpec(
            name="list_asset_categories",
            description="List the distinct collection categories the user has items in.",
            parameters={"type": "object", "properties": {}},
        ),
        handler=_list_asset_categories,
        mutating=False,
    ),
    ToolDefinition(
        spec=ToolSpec(
            name="create_custom_asset",
            description="Create a new collection item. Requires user confirmation before running.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "category": {"type": "string"},
                    "condition": {"type": "string"},
                    "quantity": {"type": "integer", "default": 1},
                    "purchase_price": {"type": "number"},
                    "estimated_value": {"type": "number"},
                    "description": {"type": "string"},
                },
                "required": ["name", "category"],
            },
        ),
        handler=_create_custom_asset,
        mutating=True,
    ),
    ToolDefinition(
        spec=ToolSpec(
            name="update_asset_value",
            description="Update a collection item's estimated value, condition, and/or description. Requires user confirmation before running.",
            parameters={
                "type": "object",
                "properties": {
                    "asset_id": {"type": "integer"},
                    "estimated_value": {"type": "number"},
                    "condition": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["asset_id"],
            },
        ),
        handler=_update_asset_value,
        mutating=True,
    ),
]
