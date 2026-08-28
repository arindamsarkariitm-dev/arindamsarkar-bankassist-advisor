"""Terminal-ish nodes: refuse_node, escalate_node, clarify_node.

Deliberately NOT LLM-generated for refuse_node -- deterministic, fixed
wording per category. A hardcoded refusal cannot drift into the
legal-advice-adjacent territory Phase 3 caught P2 doing (evidence/03_prompt_comparison.md);
a canned string has no attack surface for a rephrased jailbreak to work on."""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import memory  # noqa: E402
from observability import accumulate_tokens  # noqa: E402
from resilience import LLMUnavailable, invoke_with_retry  # noqa: E402
from tools._data import customer_instrument_directory  # noqa: E402
from tools.exceptions import AccountServiceUnavailable  # noqa: E402
from tools.registry import build_toolset  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
MODEL = os.environ.get("OPENAI_MODEL_AGENT", "gpt-4o-mini")

REFUSAL_MESSAGES = {
    "money_movement": (
        "I can't process transfers or move money through this system. "
        "Please direct the customer to the bank's authenticated transfer flow (app, "
        "net banking, or branch) to complete this."
    ),
    "approval": (
        "I can't waive fees, I can't approve requests, and I can't raise limits on the bank's "
        "behalf -- that decision is made by a human team based on the bank's published criteria. "
        "I can explain the relevant criteria and process, and escalate this to that team "
        "if the customer wants it reviewed."
    ),
    "legal_advice": (
        "I can't give legal advice on this. I'd recommend the customer consult "
        "a qualified legal professional for a definitive answer. I can share general, "
        "non-legal information about the bank's relevant policy if that would help."
    ),
}


def refuse_node(state: dict) -> dict:
    intent = state["intent"]
    return {
        "final_response": REFUSAL_MESSAGES[intent],
        "refusal_code": intent,
    }


ESCALATION_TEAM_BY_INTENT = {
    "suspected_fraud": "Fraud",
    "hardship": "Hardship & Collections",
    "regulatory_complaint": "Complaints & Compliance",
    "deceased_account": "Bereavement & Estate",
    "vulnerable_or_distress": "Specialist Care",
}


def escalate_node(state: dict) -> dict:
    intent = state["intent"]
    team = ESCALATION_TEAM_BY_INTENT.get(intent, "Specialist")
    tools = {t.name: t for t in build_toolset(state["customer_id"])}
    ticket = tools["create_escalation_ticket"].invoke({
        "category": intent,
        "summary": f"Escalated from associate turn, risk_level={state['risk_level']}.",
        "redacted_ctx": state.get("redacted_input_for_log", ""),
    })
    message = f"I'm escalating this to our {team} team rather than handling it here -- I've raised ticket {ticket['ticket_id']} for it."
    if intent == "deceased_account":
        message = (
            "I'm very sorry for the loss. I can't continue discussing this account "
            f"with the caller -- I'm escalating this to our {team} team. "
            f"I've raised ticket {ticket['ticket_id']}."
        )
    return {
        "final_response": message,
        "escalation_code": intent,
        "escalation_ticket": ticket,
    }


def forget_node(state: dict) -> dict:
    """Handles the /forget command: clears both short-term (this session)
    and long-term (this customer's preferences) memory. Bypasses
    classify/policy_gate/agent entirely -- this is a memory-management
    command, not a banking question."""
    memory.forget(state["session_id"], state["customer_id"], clear_long_term=True)
    return {
        "final_response": "Done -- I've cleared this session's memory and this customer's saved preferences.",
        "intent": "chitchat",
        "risk_level": "none",
        "route": "proceed",
    }


