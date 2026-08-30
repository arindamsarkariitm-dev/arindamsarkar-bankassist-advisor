"""
[Phase 9] Two tool-safety guards, tested directly rather than by hoping a
real conversation happens to trigger them (same pattern established in
Phase 5's safeguard tests and Phase 8's resilience tests):

1. Cross-customer account access is blocked -- a tool built for CUST-0001
   must raise AccountNotOwned (never silently return data, never a plain
   "not found" that would let someone probe which ids exist) when asked
   for an account/card/dispute id that actually belongs to CUST-0002.
2. The per-turn tool-call loop cap (MAX_TOOL_CALLS_PER_TURN=5) is enforced
   -- the 6th call in one turn gets an error message back, not a 6th real
   tool execution.

Plain script with asserts, matching this project's existing eval-script
style (no pytest dependency) -- run directly:

    python tests/test_tool_guards.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from langchain_core.messages import AIMessage  # noqa: E402

from nodes.agent import tools_node  # noqa: E402
from tools.exceptions import AccountNotOwned  # noqa: E402
from tools.registry import build_toolset  # noqa: E402

FAILURES = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


# --- Guard 1: cross-customer account access -------------------------------
cust1_tools = {t.name: t for t in build_toolset("CUST-0001")}
get_account_summary = cust1_tools["get_account_summary"]

# ACC-1003 belongs to CUST-0002 (data/customers.json) -- CUST-0001's own
# tool instance must refuse it.
try:
    get_account_summary.invoke({"account_id": "ACC-1003"})
    check("cross-customer account access raises AccountNotOwned", False)
except AccountNotOwned:
    check("cross-customer account access raises AccountNotOwned", True)
except Exception as e:  # noqa: BLE001
    check(f"cross-customer account access raises AccountNotOwned (got {type(e).__name__} instead)", False)

# Sanity check the guard isn't just "always raise" -- CUST-0001's own
# account must still work.
try:
    result = get_account_summary.invoke({"account_id": "ACC-1001"})
    check("CUST-0001's own account (ACC-1001) still accessible", result.get("account_id") == "ACC-1001")
except Exception as e:  # noqa: BLE001
    check(f"CUST-0001's own account (ACC-1001) still accessible (raised {type(e).__name__})", False)

check_dispute_status = cust1_tools["check_dispute_status"]
try:
    check_dispute_status.invoke({"case_id": "DSP-002"})  # belongs to CUST-0002
    check("cross-customer dispute access raises AccountNotOwned", False)
except AccountNotOwned:
    check("cross-customer dispute access raises AccountNotOwned", True)
except Exception as e:  # noqa: BLE001
    check(f"cross-customer dispute access raises AccountNotOwned (got {type(e).__name__} instead)", False)


# --- Guard 2: per-turn tool-call loop cap ----------------------------------
def _make_state(tool_call_count: int, account_id: str = "ACC-1001") -> dict:
    ai_message = AIMessage(
        content="",
        tool_calls=[{"name": "get_account_summary", "args": {"account_id": account_id}, "id": "call_1"}],
    )
    return {
        "customer_id": "CUST-0001",
        "messages": [ai_message],
        "tool_call_count": tool_call_count,
        "tool_call_hashes": [],
        "tools_called": [],
        "doc_ids_cited": [],
    }


# Below the cap (count=4 -> this would be the 5th call): allowed through.
below_cap_result = tools_node(_make_state(4, account_id="ACC-1001"))
below_cap_tool_message = below_cap_result["messages"][-1]
check(
    "5th call in a turn (at the cap, not over it) executes normally",
    "error" not in below_cap_tool_message.content.lower() or "limit" not in below_cap_tool_message.content.lower(),
)

# At the cap (count=5 -> this would be the 6th call): blocked.
at_cap_result = tools_node(_make_state(5))
at_cap_tool_message = at_cap_result["messages"][-1]
check(
    "6th call in a turn is blocked with a limit error, not executed",
    "limit" in at_cap_tool_message.content.lower(),
)
check(
    "tool_call_count does not increment past the cap",
    at_cap_result["tool_call_count"] == 5,
)

print()
if FAILURES:
    print(f"{len(FAILURES)} check(s) FAILED: {FAILURES}")
    sys.exit(1)
else:
    print("All tool-guard checks passed.")
