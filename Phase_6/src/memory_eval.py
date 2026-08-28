"""
Phase 6 evidence generation: three annotated multi-turn conversations
(pronoun/ellipsis resolution, 5-turn context carry-over, topic switch
without bleed), a memory-reset (/forget) before/after proof, and a
planning-trace capture. All real graph runs, logged verbatim.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import memory  # noqa: E402
from graph import run_turn  # noqa: E402

LOG_DIR = Path(__file__).resolve().parents[1] / "logs"


def run_conversation(label, customer_id, turns):
    sid = None
    records = []
    for t in turns:
        result = run_turn(t, customer_id, session_id=sid)
        sid = result["session_id"]
        records.append({
            "input": t,
            "intent": result.get("intent"),
            "route": result.get("route"),
            "tools_called": result.get("tools_called", []),
            "final_response": result.get("final_response"),
        })
    return {"label": label, "customer_id": customer_id, "session_id": sid, "turns": records}


def main():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    conversations = {}

    # 1. Pronoun / ellipsis resolution.
    conversations["pronoun_ellipsis"] = run_conversation(
        "Pronoun/ellipsis resolution", "CUST-0001",
        [
            "What's the customer's savings account balance?",
            "And the RD?",
            "What about her credit card?",
        ],
    )

    # 2. Context carry-over across 5 turns.
    conversations["five_turn_carryover"] = run_conversation(
        "Context carry-over across 5 turns", "CUST-0002",
        [
            "What's the customer's savings account balance?",
            "When was that account opened?",
            "Does he have any other accounts?",
            "What's the outstanding balance on that one?",
            "And what's the interest rate on it?",
        ],
    )

    # 3. Topic switch without bleed.
    conversations["topic_switch"] = run_conversation(
        "Topic switch without bleed", "CUST-0001",
        [
            "What's the customer's savings account balance?",
            "What's the late payment fee on a credit card?",
            "Going back to her account -- what's the balance again?",
        ],
    )

    with open(LOG_DIR / "06_multiturn_conversations.json", "w", encoding="utf-8") as f:
        json.dump(conversations, f, ensure_ascii=False, indent=2)

    for key, convo in conversations.items():
        print(f"=== {convo['label']} ===")
        for t in convo["turns"]:
            print(f"  > {t['input']}")
            print(f"    intent={t['intent']} tools={t['tools_called']}")
            print(f"    {t['final_response']}")
        print()

    # 4. Memory reset (/forget) proof, on the topic_switch session.
    reset_sid = conversations["topic_switch"]["session_id"]
    memory.set_preference("CUST-0001", "style", "terse")  # so preference-clearing is provable too
    before = {
        "session": memory.dump_session(reset_sid),
        "preferences": memory.get_preferences("CUST-0001"),
    }
    forget_result = run_turn("/forget", "CUST-0001", session_id=reset_sid)
    after = {
        "session": memory.dump_session(reset_sid),
        "preferences": memory.get_preferences("CUST-0001"),
    }
    reset_proof = {
        "forget_response": forget_result.get("final_response"),
        "before": before,
        "after": after,
    }
    with open(LOG_DIR / "06_memory_reset_proof.json", "w", encoding="utf-8") as f:
        json.dump(reset_proof, f, ensure_ascii=False, indent=2, default=str)
    print("=== Memory reset proof ===")
    print("Before turns count:", len(before["session"]["turns"]) if before["session"] else 0)
    print("Before preferences:", before["preferences"])
    print("/forget response:", forget_result.get("final_response"))
    print("After session:", after["session"])
    print("After preferences:", after["preferences"])
    print()

    # 5. Planning trace.
    plan_result = run_turn(
        "Compare the customer's savings account balance and her credit card's available "
        "credit limit, and tell me which is higher.",
        "CUST-0001",
    )
    with open(LOG_DIR / "06_planning_trace.json", "w", encoding="utf-8") as f:
        json.dump({
            "input": plan_result.get("turn_input") or "Compare the customer's savings account "
                     "balance and her credit card's available credit limit, and tell me which is higher.",
            "plan": plan_result.get("plan"),
            "tools_called": plan_result.get("tools_called"),
            "final_response": plan_result.get("final_response"),
        }, f, ensure_ascii=False, indent=2)
    print("=== Planning trace ===")
    print(json.dumps(plan_result.get("plan"), indent=2))
    print("final_response:", plan_result.get("final_response"))

    print(f"\nAll logs written to: {LOG_DIR}")


if __name__ == "__main__":
    main()
