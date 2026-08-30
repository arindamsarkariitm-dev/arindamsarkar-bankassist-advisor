"""
[Phase 9] Every money-movement / approval / legal-advice prompt in the
golden test set must be refused -- no exceptions, since these are the
categories capability-by-omission and policy_gate exist specifically to
guarantee (docs/01_risk_taxonomy.md). Reuses tests/eval_set.yaml's own
prohibited_money_movement / prohibited_approval / prohibited_legal_advice
buckets (8 cases total) rather than a separate hardcoded list, so this
test and the golden set can never silently drift apart.

Plain script with asserts, matching this project's existing eval-script
style (no pytest dependency) -- run directly:

    python tests/test_refusals.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import yaml  # noqa: E402

from graph import run_turn  # noqa: E402

EVAL_SET_PATH = ROOT / "tests" / "eval_set.yaml"
REFUSAL_BUCKETS = {"prohibited_money_movement", "prohibited_approval", "prohibited_legal_advice"}

FAILURES = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


with open(EVAL_SET_PATH, encoding="utf-8") as f:
    all_cases = yaml.safe_load(f)["cases"]

cases = [c for c in all_cases if c["bucket"] in REFUSAL_BUCKETS]
print(f"Testing {len(cases)} refusal-category cases across {sorted(REFUSAL_BUCKETS)}...")

for case in cases:
    customer_id = (case.get("context") or {}).get("customer_id") or "CUST-0001"
    result = run_turn(case["input"], customer_id)
    trace = result.get("trace") or {}
    check(f"{case['id']} ({case['bucket']}) refused", trace.get("outcome") == "refused")
    check(f"{case['id']} refusal never called a tool (refusal fires before any tool call)",
          not result.get("tools_called"))
    for forbidden in case.get("must_not_contain") or []:
        check(f"{case['id']} does not contain {forbidden!r}",
              forbidden.lower() not in (result.get("final_response") or "").lower())

print()
if FAILURES:
    print(f"{len(FAILURES)} check(s) FAILED: {FAILURES}")
    sys.exit(1)
else:
    print(f"All {len(cases)} refusal cases correctly refused, no tool calls, no forbidden strings.")
