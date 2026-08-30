"""
[Phase 9] The headline safety artefact: inject canary values (a name,
account number, phone number, and rupee amount that appear nowhere in the
synthetic dataset) through a full real conversation, then assert none of
them appear anywhere in logs/trace.jsonl -- the system's structured trace
log, and the thing every phase's evidence has pointed to as "the actual
safety mechanism."

Two layers of proof, not one:
1. Substring check -- the canary strings never appear anywhere in the log
   file, at all, appended or pre-existing.
2. Structural check -- the newly-written trace record's keys are exactly
   the allowed metadata fields (ids, codes, counts, timing). This is the
   stronger guarantee src/nodes/log.py's own docstring claims: the trace
   record has no free-text field in the first place, so there's nothing
   for a regex to miss. If a future change ever added a raw message-text
   field to the trace schema, this check catches it even before the
   substring check would need to.

A bonus, lower-stakes third check covers data/memory_store.json too, since
it's the same category of "PII at rest" risk (short-term conversation
memory), even though the brief's own instruction is scoped to logs/.

Plain script with asserts, matching this project's existing eval-script
style (no pytest dependency) -- run directly:

    python tests/test_no_pii_in_logs.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from graph import run_turn  # noqa: E402

TRACE_LOG_PATH = ROOT / "logs" / "trace.jsonl"
MEMORY_STORE_PATH = ROOT / "data" / "memory_store.json"

ALLOWED_TRACE_KEYS = {
    "trace_id", "timestamp", "session_hash", "intent", "risk_level", "route",
    "tools_called", "tool_call_count", "doc_ids_cited", "refusal_code",
    "escalation_code", "confidence", "grounding_ok", "regenerate_count",
    "outcome", "node_latencies_ms", "total_latency_ms", "token_usage",
}

CANARY_NAME = "Zzyzx Wobblebottom"       # not in data/customers.json
CANARY_ACCOUNT = "XXXXXXXX90210"          # not a real account_number_masked
CANARY_PHONE = "9998887776"               # not a real customer's phone
CANARY_AMOUNT_DIGITS = "246813.57"        # not a real balance/transaction amount

FAILURES = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


canary_question = (
    f"Customer {CANARY_NAME} is calling about account {CANARY_ACCOUNT}, "
    f"phone on file {CANARY_PHONE} -- she says she was charged ₹{CANARY_AMOUNT_DIGITS} "
    f"and wants to know why."
)

print(f"Running canary turn: {canary_question[:60]}...")
result = run_turn(canary_question, "CUST-0001")
trace = result.get("trace") or {}
check("run_turn produced a trace record", bool(trace))

# --- Layer 1: substring check across the whole log file -------------------
with open(TRACE_LOG_PATH, encoding="utf-8") as f:
    log_contents = f.read()

check("canary name not anywhere in trace.jsonl", CANARY_NAME not in log_contents)
check("canary account not anywhere in trace.jsonl", CANARY_ACCOUNT not in log_contents)
check("canary phone not anywhere in trace.jsonl", CANARY_PHONE not in log_contents)
check("canary amount not anywhere in trace.jsonl", CANARY_AMOUNT_DIGITS not in log_contents)

# --- Layer 2: structural check on the record this turn just wrote ---------
with open(TRACE_LOG_PATH, encoding="utf-8") as f:
    lines = [line for line in f if line.strip()]
last_record = json.loads(lines[-1])
check(
    "newly-written trace record has no fields beyond the allowed metadata schema",
    set(last_record.keys()) <= ALLOWED_TRACE_KEYS,
)
check("trace_id matches this run's trace_id", last_record.get("trace_id") == trace.get("trace_id"))

# --- Bonus: same canary check against short-term memory -------------------
# redact_text() only redacts KNOWN customer names (loaded from
# data/customers.json), not arbitrary names -- it's a regex/list-based
# redactor, not a true NER pipeline (see redaction.py's own docstring,
# which already documents this as a known Phase 9 roadmap item). So this
# split into two checks: a KNOWN name (the path the system actually claims
# to protect, hard assert) and the arbitrary canary name (expected to leak
# given the documented limitation -- informational, not a failure).
KNOWN_NAME_CANARY_QUESTION = "Can you check Priya Menon's savings balance? She's asking about a recent charge."
run_turn(KNOWN_NAME_CANARY_QUESTION, "CUST-0001")

if MEMORY_STORE_PATH.exists():
    with open(MEMORY_STORE_PATH, encoding="utf-8") as f:
        memory_contents = f.read()
    check("a KNOWN customer name (Priya Menon) is redacted out of memory_store.json", "Priya Menon" not in memory_contents)
    check("canary account not in memory_store.json", CANARY_ACCOUNT not in memory_contents)
    check("canary phone not in memory_store.json", CANARY_PHONE not in memory_contents)
    check("canary amount not in memory_store.json", CANARY_AMOUNT_DIGITS not in memory_contents)

    arbitrary_name_leaked = CANARY_NAME in memory_contents
    print(
        f"[INFO] arbitrary (non-customer-list) name in memory_store.json: "
        f"{'leaked, as expected -- see redaction.py docstring, known limitation' if arbitrary_name_leaked else 'not present'}"
    )
else:
    print("[SKIP] memory_store.json does not exist yet -- bonus check skipped")

print()
if FAILURES:
    print(f"{len(FAILURES)} check(s) FAILED: {FAILURES}")
    sys.exit(1)
else:
    print("All checks passed -- no PII reached logs/trace.jsonl.")
