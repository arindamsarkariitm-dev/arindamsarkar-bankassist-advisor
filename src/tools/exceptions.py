"""
Tool error hierarchy for BankAssist Advisor.

Every tool in this package fails CLOSED: on any of these, the caller must
show "I couldn't retrieve that right now" + an escalation offer, and must
never guess or fabricate a substitute value. See capstone_build_plan.md §5.
"""


class ToolError(Exception):
    """Base class for all tool failures. Never caught silently -- the graph's
    tool node must turn every one of these into a fail-closed response."""


class AccountNotOwned(ToolError):
    """Raised when the requested account_id does not belong to the
    session's verified customer_id. This is a safeguard, not a lookup
    miss -- it must never be treated as 'account not found' and must never
    reveal whether the account_id exists at all."""


class NotFound(ToolError):
    """Raised when a valid, owned lookup key (account_id, case_id) doesn't
    match any record."""


class InvalidArguments(ToolError):
    """Raised for malformed tool arguments (e.g. a negative EMI tenure)."""


class AccountServiceUnavailable(ToolError):
    """Raised when the account/card/dispute data store itself can't be read
    (capstone_build_plan.md §8's "Account API down" degradation case). This
    can be raised OUTSIDE a tool call too -- customer_instrument_directory()
    is called directly from classify_intent/agent_node/clarify_node, not
    just from inside tools_node's try/except -- so those call sites must
    each catch this too, not just the tool loop."""
