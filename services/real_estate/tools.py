"""
AI tools for Property Records (services/real_estate).

Both tools are read-only. See services/custom_assets/tools.py for the
handler/registration pattern.
"""
from __future__ import annotations

from services.shared.llm import ToolSpec
from services.shared.tool_registry import ToolDefinition
from .router import list_mortgages, real_estate_summary


def _get_real_estate_summary(session, user, args):
    return real_estate_summary(session=session, current_user=user)


def _list_mortgages(session, user, args):
    return list_mortgages(asset_id=args.get("asset_id"), session=session, current_user=user)


TOOLS = [
    ToolDefinition(
        spec=ToolSpec(
            name="get_real_estate_summary",
            description="Get summary stats for the user's properties: property count, total mortgage balance, total estimated value, estimated equity, and property taxes due soon.",
            parameters={"type": "object", "properties": {}},
        ),
        handler=_get_real_estate_summary,
        mutating=False,
    ),
    ToolDefinition(
        spec=ToolSpec(
            name="list_mortgages",
            description="List the user's mortgages/loans, optionally filtered to one property (asset).",
            parameters={
                "type": "object",
                "properties": {"asset_id": {"type": "integer", "description": "Filter to one property's asset ID"}},
            },
        ),
        handler=_list_mortgages,
        mutating=False,
    ),
]
