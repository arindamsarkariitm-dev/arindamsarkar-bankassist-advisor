"""
[10] redact_out + log -- write the structured JSONL trace. Per
capstone_build_plan.md §8's logging spec (which supersedes §2's more casual
phrasing): the trace record holds ids, codes, counts, and timing -- NO
message text at all, redacted or not, no names, no account numbers, no
amounts. redact_in/redact_out (src/redaction.py) still exist and are used
in Phase 5's safeguard evidence to prove the redaction pipeline works, but
the production trace log never includes a free-text field in the first
place, which is a stronger guarantee than "redacted text might still leak
something the regex missed."
"""
import hashlib
import json
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRACE_LOG_PATH = ROOT / "logs" / "trace.jsonl"
SESSION_HASH_SALT = "bankassist-advisor-demo-salt"


def _session_hash(customer_id: str) -> str:
    return hashlib.sha256(f"{SESSION_HASH_SALT}:{customer_id}".encode("utf-8")).hexdigest()[:16]


def _outcome(state: dict) -> str:
    if state.get("refusal_code"):
        return "refused"
    if state.get("escalation_code"):
        return "escalated"
    if state.get("route") == "clarify":
        return "clarified"
    return "answered"


def log_node(state: dict) -> dict:
    trace = {
        "trace_id": str(uuid.uuid4()),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "session_hash": _session_hash(state["customer_id"]),
        "intent": state.get("intent"),
        "risk_level": state.get("risk_level"),
        "route": state.get("route"),
        "tools_called": state.get("tools_called", []),
        "tool_call_count": state.get("tool_call_count", 0),
        "doc_ids_cited": state.get("doc_ids_cited", []),
        "refusal_code": state.get("refusal_code"),
        "escalation_code": state.get("escalation_code"),
        "confidence": (state.get("answer_json") or {}).get("confidence"),
        "grounding_ok": state.get("grounding_ok"),
        "regenerate_count": state.get("regenerate_count", 0),
        "outcome": _outcome(state),
        "node_latencies_ms": state.get("node_latencies", {}),
        "total_latency_ms": round(sum((state.get("node_latencies") or {}).values()), 2),
        "token_usage": state.get("token_usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}),
    }
    TRACE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TRACE_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(trace, ensure_ascii=False) + "\n")
    return {"trace": trace}
