"""
Adaptation decision logic -- reads what src/feedback.py stored and decides
whether/how behaviour should change. Three mechanisms, all bounded and
reversible (capstone_build_plan.md §7):

1. Style adaptation: 2 `too_long` votes from a customer -> terse mode for
   that customer (reuses the Phase 6 preference mechanism directly).
2. Dynamic few-shot injection: handled by feedback.find_similar_correction()
   directly, called from the agent node -- no separate trigger needed here,
   included in this module's docstring for completeness.
3. Escalation-threshold tuning: 2+ negative-feedback votes on a topic ->
   that topic's required confidence to answer directly (rather than
   escalate) rises from the default to a stricter bar.

Reversal: style adaptation reverses by clearing the preference
(memory.forget or a future 👍-based relaxation -- not built here, see
docs/07_adaptation_logic.md for the explicit rollback story). Escalation-
threshold tuning is naturally per-topic and re-evaluated fresh from the
feedback store on every turn, so it silently relaxes again if a topic
stops accumulating negative feedback -- no separate "undo" needed.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import feedback  # noqa: E402
import memory  # noqa: E402

STYLE_ADAPTATION_THRESHOLD = 2
DEFAULT_CONFIDENCE_THRESHOLD = 0.5
STRICT_CONFIDENCE_THRESHOLD = 0.8
ESCALATION_TUNING_TRIGGER = 2


def maybe_adapt_style(customer_id: str) -> bool:
    """Called after any feedback submission. Returns True if this call is
    what flipped the customer into terse mode (for evidence capture)."""
    if memory.get_preferences(customer_id).get("style") == "terse":
        return False  # already adapted, nothing new happened
    too_long_count = feedback.count_reason_for_customer(customer_id, "too_long")
    if too_long_count >= STYLE_ADAPTATION_THRESHOLD:
        memory.set_preference(customer_id, "style", "terse")
        return True
    return False


def process_feedback(
    session_id, customer_id, turn_input, final_response, intent,
    doc_ids_cited, tools_called, signal, reason_code=None, corrected_answer=None,
) -> dict:
    """The single entry point Phase 8's POST /feedback will call: stores
    the feedback record, then checks whether it should trigger the style
    adaptation (the other two mechanisms -- few-shot injection and
    escalation-threshold tuning -- are read fresh from the store on every
    turn by agent_node/confidence_gate, so they need no separate trigger
    here)."""
    record = feedback.submit_feedback(
        session_id, customer_id, turn_input, final_response, intent,
        doc_ids_cited, tools_called, signal, reason_code, corrected_answer,
    )
    style_adapted_now = maybe_adapt_style(customer_id)
    return {"feedback_record": record, "style_adapted_now": style_adapted_now}


def confidence_threshold_for_topic(topic: str) -> float:
    """The bar a turn's answer_json.confidence must clear to be delivered
    directly rather than escalated. Topics with a history of negative
    feedback get a stricter bar -- 'escalates to a human sooner where it
    has historically underperformed.'"""
    if feedback.count_negative_for_topic(topic) >= ESCALATION_TUNING_TRIGGER:
        return STRICT_CONFIDENCE_THRESHOLD
    return DEFAULT_CONFIDENCE_THRESHOLD
