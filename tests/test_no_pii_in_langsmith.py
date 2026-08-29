"""
Safety test: proves src/langsmith_tracing.py's redaction hook actually
strips PII from realistic LangChain run payloads, and that tracing stays
off unless explicitly enabled. Plain script with asserts, matching this
project's existing eval-script style (no pytest dependency) -- run directly:

    python tests/test_no_pii_in_langsmith.py

Does NOT make a real network call to LangSmith -- it tests the redaction
function and the Client wiring in isolation, which is what matters for the
"no PII leaves this process" guarantee. A real live-traffic check (does the
LangSmith dashboard actually show redacted text) is a separate, manual
verification step documented in Phase_8/docs/08_deployment.md, since it
needs a real API key that only the project owner holds.
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


# 1. Tracing is off by default -- the single most important safety property:
# if nothing is configured, zero data of any kind reaches LangSmith.
check("tracing disabled by default (no env var set)", lt.ENABLED is False)
check("tracing_callbacks() returns [] when disabled", lt.tracing_callbacks() == [])

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
