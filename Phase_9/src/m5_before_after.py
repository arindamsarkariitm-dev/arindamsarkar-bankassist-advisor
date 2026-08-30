"""
[Phase 9] Honest before/after measurement of M5 (retrieval hit@3) for the
stale-fee fix, reusing the exact 20 labelled queries from
Phase_4/evidence/04_retrieval_eval.md. "Before" is simulated by
monkeypatching retriever._filter_superseded() to a no-op for that pass only
(the real pre-fix code is gone, correctly, but this reproduces its exact
observable behaviour) -- both passes call the same retrieve() function, so
this is an apples-to-apples comparison, not two different code paths.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import retriever  # noqa: E402

LABELLED_QUERIES = [
    ("What's the daily ATM withdrawal limit on a debit card?", "debit-card-terms"),
    ("How do I block a lost or stolen debit card?", "debit-card-terms"),
    ("When is the minimum amount due on a credit card bill?", "credit-card-terms"),
    ("What happens if I withdraw cash using my credit card?", "credit-card-terms"),
    ("How long does it take to resolve a disputed transaction?", "dispute-chargeback-procedure"),
    ("What evidence do I need to raise a dispute?", "dispute-chargeback-procedure"),
    ("What documents are needed for a home loan application?", "home-loan-document-checklist"),
    ("What's the minimum credit score for home loan eligibility?", "home-loan-document-checklist"),
    ("How often do I need to complete re-KYC?", "kyc-requirements"),
    ("What happens if I don't complete KYC on time?", "kyc-requirements"),
    ("What's the interest rate on a fixed deposit?", "savings-interest-policy"),
    ("How is savings account interest calculated?", "savings-interest-policy"),
    ("What's the maximum amount I can send via IMPS?", "upi-neft-imps-limits"),
    ("Is there a fee for NEFT transfers?", "upi-neft-imps-limits"),
    ("How do I escalate a complaint to the banking ombudsman?", "complaint-escalation-matrix"),
    ("What's the response time for a Level 2 complaint escalation?", "complaint-escalation-matrix"),
    ("What options are available if I can't pay my EMI due to job loss?", "financial-hardship-policy"),
    ("What documents are needed to apply for an EMI moratorium?", "financial-hardship-policy"),
    ("What's the late payment fee on a credit card?", "fee-schedule"),
    ("How much does it cost to replace a lost debit card?", "fee-schedule"),
]


def _identity(candidates):
    return candidates


def score(label):
    hit1 = hit3 = 0
    rr_sum = 0.0
    conflicting_pairs = 0
    for query, expected in LABELLED_QUERIES:
        results = retriever.retrieve(query)
        doc_ids = [r["metadata"]["doc_id"] for r in results]
        statuses = [r["metadata"]["status"] for r in results]
        if expected in doc_ids:
            rank = doc_ids.index(expected) + 1
            if rank == 1:
                hit1 += 1
            if rank <= 3:
                hit3 += 1
            rr_sum += 1.0 / rank
        if "superseded" in statuses and "current" in statuses:
            conflicting_pairs += 1
    n = len(LABELLED_QUERIES)
    print(f"[{label}] hit@1={hit1}/{n} ({100*hit1/n:.1f}%)  hit@3={hit3}/{n} ({100*hit3/n:.1f}%)  "
          f"MRR={rr_sum/n:.3f}  queries with a superseded+current pair in the SAME result set: {conflicting_pairs}/{n}")
    return hit1, hit3, rr_sum / n, conflicting_pairs


_real_filter = retriever._filter_superseded
retriever._filter_superseded = _identity
before = score("BEFORE (superseded-filter bypassed, reproduces the planted-bug behaviour)")
retriever._filter_superseded = _real_filter
after = score("AFTER  (fix applied)")
