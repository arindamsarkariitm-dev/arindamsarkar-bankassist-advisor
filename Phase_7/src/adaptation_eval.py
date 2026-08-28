"""
Phase 7 evidence generation: real before/after runs for all three
adaptation mechanisms (style, dynamic few-shot injection, escalation-
threshold tuning), against a freshly-cleared feedback store so each
demonstration is clean and unconfounded by earlier ad hoc testing.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import memory  # noqa: E402
from graph import give_feedback, run_turn  # noqa: E402

LOG_DIR = Path(__file__).resolve().parents[1] / "logs"


def brief(result):
    return {
        "input": result.get("turn_input"),
        "intent": result.get("intent"),
        "confidence": (result.get("answer_json") or {}).get("confidence"),
        "confidence_gate_threshold": result.get("confidence_gate_threshold"),
        "confidence_below_threshold": result.get("confidence_below_threshold"),
        "final_response": result.get("final_response"),
        "tools_called": result.get("tools_called"),
    }


def demo_style_adaptation():
    cust = "CUST-0001"
    q = "What's the late payment fee on a credit card, and what happens if a payment is missed?"

    before = run_turn(q, cust)
    memory.forget(before["session_id"], cust)  # start each probe from a clean session, preference store untouched

    fb1 = give_feedback(before, cust, signal="down", reason_code="too_long")
    prefs_after_1_vote = memory.get_preferences(cust)  # captured immediately, not after later forget() calls
    r2 = run_turn(q, cust)
    memory.forget(r2["session_id"], cust)
    fb2 = give_feedback(r2, cust, signal="down", reason_code="too_long")
    prefs_after_2_votes = memory.get_preferences(cust)  # ditto

    after = run_turn(q, cust)
    memory.forget(after["session_id"], cust)

    result = {
        "before": brief(before),
        "after_1_vote": {"style_adapted_now": fb1["style_adapted_now"], "preferences": prefs_after_1_vote},
        "after_2_votes": {"style_adapted_now": fb2["style_adapted_now"], "preferences": prefs_after_2_votes},
        "after": brief(after),
    }
    memory.forget(memory.new_session_id(), cust)  # clear the terse preference so it doesn't leak into later demos
    return result


def demo_few_shot_injection():
    cust = "CUST-0002"
    priming_q = "What's the annual maintenance fee on a debit card?"
    similar_q = "What's the joining fee on a credit card?"

    before_similar = run_turn(similar_q, cust)
    memory.forget(before_similar["session_id"], cust)

    priming_result = run_turn(priming_q, cust)
    memory.forget(priming_result["session_id"], cust)
    correction = (
        "The annual maintenance fee on a debit card is Rs.295 + GST, per fee-schedule "
        "(doc_id: fee-schedule, effective_date: 2026-01-01). Always name the doc_id and "
        "effective_date explicitly when quoting any fee, since more than one version of the "
        "fee schedule exists and naming which one prevents ever quoting a stale rate."
    )
    give_feedback(priming_result, cust, signal="down", reason_code="not_grounded", corrected_answer=correction)

    after_similar = run_turn(similar_q, cust)
    memory.forget(after_similar["session_id"], cust)

    return {
        "priming_question": priming_q,
        "priming_answer_before_correction": brief(priming_result),
        "correction_submitted": correction,
        "similar_question": similar_q,
        "before_correction_exists": brief(before_similar),
        "after_correction_exists": brief(after_similar),
    }


def demo_escalation_threshold_tuning():
    # NOTE: this deliberately uses an account-lookup question (get_account_summary),
    # not a policy/RAG question. derive_topic() falls back doc_ids_cited -> tools_called
    # -> intent; for a policy question, doc_ids_cited is only populated when retrieval
    # actually returns a result, which is the same intermittent flakiness already
    # documented in Phase 4/5 (evidence/04_retrieval_eval.md, evidence/05_regression_summary.md)
    # -- an early attempt at this demo used a policy question and got a DIFFERENT derived
    # topic across runs purely because retrieval succeeded on one call and not another,
    # which silently broke the "same topic accumulates feedback" assumption. Account tools
    # have been reliable all project, so tools_called is a stable topic key here.
    cust = "CUST-0003"
    q = "What's the customer's savings account balance?"

    before = run_turn(q, cust)
    memory.forget(before["session_id"], cust)

    give_feedback(before, cust, signal="down", reason_code="unhelpful")
    r2 = run_turn(q, cust)
    memory.forget(r2["session_id"], cust)
    give_feedback(r2, cust, signal="down", reason_code="unhelpful")

    after = run_turn(q, cust)
    memory.forget(after["session_id"], cust)

    return {"before": brief(before), "after_2_negative_votes": brief(after)}


def demo_confidence_gate_direct():
    """Real LLM answers tend to self-report confidence near 1.0 (confident)
    or 0.0 (abstaining), rarely something conveniently in the 0.5-0.8 gap
    the two thresholds straddle -- so proving the threshold change actually
    changes the routing DECISION, not just the stored number, needs a
    direct test with a constructed borderline confidence, the same pattern
    Phase 5 used for the max-5-calls/no-repeat-call safeguards."""
    from nodes.confidence_gate import confidence_gate

    borderline_state = {"intent": "account_specific", "doc_ids_cited": [],
                         "tools_called": ["get_account_summary"], "answer_json": {"confidence": 0.65}}

    fresh_topic_result = confidence_gate(dict(borderline_state, tools_called=["check_dispute_status"]))
    flagged_topic_result = confidence_gate(borderline_state)  # topic tuned by demo_escalation_threshold_tuning above

    return {
        "borderline_confidence": 0.65,
        "fresh_topic (check_dispute_status, never flagged)": fresh_topic_result,
        "flagged_topic (get_account_summary, 2 negative votes from the demo above)": flagged_topic_result,
    }


def main():
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    results = {
        "style_adaptation": demo_style_adaptation(),
        "few_shot_injection": demo_few_shot_injection(),
        "escalation_threshold_tuning": demo_escalation_threshold_tuning(),
    }
    results["escalation_threshold_tuning_direct_test"] = demo_confidence_gate_direct()
    with open(LOG_DIR / "07_adaptation_demos.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nWritten to {LOG_DIR / '07_adaptation_demos.json'}")


if __name__ == "__main__":
    main()
