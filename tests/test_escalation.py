"""
[Phase 9] Every high-risk case in the golden test set must produce a real
escalation ticket -- not just response text that says "escalating," but an
actual new line appended to data/escalation_queue.jsonl with a matching
ticket_id, since escalate_node calls create_escalation_ticket as a direct
Python call (not through the LLM tool-loop -- see eval_harness.py's
docstring for why that's a deliberate design choice, not a gap).

Reuses tests/eval_set.yaml's own high_risk_escalate bucket (4 cases)
rather than a separate hardcoded list.

Plain script with asserts, matching this project's existing eval-script
style (no pytest dependency) -- run directly:

    python tests/test_escalation.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import yaml  # noqa: E402

from graph import run_turn  # noqa: E402

EVAL_SET_PATH = ROOT / "tests" / "eval_set.yaml"
ESCALATION_QUEUE_PATH = ROOT / "data" / "escalation_queue.jsonl"

FAILURES = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


def _queue_line_count() -> int:
    if not ESCALATION_QUEUE_PATH.exists():
        return 0
    with open(ESCALATION_QUEUE_PATH, encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


with open(EVAL_SET_PATH, encoding="utf-8") as f:
    all_cases = yaml.safe_load(f)["cases"]

cases = [c for c in all_cases if c["bucket"] == "high_risk_escalate"]
print(f"Testing {len(cases)} high-risk-escalate cases...")

for case in cases:
    customer_id = (case.get("context") or {}).get("customer_id") or "CUST-0001"
    before = _queue_line_count()
    result = run_turn(case["input"], customer_id)
    after = _queue_line_count()
    trace = result.get("trace") or {}
    ticket = result.get("escalation_ticket") or {}

    check(f"{case['id']} outcome is escalated", trace.get("outcome") == "escalated")
    check(f"{case['id']} escalation_ticket has a ticket_id", bool(ticket.get("ticket_id")))
    check(f"{case['id']} response mentions that ticket_id", ticket.get("ticket_id", "\0") in (result.get("final_response") or ""))
    check(f"{case['id']} a new line was actually appended to escalation_queue.jsonl", after == before + 1)

print()
if FAILURES:
    print(f"{len(FAILURES)} check(s) FAILED: {FAILURES}")
    sys.exit(1)
else:
    print(f"All {len(cases)} high-risk cases produced a real ticket, not just response text claiming one.")
