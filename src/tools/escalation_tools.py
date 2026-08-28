"""
Escalation tool: create_escalation_ticket -- the ONE deliberate write in the
whole system (capstone_build_plan.md §2's "one deliberate carve-out"). It
writes to data/escalation_queue.jsonl, an internal ticket queue, and NEVER
to customer or financial records; there is no tool anywhere in this package
that can modify a balance, a transaction, or an account.

`redacted_ctx` is expected to already be PII-free -- redaction happens
upstream (src/redaction.py, in the graph's redact_in node), not here. This
tool additionally salt-hashes customer_id rather than storing it raw, so
the ticket queue itself never holds a plain customer identifier.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.tools import tool

from .schemas import TicketRef

ROOT = Path(__file__).resolve().parents[2]
QUEUE_PATH = ROOT / "data" / "escalation_queue.jsonl"
HASH_SALT = "bankassist-advisor-demo-salt"  # placeholder; a real deployment reads this from a secret store


def _hash_customer_id(customer_id: str) -> str:
    return hashlib.sha256(f"{HASH_SALT}:{customer_id}".encode("utf-8")).hexdigest()[:16]


def _next_ticket_id() -> str:
    n = 0
    if QUEUE_PATH.exists():
        with open(QUEUE_PATH, encoding="utf-8") as f:
            n = sum(1 for _ in f)
    return f"TCKT-{n + 1:05d}"


def make_create_escalation_ticket_tool(customer_id: str):
    @tool
    def create_escalation_ticket(category: str, summary: str, redacted_ctx: str) -> dict:
        """Create an escalation ticket, routing the case to the right
        internal team (e.g. fraud, disputes, hardship/collections,
        compliance). `category` should be one of the risk-taxonomy
        categories (see docs/01_risk_taxonomy.md). `summary` and
        `redacted_ctx` must already have PII removed -- never pass raw
        customer names, account numbers, or amounts here. This is the only
        tool in the system that writes anything, and it writes only to the
        internal escalation queue, never to customer or financial records."""
        ticket_id = _next_ticket_id()
        created_at = datetime.now(timezone.utc).isoformat()
        record = {
            "ticket_id": ticket_id,
            "created_at": created_at,
            "category": category,
            "summary": summary,
            "redacted_ctx": redacted_ctx,
            "customer_id_hash": _hash_customer_id(customer_id),
        }
        QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(QUEUE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        return TicketRef(
            ticket_id=ticket_id, category=category, created_at=created_at, summary=summary,
        ).model_dump()

    return create_escalation_ticket
