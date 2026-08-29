"""
The PII layer, used by both logging (this phase) and memory (Phase 6).

Pattern-based redaction: currency amounts, account/card-number-shaped
sequences, known customer names, emails, and phone numbers are replaced
with typed placeholders before any free text reaches a log file. Reference
IDs (TXN-/ACC-/DSP-/CARD-/TCKT-/doc_id strings) are deliberately left alone
-- capstone_build_plan.md §8's structured-logging spec explicitly allows
tool names and doc_ids in logs; they're safe handles, not PII.

This is a first-pass, regex-based redactor appropriate for this capstone's
scope, not a production NER pipeline -- documented as a known limitation
in the Phase 9 roadmap.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

_AMOUNT_RE = re.compile(r"₹\s?[\d,]+(?:\.\d+)?")
# \d+ (not \d{2}) after the point -- a JSON-serialized float like 42115.0
# has only one decimal digit, not the two a formatted "590.00"-style amount
# has; the old \d{2}-only pattern silently missed bare floats in that shape
# (found via LangSmith trace inspection, see Phase_8/docs/08_deployment.md).
_BARE_DECIMAL_AMOUNT_RE = re.compile(r"\b\d{3,}\.\d+\b")
_MASKED_ACCOUNT_RE = re.compile(r"\bX{4,}[\-\s]?\d{2,6}\b")
_LONG_DIGIT_RE = re.compile(r"\b\d{8,}\b")
_PHONE_RE = re.compile(r"\b\d{10}\b")
_EMAIL_RE = re.compile(r"[\w.\-]+@[\w.\-]+\.\w+")

# Reference-ID patterns that are safe to keep (see docstring).
_SAFE_ID_RE = re.compile(r"\b(?:TXN|ACC|DSP|CARD|TCKT)-\d+\b")


def _load_known_names():
    with open(DATA_DIR / "customers.json", encoding="utf-8") as f:
        customers = json.load(f)["customers"]
    return [c["name"] for c in customers]


_KNOWN_NAMES = _load_known_names()


def redact_text(text: str) -> str:
    """Return a PII-scrubbed copy of `text`, safe to write to a log file.
    Never mutates the original -- callers keep operating on the real text;
    only the redacted copy is logged."""
    if not text:
        return text

    # Protect safe reference IDs from the digit-sequence pattern below by
    # temporarily placeholding them, redacting everything else, then
    # restoring them.
    safe_ids = _SAFE_ID_RE.findall(text)
    working = text
    for i, sid in enumerate(safe_ids):
        working = working.replace(sid, f"\0SAFEID{i}\0", 1)

    working = _AMOUNT_RE.sub("[AMOUNT]", working)
    working = _BARE_DECIMAL_AMOUNT_RE.sub("[AMOUNT]", working)
    working = _EMAIL_RE.sub("[EMAIL]", working)
    working = _MASKED_ACCOUNT_RE.sub("[ACCOUNT]", working)
    working = _PHONE_RE.sub("[PHONE]", working)
    working = _LONG_DIGIT_RE.sub("[ACCOUNT]", working)

    for name in _KNOWN_NAMES:
        if name in working:
            working = working.replace(name, "[CUSTOMER_NAME]")
        # also catch a bare first name, common in associate phrasing
        first_name = name.split()[0]
        working = re.sub(rf"\b{re.escape(first_name)}\b", "[CUSTOMER_NAME]", working)

    for i, sid in enumerate(safe_ids):
        working = working.replace(f"\0SAFEID{i}\0", sid, 1)

    return working


if __name__ == "__main__":
    samples = [
        "Customer's asking why she was charged ₹590 on 14 July -- can you check TXN-0076?",
        "Priya Menon's account XXXXXXXX1001 balance is 184230.50, phone 9876543210.",
        "Escalate for Rohan Verma, email rohan.verma@example.com, ticket TCKT-00001.",
    ]
    for s in samples:
        print("IN :", s)
        print("OUT:", redact_text(s))
        print()
