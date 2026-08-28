"""[4] policy_gate -- HARD RULES, pre-LLM (well, post-classification, but
pre-compose). This is deterministic code, not prompt text: exactly the fix
Phase 3 identified as missing (evidence/03_prompt_comparison.md found both
P2 and P3 skip the required clarifying question when a case is ambiguous
AND touches an escalation keyword like "dispute" -- the precedence is now
enforced here in code instead of hoped for from prompt wording).

Precedence, in order: service_unavailable > refuse > escalate > clarify >
proceed. A refuse-worthy request always refuses even if also ambiguous
(e.g. "transfer some money to one of my accounts" refuses regardless of
which account). Escalate beats clarify, because escalation-worthy
situations must never wait on a clarifying question the associate might
not even get to ask. service_unavailable beats everything, since none of
the other routes can be trusted to work correctly without account data."""
from state import ESCALATE_INTENTS, REFUSE_INTENTS


def policy_gate(state: dict) -> dict:
    if state.get("account_service_down") or state.get("llm_service_down"):
        return {"route": "service_unavailable"}

    intent = state["intent"]
    risk_level = state["risk_level"]

    if intent in REFUSE_INTENTS:
        return {"route": "refuse"}
    if intent in ESCALATE_INTENTS or risk_level == "high":
        return {"route": "escalate"}
    if intent == "ambiguous":
        return {"route": "clarify"}
    return {"route": "proceed"}
