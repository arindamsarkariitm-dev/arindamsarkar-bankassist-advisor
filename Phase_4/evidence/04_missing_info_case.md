# Phase 4 — Missing-Info Case: the Crypto Savings Question

**Question:** "What's the interest rate on your crypto savings product?" — no such product exists anywhere in the 11-document policy corpus; the bank only offers standard savings, RD, and FD products.

## What actually happens (floor = 0.35, real run)

The retriever does **not** cleanly return zero results — this is the same leakage documented in `evidence/04_retrieval_eval.md`. Three chunks clear the 0.35 floor:

| doc_id | score | Why it matched at all |
|---|---|---|
| `savings-interest-policy` | 0.491 | Topically closest — it's the only doc that discusses "interest rate" on a savings-type product |
| `fee-schedule` (2026) | 0.376 | Weak, generic lexical overlap ("savings account," "interest") |
| `fee-schedule` (2024) | 0.370 | Same weak overlap — both fee-schedule versions surface together |

None of these three chunks say anything about a crypto product, because none exists.

## The response (P3 prompt, real API call)

```json
{
  "answer": "I don't have information on a cryptocurrency savings product in our current product lineup, so I can't confirm a rate. I'd suggest escalating to confirm whether this product exists.",
  "sources": [],
  "confidence": 0.0,
  "assumptions": [],
  "escalate": true
}
```

**Correct abstention, despite retrieval leakage.** The system does not use the `savings-interest-policy` chunk's real rates (3.00%–4.00%) to fabricate a plausible-sounding crypto rate, does not cite a source (empty `sources[]`, since nothing supports the answer), and correctly sets `escalate: true` rather than deflecting the associate with a bare "I don't know."

## Why this matters beyond the one example

This is the direct evidence behind the design conclusion in `evidence/04_retrieval_eval.md`: a similarity floor tuned to 0.35 lets weakly-related content through for genuinely out-of-corpus questions, and **that's acceptable** because the hard grounding rule (Phase 3, P3) is the layer that actually prevents fabrication — verified here on the exact scenario `capstone_build_plan.md` §4 names as the target case ("Handle the miss case... abstain and offer escalation. Never fall back to the model's own knowledge of banking").
