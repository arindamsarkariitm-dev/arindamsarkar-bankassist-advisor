"""
Phase 2 baseline agent for BankAssist Advisor.

Deliberately bad, on purpose: pure keyword matching against a fixed dictionary
of canned templates. No LLM, no intent classifier, no safety routing, no
retrieval, no memory. Its job is to fail informatively so Phases 3-9 have a
real "before" to improve on -- see docs/02_baseline_limitations.md.

Run directly to execute the golden test set (tests/eval_set.yaml) plus three
extra hand-picked exchanges that demonstrate specific limitations, and write
a JSONL log plus a metrics summary.
"""
import json
import re
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]          # .../Capstone_Project_Arindam Sarkar
DATA_DIR = ROOT / "data"
EVAL_SET_PATH = ROOT / "tests" / "eval_set.yaml"
LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "phase2_baseline_runs.jsonl"


def load_json(name):
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


CUSTOMERS = load_json("customers.json")


def get_customer(customer_id):
    return next((c for c in CUSTOMERS["customers"] if c["customer_id"] == customer_id), None)


def get_account(account_id):
    return next((a for a in CUSTOMERS["accounts"] if a["account_id"] == account_id), None)


# ---------------------------------------------------------------------------
# Rule handlers. Each one is a canned template, with at most a naive regex
# grab for an amount already present in the input text. None of them verify
# anything against real tool output, none of them refuse, none of them ask
# a clarifying question, and none of them remember a prior turn.
# ---------------------------------------------------------------------------

def handle_transfer(text, customer_id):
    m = re.search(r"₹\s?([\d,]+)", text)
    amount = m.group(1) if m else "the requested amount"
    return f"Sure, I can help transfer ₹{amount}. Please confirm the recipient account and I'll process it."


def handle_waive(text, customer_id):
    return ("I can look into waiving that for you. I've noted it down as approved on our end, "
            "pending final confirmation.")


def handle_balance(text, customer_id):
    # BAD: ignores whatever account/product was actually named in the text and
    # always returns whichever account happens to be first in the customer's list.
    cust = get_customer(customer_id) if customer_id else None
    if not cust or not cust["accounts"]:
        return "I'm sorry, I don't have information about that. Please contact customer support."
    acc = get_account(cust["accounts"][0])
    return f"Your balance is ₹{acc.get('balance', acc.get('outstanding_principal', 'N/A'))}."


def handle_fee_charge(text, customer_id):
    m = re.search(r"₹\s?([\d,]+(?:\.\d+)?)", text)
    if m:
        return f"This appears to be a standard fee of ₹{m.group(1)}. Please refer to our fee schedule for details."
    return "That looks like a standard fee. Please refer to our fee schedule for details."


def handle_emi(text, customer_id):
    return "EMI amounts depend on your loan's principal, interest rate, and tenure. Please refer to your loan documents."


def handle_dispute(text, customer_id):
    return "To raise a dispute, please provide the transaction details and our team will look into it within a few business days."


def handle_documents(text, customer_id):
    return "Standard documents required include identity proof, address proof, and income proof."


def handle_interest(text, customer_id):
    # BAD: answers ANY interest-rate question with the savings slab rates,
    # confidently, even if the product asked about doesn't exist. No abstention.
    return "Our savings account offers interest rates from 3.00% to 4.00% per annum depending on your balance slab."


def handle_limit(text, customer_id):
    return "Standard UPI transfer limits are typically around ₹1,00,000 per transaction."


FALLBACK = "I'm sorry, I don't have information about that. Please contact customer support for further assistance."

# Order matters: first keyword list that matches wins. Deliberately narrow
# phrasing (e.g. "was charged" but not the bare word "charge") to demonstrate
# brittle intent matching on rephrased-but-equivalent questions.
RULES = [
    (["transfer", "send money", "process this", "neft payment"], handle_transfer),
    (["waive", "can you approve", "raise my limit", "raise the customer's credit card limit",
      "approve her home loan", "approve the customer"], handle_waive),
    (["was charged", "charged me", "charged on", "charged ₹"], handle_fee_charge),
    (["balance"], handle_balance),
    (["emi"], handle_emi),
    (["dispute"], handle_dispute),
    (["document", "checklist"], handle_documents),
    (["interest rate"], handle_interest),
    (["upi", "send via upi"], handle_limit),
]


def baseline_respond(text, customer_id=None):
    lowered = text.lower()
    for keywords, handler in RULES:
        if any(kw in lowered for kw in keywords):
            return handler(text, customer_id), handler.__name__
    return FALLBACK, "fallback"


# ---------------------------------------------------------------------------
# Runner: golden test set + three hand-picked limitation-demonstration turns.
# ---------------------------------------------------------------------------

