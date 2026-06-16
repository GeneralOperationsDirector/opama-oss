"""
AI tools for Insurance & Appraisals (services/insurance).

Both tools are read-only. See services/custom_assets/tools.py for the
handler/registration pattern.
"""
from __future__ import annotations

from services.shared.llm import ToolSpec
from services.shared.tool_registry import ToolDefinition
from .router import insurance_summary, list_policies


def _get_insurance_summary(session, user, args):
    return insurance_summary(session=session, current_user=user)


def _list_insurance_policies(session, user, args):
    return list_policies(session=session, current_user=user)


TOOLS = [
    ToolDefinition(
        spec=ToolSpec(
            name="get_insurance_summary",
            description="Get summary stats for the user's insurance: policy count, appraisal count, total coverage, total scheduled item value, and policies expiring soon.",
            parameters={"type": "object", "properties": {}},
        ),
        handler=_get_insurance_summary,
        mutating=False,
    ),
    ToolDefinition(
        spec=ToolSpec(
            name="list_insurance_policies",
            description="List the user's insurance policies.",
            parameters={"type": "object", "properties": {}},
        ),
        handler=_list_insurance_policies,
        mutating=False,
    ),
]
