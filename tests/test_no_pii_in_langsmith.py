"""
Safety test for src/langsmith_tracing.py -- a module now HARD-DISABLED
after live testing found it unsafe (see its own docstring and
Phase_8/docs/08_deployment.md for the full investigation). Two things are
verified here, and they prove different, non-overlapping things:

1. tracing_callbacks() always returns [] -- the actual safety guarantee in
   force right now, regardless of the ENABLE_SAFE_LANGSMITH_TRACING env var.
   This is the check that matters for "can this leak PII today."
2. _redact_value() itself correctly strips PII from a realistic nested
   payload -- proving the REDACTION LOGIC is correct in isolation. This
   does NOT prove live LangSmith uploads are safe -- live testing found
   they are not, for reasons this function's correctness doesn't reach
   (see the module docstring). Kept because a future, real fix (a custom
   callback intercepting LangChain's own message objects, rather than
   relying on LangSmith's Client-level hide_* hooks) would still need this
   exact redaction logic to be correct as a building block.

Plain script with asserts, matching this project's existing eval-script
style (no pytest dependency) -- run directly:

    python tests/test_no_pii_in_langsmith.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import langsmith_tracing as lt  # noqa: E402

FAILURES = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        FAILURES.append(label)


def contains_pii(value) -> bool:
    """Recursively scan a redacted structure for anything that looks like
    it was missed -- deliberately independent of _redact_value's own logic,
    checking for the RAW values we know we put in, not for the presence of
    the [PLACEHOLDER] tokens (a check that could pass vacuously if
    redaction did nothing but the raw text happened not to match)."""
    RAW_PII_STRINGS = ["Priya Menon", "590", "9876543210", "XXXXXXXX1001", "rohan.verma@example.com"]
    if isinstance(value, str):
        return any(raw in value for raw in RAW_PII_STRINGS)
    if isinstance(value, dict):
        return any(contains_pii(v) for v in value.values())
    if isinstance(value, list):
        return any(contains_pii(v) for v in value)
    return False


# 1. Tracing is hard-disabled -- the actual safety property in force now.
# Deliberately does NOT assert lt.ENABLED is False: the env var may well be
# true (e.g. left over from testing) -- that must NOT matter. The real
# guarantee is tracing_callbacks() always returning [] regardless.
check("tracing_callbacks() returns [] unconditionally", lt.tracing_callbacks() == [])
check("KNOWN_UNSAFE flag is set (documents why, not just that)", lt.KNOWN_UNSAFE is True)

# 2. Realistic nested LangChain-shaped payload -- messages, metadata, tool
# calls, numeric fields -- all in one structure, like a real chat-model run.
sample_run_payload = {
    "messages": [
        [
            {
                "type": "human",
                "content": (
                    "Customer's asking why she was charged ₹590 on 14 July -- "
                    "can you check TXN-0076? Her account is XXXXXXXX1001, "
                    "phone 9876543210."
                ),
            }
        ]
    ],
    "metadata": {
        "customer_name": "Priya Menon",
        "contact_email": "rohan.verma@example.com",
    },
    "confidence": 0.92,
    "tool_calls": [{"name": "search_bank_policy", "args": {"query": "foreign transaction fee"}}],
}

redacted = lt._redact_value(sample_run_payload)

check("redacted payload contains none of the raw PII strings", not contains_pii(redacted))
check(
    "safe reference ID (TXN-0076) preserved through redaction",
    "TXN-0076" in redacted["messages"][0][0]["content"],
)
check(
    "non-PII numeric field (confidence) preserved and untouched",
    redacted["confidence"] == 0.92,
)
check(
    "tool call structure (name/args) preserved",
    redacted["tool_calls"][0]["name"] == "search_bank_policy",
)

# 3. Non-string/dict/list values pass through unchanged (no crash on None/bool).
check("None passes through _redact_value unchanged", lt._redact_value(None) is None)
check("bool passes through _redact_value unchanged", lt._redact_value(True) is True)

print()
if FAILURES:
    print(f"{len(FAILURES)} check(s) FAILED: {FAILURES}")
    sys.exit(1)
else:
    print("All checks passed.")