def run_eval_set():
    with open(EVAL_SET_PATH, encoding="utf-8") as f:
        cases = yaml.safe_load(f)["cases"]

    records = []
    for case in cases:
        customer_id = case["context"].get("customer_id")
        t0 = time.perf_counter()
        response, rule = baseline_respond(case["input"], customer_id)
        latency_ms = (time.perf_counter() - t0) * 1000
        lowered_response = response.lower()
        must_contain_ok = all(s.lower() in lowered_response for s in case["must_contain"])
        must_not_contain_ok = all(s.lower() not in lowered_response for s in case["must_not_contain"])
        passed = must_contain_ok and must_not_contain_ok
        records.append({
            "source": "eval_set",
            "case_id": case["id"],
            "bucket": case["bucket"],
            "input": case["input"],
            "customer_id": customer_id,
            "matched_rule": rule,
            "response": response,
            "expected_behaviour": case["expected_behaviour"],
            "must_contain_ok": must_contain_ok,
            "must_not_contain_ok": must_not_contain_ok,
            "passed": passed,
            "latency_ms": round(latency_ms, 3),
        })
    return records


def run_limitation_demos():
    """Three extra, hand-picked exchanges illustrating specific failure modes
    called out in capstone_build_plan.md Phase 2: brittle intent matching,
    no abstention, and no multi-turn state."""
    records = []

    # 1. Brittle intent matching: same underlying question, two phrasings.
    for label, text in [
        ("brittle_matching_hit", "Why was she charged ₹590 on 14 July?"),
        ("brittle_matching_miss", "There's a charge on her account she doesn't recognise."),
    ]:
        response, rule = baseline_respond(text, "CUST-0001")
        records.append({
            "source": "limitation_demo", "demo": "brittle_intent_matching", "label": label,
            "input": text, "customer_id": "CUST-0001", "matched_rule": rule, "response": response,
        })

    # 2. No abstention: a product that does not exist in the corpus still gets
    # a confident, specific-sounding answer.
    text = "What's the interest rate on your crypto savings product?"
    response, rule = baseline_respond(text, None)
    records.append({
        "source": "limitation_demo", "demo": "no_abstention", "label": "confident_wrong_answer",
        "input": text, "customer_id": None, "matched_rule": rule, "response": response,
    })

    # 3. No multi-turn state: a natural two-turn exchange about the same customer.
    turn1 = "What's the customer's savings account balance?"
    r1, rule1 = baseline_respond(turn1, "CUST-0002")
    records.append({
        "source": "limitation_demo", "demo": "no_multiturn_state", "label": "turn_1",
        "input": turn1, "customer_id": "CUST-0002", "matched_rule": rule1, "response": r1,
    })
    turn2 = "And the home loan account?"
    r2, rule2 = baseline_respond(turn2, "CUST-0002")
    records.append({
        "source": "limitation_demo", "demo": "no_multiturn_state", "label": "turn_2",
        "input": turn2, "customer_id": "CUST-0002", "matched_rule": rule2, "response": r2,
    })

    return records


def main():
    eval_records = run_eval_set()
    demo_records = run_limitation_demos()
    all_records = eval_records + demo_records

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        for r in all_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    total = len(eval_records)
    passed = sum(1 for r in eval_records if r["passed"])

    def bucket_rate(bucket_prefix):
        bucket_cases = [r for r in eval_records if r["bucket"].startswith(bucket_prefix)]
        if not bucket_cases:
            return None
        return sum(1 for r in bucket_cases if r["passed"]) / len(bucket_cases)

    print(f"Overall pass rate: {passed}/{total} = {passed/total:.1%}")
    print(f"M2 proxy - prohibited-intent refusal recall "
          f"(prohibited_money_movement + prohibited_approval + prohibited_legal_advice): "
          f"{bucket_rate('prohibited'):.1%}")
    print(f"M4 proxy - escalation recall (high_risk_escalate): {bucket_rate('high_risk_escalate'):.1%}")
    print(f"M9 proxy - abstention correctness (unanswerable): {bucket_rate('unanswerable'):.1%}")
    print(f"Ambiguous-bucket clarify rate (ambiguous): {bucket_rate('ambiguous'):.1%}")
    print(f"General-product-Q pass rate (general_product): {bucket_rate('general_product'):.1%}")
    print(f"Account-specific-Q pass rate (account_specific): {bucket_rate('account_specific'):.1%}")
    p95_latency = sorted(r["latency_ms"] for r in eval_records)[int(0.95 * (total - 1))]
    print(f"M8 proxy - p95 latency: {p95_latency:.3f} ms")
    print(f"Log written to: {LOG_PATH}")


if __name__ == "__main__":
    main()
