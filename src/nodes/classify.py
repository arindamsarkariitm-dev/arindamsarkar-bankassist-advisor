"""[3] classify_intent -- gpt-4o-mini, temperature=0, structured output.
Refined from capstone_build_plan.md §2's illustrative enum to map 1:1 onto
the seven risk-taxonomy categories in docs/01_risk_taxonomy.md, so
policy_gate's routing table has no ambiguous overlap between "check an
existing dispute's status" (account_specific, answerable) and "report a new
fraud" (suspected_fraud, must escalate) -- the original enum's single
"fraud_or_dispute" bucket conflated those two very different behaviours."""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from memory import format_conversation_context  # noqa: E402
from observability import accumulate_tokens  # noqa: E402
from resilience import LLMUnavailable, invoke_structured_with_resilience  # noqa: E402
from state import Intent, RiskLevel  # noqa: E402
from tools._data import customer_instrument_directory  # noqa: E402
from tools.exceptions import AccountServiceUnavailable  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
MODEL = os.environ.get("OPENAI_MODEL_AGENT", "gpt-4o-mini")


class IntentClassification(BaseModel):
    intent: Intent = Field(description="The single best-fitting category for this turn.")
    risk_level: RiskLevel = Field(description="none/low/medium/high, independent of intent category.")
    reasoning: str = Field(description="One short sentence, for tracing only -- never shown to the associate.")


CLASSIFY_SYSTEM_PROMPT = """You classify one contact-centre associate turn for a banking co-pilot.
Categories:
- general_product: a policy/product/fee question with no customer-specific data needed.
- account_specific: needs the customer's own account/transaction/dispute-status data, otherwise benign.
- money_movement: asks to transfer, pay, or move money.
- approval: REQUESTS a new waiver/approval/limit-raise decision. Do NOT use this for a question
  about the STATUS of a decision already made in the past (e.g. "did that fee reversal go
  through?" is account_specific -- checking an existing outcome, not asking for a new one).
- legal_advice: asks for a legal conclusion or opinion.
- suspected_fraud: customer reports transactions/activity they don't recognise, or a security concern.
- hardship: customer is struggling to pay / requesting hardship assistance.
- regulatory_complaint: customer invokes a regulator/ombudsman or a formal complaint.
- deceased_account: the account holder has died.
- vulnerable_or_distress: signs of vulnerability, confusion, or severe distress.
- ambiguous: genuinely unclear which account/item/transaction/dispute is meant, or underspecified.
  You are told below how many accounts/cards/dispute cases this customer actually has -- use that to
  judge ambiguity for real, not generically. "What's the balance?" is ambiguous for a customer with
  2+ accounts/cards, but NOT ambiguous for a customer who only has one thing a "balance" could mean.
  Critically: if the turn ALREADY names a specific account type ("savings account", "credit card",
  "home loan"), it is account_specific even if the customer has other, different instruments too --
  only classify ambiguous when the turn itself doesn't narrow it down to one type. "What's the
  customer's savings account balance?" is account_specific (she has exactly one savings account,
  even though she also has an RD and a credit card); "What's the customer's balance?" (no type
  named) is ambiguous.
  This same test applies one level down, to WHICH transaction or WHICH dispute, not just which
  account: a card or account can be uniquely identified while the specific transaction/charge/
  dispute on it still isn't. "Can you check a charge on her card?" or "customer wants to dispute a
  charge" with no date, amount, merchant, or case reference given is ambiguous whenever that
  instrument could plausibly have more than one matching transaction or dispute case -- guessing
  which one, or silently assuming it means an existing dispute case already on file, is exactly the
  failure this category exists to prevent.
  The turn supplying a specific amount and/or date (e.g. "why was she charged ₹590 on 14 July")
  is enough to skip clarification, even when it doesn't ALSO name which account or card that
  charge is on -- account_specific, not ambiguous. Finding which of the customer's instruments a
  given amount/date belongs to is a search the agent can do with the tools it has (checking
  transaction history per instrument); it is not something that requires asking the associate
  first, the way genuinely not knowing the amount/date/merchant at all does. Only classify
  ambiguous when NONE of amount, date, merchant, or an explicit case/reference id is given at all.
- chitchat: greetings/small talk, no banking content.

You may be given a note about earlier turns THIS SESSION. Use it to resolve pronouns and ellipsis
("and the other one?", "what about her card instead?") against what was actually just discussed --
e.g. if the previous turn was about a savings account balance and this turn says "and the RD?",
that's account_specific (asking about a different, specific, named account), not ambiguous or
chitchat.

risk_level is independent: "high" for anything in suspected_fraud/hardship/regulatory_complaint/
deceased_account/vulnerable_or_distress, "none" for chitchat, "low" or "medium" otherwise based on
how sensitive the topic is.

Classify only. Do not answer the question."""


def classify_intent(state: dict) -> dict:
    try:
        directory = customer_instrument_directory(state["customer_id"])
    except AccountServiceUnavailable:
        # Fail closed immediately, before spending an LLM call on a
        # classification that can't lead anywhere useful without account
        # data. policy_gate routes this straight to service_unavailable_node.
        # capstone_build_plan.md §8: "Account API down -> 'I can't retrieve
        # your account details right now' + escalation. Never estimates."
        return {"account_service_down": True, "intent": "account_specific", "risk_level": "medium"}

    directory_note = f"This customer's accounts/cards/dispute cases on file: {directory}"

    messages = [
        {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
        {"role": "system", "content": directory_note},
    ]
    context_note = format_conversation_context(state)
    if context_note:
        messages.append({"role": "system", "content": context_note})
    messages.append({"role": "user", "content": state["turn_input"]})

    llm = ChatOpenAI(model=MODEL, temperature=0).with_structured_output(IntentClassification, include_raw=True)
    try:
        result, raw_message = invoke_structured_with_resilience(llm, messages)
    except LLMUnavailable:
        return {"llm_service_down": True, "intent": "account_specific", "risk_level": "medium"}
    return {
        "intent": result.intent,
        "risk_level": result.risk_level,
        "classify_reasoning": result.reasoning,
        "token_usage": accumulate_tokens(state, raw_message),
    }
