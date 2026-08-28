"""Shared state schema for the BankAssist Advisor LangGraph StateGraph."""
from typing import Literal, TypedDict

Intent = Literal[
    "general_product", "account_specific", "money_movement", "approval",
    "legal_advice", "suspected_fraud", "hardship", "regulatory_complaint",
    "deceased_account", "vulnerable_or_distress", "ambiguous", "chitchat",
]
RiskLevel = Literal["none", "low", "medium", "high"]
Route = Literal["refuse", "escalate", "clarify", "proceed", "service_unavailable"]

REFUSE_INTENTS = {"money_movement", "approval", "legal_advice"}
ESCALATE_INTENTS = {
    "suspected_fraud", "hardship", "regulatory_complaint",
    "deceased_account", "vulnerable_or_distress",
}


class GraphState(TypedDict, total=False):
    # ingest
    turn_input: str
    customer_id: str
    locale: str
    session_id: str
    is_forget_command: bool
    account_service_down: bool
    llm_service_down: bool

    # load_memory (Phase 6)
    short_term_turns: list[dict]
    rolling_summary: str
    preferences: dict

    # redact_in
    redacted_input_for_log: str

    # classify_intent
    intent: Intent
    risk_level: RiskLevel
    classify_reasoning: str

    # policy_gate
    route: Route

    # plan (Phase 6)
    plan: dict

    # agent / tool loop
    messages: list  # LangChain message objects, the agent scratchpad
    tool_call_count: int
    tool_call_hashes: list[str]
    tools_called: list[str]
    doc_ids_cited: list[str]
    tool_error: str | None

    # compose output (structured)
    answer_json: dict

    # verify_grounding
    grounding_ok: bool
    regenerate_count: int

    # confidence_gate (Phase 7)
    confidence_gate_topic: str
    confidence_gate_threshold: float
    confidence_below_threshold: bool

    # terminal
    final_response: str
    refusal_code: str | None
    escalation_code: str | None
    escalation_ticket: dict | None

    # observability (Phase 8)
    node_latencies: dict
    token_usage: dict

    # redact_out + log
    trace: dict