def service_unavailable_node(state: dict) -> dict:
    """capstone_build_plan.md §8, "Account API down" / "LLM timeout / 429":
    policy_gate routed here because classify_intent couldn't complete --
    either the account data lookup or the LLM call itself failed (after its
    one retry). create_escalation_ticket itself doesn't need account data
    or another LLM call (only customer_id, which is already verified
    session context, and a fixed category/summary), so escalation still
    works even though the thing that actually broke can't."""
    is_llm_failure = bool(state.get("llm_service_down"))
    category = "llm_service_unavailable" if is_llm_failure else "account_service_unavailable"
    message = (
        "I'm having trouble processing this right now, so I don't want to guess."
        if is_llm_failure else
        "I can't retrieve your account details right now."
    )
    tools = {t.name: t for t in build_toolset(state["customer_id"])}
    ticket = tools["create_escalation_ticket"].invoke({
        "category": category,
        "summary": f"{'LLM' if is_llm_failure else 'Account data'} service was unavailable "
                   f"when this turn was processed.",
        "redacted_ctx": state.get("redacted_input_for_log", ""),
    })
    return {
        "final_response": f"{message} I've raised ticket {ticket['ticket_id']} so this can be followed up.",
        "escalation_code": category,
        "escalation_ticket": ticket,
    }


def answer_to_response_node(state: dict) -> dict:
    """Grounding check passed (possibly after one regenerate). Turn the
    structured answer_json into the associate-facing final_response."""
    return {"final_response": state["answer_json"]["answer"]}


def low_confidence_escalate_node(state: dict) -> dict:
    """The answer was grounded, but its own confidence fell below a
    threshold that's been raised for this topic due to repeated negative
    feedback (Phase 7, escalation-threshold tuning). The answer itself is
    suppressed -- delivering a low-confidence answer on a topic already
    known to be troublesome is exactly the failure mode this mechanism
    exists to prevent."""
    tools = {t.name: t for t in build_toolset(state["customer_id"])}
    topic = state.get("confidence_gate_topic", "unknown")
    ticket = tools["create_escalation_ticket"].invoke({
        "category": "low_confidence_on_flagged_topic",
        "summary": f"Answer confidence below the tuned threshold for topic '{topic}' "
                   f"(history of negative feedback on this topic).",
        "redacted_ctx": state.get("redacted_input_for_log", ""),
    })
    return {
        "final_response": (
            "I have an answer, but my confidence in it is low for this particular topic -- "
            f"this area has had trouble before, so I'd rather get it checked. I've raised "
            f"ticket {ticket['ticket_id']}."
        ),
        "escalation_code": "low_confidence_on_flagged_topic",
        "escalation_ticket": ticket,
    }


def fail_closed_node(state: dict) -> dict:
    """verify_grounding gave up after the one allowed regenerate. Suppress
    the ungrounded answer entirely and escalate -- capstone_build_plan.md §8's
    degradation matrix: 'Grounding verifier fails twice -> Suppress the
    answer entirely, escalate. Fail closed.'"""
    tools = {t.name: t for t in build_toolset(state["customer_id"])}
    ticket = tools["create_escalation_ticket"].invoke({
        "category": "grounding_verification_failed",
        "summary": "Could not produce a fully grounded answer after one regenerate attempt.",
        "redacted_ctx": state.get("redacted_input_for_log", ""),
    })
    return {
        "final_response": (
            "I can't confirm that answer against verified data right now, so I don't want to "
            f"guess. I've raised ticket {ticket['ticket_id']} to get this looked at properly."
        ),
        "escalation_code": "grounding_verification_failed",
        "escalation_ticket": ticket,
    }


def clarify_node(state: dict) -> dict:
    try:
        directory = customer_instrument_directory(state["customer_id"])
    except AccountServiceUnavailable:
        # A narrow race: the account service was up when classify_intent
        # checked it, but went down before we got here. Fail safe with a
        # generic clarifying question rather than crash.
        directory = []

    llm = ChatOpenAI(model=MODEL, temperature=0)
    messages = [
        {"role": "system", "content": (
            "The associate's request below is ambiguous for THIS customer, who is already "
            "known (the ambiguity is never about which customer). Here is what's ambiguous "
            f"between -- this customer's accounts/cards/dispute cases on file: {directory}. "
            "Also, why the classifier flagged it ambiguous: "
            f"{state.get('classify_reasoning', '')!r}. "
            "Ask EXACTLY ONE short, specific clarifying question that would resolve it (e.g. "
            "naming the specific account types to choose between). Do not answer anything, "
            "do not apologise at length, just ask the one question."
        )},
        {"role": "user", "content": state["turn_input"]},
    ]
    try:
        resp = invoke_with_retry(llm, messages)
    except LLMUnavailable:
        return {"final_response": "Could you clarify exactly which account or item you mean?"}
    return {"final_response": resp.content, "token_usage": accumulate_tokens(state, resp)}
