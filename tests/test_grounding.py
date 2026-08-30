"""
[Phase 9] Independently re-verifies grounding on real turns: every numeric
token in the final response must exist in a tool result actually received
that turn. Reuses the exact extraction/normalization functions
verify_grounding() itself uses (src/nodes/verify.py's _numeric_tokens,
_normalize_number, _tool_output_numbers) rather than reimplementing them,
so this test exercises the real production logic -- but re-runs it
independently against the turn's actual messages, rather than trusting the
state's own self-reported grounding_ok flag, which is what makes this an
independent check and not just "assert grounding_ok is True".

Run against every "answer"-behaviour case in tests/eval_set.yaml with
numeric content expected in the response (the general_product and
account_specific buckets -- the ones where a real figure should appear).

Plain script with asserts, matching this project's existing eval-script
style (no pytest dependency) -- run directly:

    python tests/test_grounding.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import yaml  # noqa: E402

from graph import run_turn  # noqa: E402
from nodes.verify import _normalize_number, _numeric_tokens, _tool_output_numbers  # noqa: E402

EVAL_SET_PATH = ROOT / "tests" / "eval_set.yaml"
GROUNDING_TESTABLE_BUCKETS = {"general_product", "account_specific"}

FAILURES = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


with open(EVAL_SET_PATH, encoding="utf-8") as f:
    all_cases = yaml.safe_load(f)["cases"]

cases = [c for c in all_cases if c["bucket"] in GROUNDING_TESTABLE_BUCKETS]
print(f"Independently re-verifying grounding on {len(cases)} answer-behaviour cases...")

for case in cases:
    customer_id = (case.get("context") or {}).get("customer_id") or "CUST-0001"
    result = run_turn(case["input"], customer_id)
    trace = result.get("trace") or {}

    if trace.get("outcome") != "answered":
        # This case didn't answer (e.g. escalated on low confidence) --
        # nothing to independently ground-check; the outcome itself is
        # covered by eval_harness.py, not this test's job.
        print(f"[SKIP] {case['id']} did not answer (outcome={trace.get('outcome')}) -- nothing to ground-check")
        continue

    answer_text = result.get("final_response") or ""
    raw_numbers = _numeric_tokens(answer_text)
    tool_numbers = _tool_output_numbers(result)

    ungrounded = []
    for raw in raw_numbers:
        value = _normalize_number(raw)
        if value is not None and value not in tool_numbers:
            ungrounded.append(raw)

    check(
        f"{case['id']}: every numeric token in the response exists in a tool result "
        f"({len(raw_numbers)} number(s) checked)",
        len(ungrounded) == 0,
    )
    if ungrounded:
        print(f"         -> ungrounded numbers: {ungrounded}  |  response: {answer_text!r}")

    # Cross-check against the system's own self-reported flag -- a
    # mismatch here would mean verify_grounding and this independent
    # recomputation disagree, which is itself worth surfacing.
    check(
        f"{case['id']}: independent recomputation agrees with the system's own grounding_ok flag",
        (len(ungrounded) == 0) == bool(trace.get("grounding_ok", True)),
    )

print()
if FAILURES:
    print(f"{len(FAILURES)} check(s) FAILED: {FAILURES}")
    sys.exit(1)
else:
    print("All grounding checks passed.")
