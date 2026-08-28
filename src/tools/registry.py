"""
The tool registry: the ALLOW-LIST for what an agent turn can call, enforced
in code, not prompt text (capstone_build_plan.md §5). build_toolset(...) is
the only way to get a bound set of tools -- there is no code path that
constructs a write tool against customer/financial data, and there never
will be, per the "capability by omission" design rule in §2.
"""
from .account_tools import (
    make_check_dispute_status_tool,
    make_get_account_summary_tool,
    make_list_recent_transactions_tool,
)
from .deterministic_tools import calculate_emi
from .escalation_tools import make_create_escalation_ticket_tool
from .policy_tools import search_bank_policy

# The complete allow-list. Six tools, exactly as specified in
# capstone_build_plan.md §2 -- five readers, one writer (to the escalation
# queue only).
TOOL_NAMES = [
    "get_account_summary",
    "list_recent_transactions",
    "search_bank_policy",
    "check_dispute_status",
    "calculate_emi",
    "create_escalation_ticket",
]


def build_toolset(customer_id: str):
    """Return the six tools for one session, with customer_id closed over
    wherever an ownership check is required. customer_id must come from
    verified session context -- never from the LLM or the user turn."""
    return [
        make_get_account_summary_tool(customer_id),
        make_list_recent_transactions_tool(customer_id),
        search_bank_policy,
        make_check_dispute_status_tool(customer_id),
        calculate_emi,
        make_create_escalation_ticket_tool(customer_id),
    ]
