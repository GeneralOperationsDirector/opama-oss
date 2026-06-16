"""
AI tools for Vehicle Maintenance (services/vehicles).

Both tools are read-only. See services/custom_assets/tools.py for the
handler/registration pattern.
"""
from __future__ import annotations

from services.shared.llm import ToolSpec
from services.shared.tool_registry import ToolDefinition
from .router import list_service_records, vehicle_summary


def _get_vehicle_summary(session, user, args):
    return vehicle_summary(session=session, current_user=user)


def _list_vehicle_service_records(session, user, args):
    return list_service_records(asset_id=args.get("asset_id"), session=session, current_user=user)


TOOLS = [
    ToolDefinition(
        spec=ToolSpec(
            name="get_vehicle_summary",
            description="Get summary stats for the user's vehicles: vehicle count, total service cost, service record count, and documents expiring soon.",
            parameters={"type": "object", "properties": {}},
        ),
        handler=_get_vehicle_summary,
        mutating=False,
    ),
    ToolDefinition(
        spec=ToolSpec(
            name="list_vehicle_service_records",
            description="List the user's vehicle service/maintenance records, optionally filtered to one vehicle (asset).",
            parameters={
                "type": "object",
                "properties": {"asset_id": {"type": "integer", "description": "Filter to one vehicle's asset ID"}},
            },
        ),
        handler=_list_vehicle_service_records,
        mutating=False,
    ),
]
