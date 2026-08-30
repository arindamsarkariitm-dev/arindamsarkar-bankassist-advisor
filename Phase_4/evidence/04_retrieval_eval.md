# Phase 4 — Retrieval Evaluation & Floor Tuning

> **Addendum (Phase 9, added without rewriting the measurements below):** query #19 in the table below ("What's the late payment fee on a credit card?") shows `fee-schedule` retrieved **twice** at floor 0.35 — that double entry is the deliberately planted stale-fee bug (both the 2024/superseded and 2026/current versions cleared the floor together), later found, root-caused, and fixed in Phase 9 — see `Phase_9/docs/09_evaluation_report.md` for the full symptom → root cause → fix → before/after writeup, and `src/retriever.py`'s `_filter_superseded()`. Re-running that exact query post-fix: `fee-schedule` now appears **once**, `status=current` only — the superseded duplicate is gone from the candidate pool entirely, not just outscored. The hit@1/hit@3/MRR numbers below are left as originally measured (pre-fix) rather than restated, since they're historical evidence of the floor-tuning decision at the time it was made, not a live claim about current retrieval behaviour.

20 labelled queries (2 per corpus document), real embedding calls via `text-embedding-3-small`, scored against `src/retriever.py`. Full per-query data and 3 out-of-corpus probe results are in `Phase_4/logs/04_floor_tuning.json`.

## Floor tuning (measured, not asserted)

`capstone_build_plan.md` §4 says "start 0.35 and tune" — so it was actually tuned, against three candidate floors:

| Floor | hit@1 | hit@3 | MRR | Out-of-corpus probes correctly empty (of 3) |
|---|---|---|---|---|
| 0.35 | 90.0% | 95.0% | 0.917 | 1 |
| 0.40 | 90.0% | 95.0% | 0.917 | 1 |
| 0.45 | **65.0%** | **65.0%** | **0.650** | 1 |

**Finding: raising the floor doesn't buy what it looks like it should.** The intuitive move — raise the floor to stop out-of-corpus queries from retrieving anything — fails on both counts here. Even at 0.45, 2 of the 3 out-of-corpus probes still leak at least one chunk (see below), and getting there costs a 25-point drop in hit@1/hit@3. The floor is not a clean in-corpus/out-of-corpus boundary for this embedding model and this corpus size; **chosen floor: 0.35**, on the reasoning in "Why the floor doesn't need to do this job alone," below.

## Per-query retrieval results (floor = 0.35)

| # | Query | Expected doc_id | Rank | Retrieved (in order) |
|---|---|---|---|---|
| 1 | What's the daily ATM withdrawal limit on a debit card? | debit-card-terms | 1 | debit-card-terms, upi-neft-imps-limits |
| 2 | How do I block a lost or stolen debit card? | debit-card-terms | 1 | debit-card-terms |
| 3 | When is the minimum amount due on a credit card bill? | credit-card-terms | 1 | credit-card-terms, credit-card-terms |
| 4 | What happens if I withdraw cash using my credit card? | credit-card-terms | 1 | credit-card-terms, debit-card-terms, credit-card-terms |
| 5 | How long does it take to resolve a disputed transaction? | dispute-chargeback-procedure | 1 | dispute-chargeback-procedure |
| 6 | What evidence do I need to raise a dispute? | dispute-chargeback-procedure | 1 | dispute-chargeback-procedure |
| 7 | What documents are needed for a home loan application? | home-loan-document-checklist | 1 | home-loan-document-checklist, home-loan-document-checklist, financial-hardship-policy |
| 8 | What's the minimum credit score for home loan eligibility? | home-loan-document-checklist | 1 | home-loan-document-checklist |
| 9 | How often do I need to complete re-KYC? | kyc-requirements | 1 | kyc-requirements, kyc-requirements |
| 10 | What happens if I don't complete KYC on time? | kyc-requirements | 1 | kyc-requirements, kyc-requirements |
| 11 | What's the interest rate on a fixed deposit? | savings-interest-policy | 1 | savings-interest-policy |
| 12 | How is savings account interest calculated? | savings-interest-policy | 1 | savings-interest-policy, fee-schedule, fee-schedule |
| 13 | What's the maximum amount I can send via IMPS? | upi-neft-imps-limits | 1 | upi-neft-imps-limits |
| 14 | Is there a fee for NEFT transfers? | upi-neft-imps-limits | 1 | upi-neft-imps-limits, credit-card-terms, fee-schedule, debit-card-terms |
| 15 | How do I escalate a complaint to the banking ombudsman? | complaint-escalation-matrix | 1 | complaint-escalation-matrix, dispute-chargeback-procedure, financial-hardship-policy |
| 16 | What's the response time for a Level 2 complaint escalation? | complaint-escalation-matrix | 1 | complaint-escalation-matrix, dispute-chargeback-procedure |
| 17 | What options are available if I can't pay my EMI due to job loss? | financial-hardship-policy | 1 | financial-hardship-policy |
| 18 | What documents are needed to apply for an EMI moratorium? | financial-hardship-policy | 1 | financial-hardship-policy, home-loan-document-checklist, home-loan-document-checklist |
| 19 | What's the late payment fee on a credit card? | fee-schedule | 3 | credit-card-terms, credit-card-terms, fee-schedule, fee-schedule |
| 20 | How much does it cost to replace a lost debit card? | fee-schedule | **miss** | debit-card-terms |

**18/20 hit@1, 19/20 hit@3, 1 genuine miss.** Query 20's miss is a real, specific embedding-similarity limitation worth naming: `debit-card-terms.md` describes the replacement *process* ("a replacement card is dispatched within 5-7 working days") without stating the *cost*, while `fee-schedule.md` has the actual ₹200 figure. The query's semantic content ("cost to replace") apparently matched the process-description document more strongly than the fee table. A future improvement (noted in the Phase 9 roadmap) would be repeating key figures near their process description, or hybrid (keyword + dense) retrieval for numeric lookups.

## Out-of-corpus probes (at each floor)

| Probe | Floor 0.35 | Floor 0.40 | Floor 0.45 |
|---|---|---|---|
| "interest rate on your crypto savings product?" | 3 results (savings-interest-policy 0.49, fee-schedule×2 ~0.37) | 1 result (savings-interest-policy 0.49) | 1 result (savings-interest-policy 0.49) |
| "EMI on a used-car loan?" | 0 results | 0 results | 0 results |
| "NRI-specific credit card, Diamond-tier lounge access?" | 4 results (debit/kyc/home-loan/credit-card, 0.35–0.46) | 2 results (debit-card-terms 0.46, credit-card-terms 0.45) | 2 results (same as 0.40) |

Only the used-car-loan probe cleanly returns nothing at every floor tested; the other two always leak at least one topically-adjacent chunk, even at 0.45.

## Why the floor doesn't need to do this job alone

Rather than keep raising the floor and eating more retrieval-quality loss, the actual fabrication risk was tested directly: does the LLM (Phase 3's P3 prompt, with its hard grounding rule) fabricate an answer when given these leaked, topically-adjacent-but-wrong chunks? **No.** Run against the worst-leaking probe (NRI card question, 4 irrelevant chunks retrieved at floor 0.35):

> **Retrieved:** debit-card-terms, kyc-requirements, credit-card-terms, fee-schedule (none actually about NRI cards or lounge access)
> **P3's answer:** "I don't have specific information about an NRI-specific credit card or its features, including airport lounge access for Diamond-tier customers. I recommend escalating this to confirm the availability and details of such a product." `escalate: true`, `sources: []`

The grounding rule correctly refuses to synthesize an answer from irrelevant context. This held for the crypto-savings probe too (see `evidence/04_missing_info_case.md`). **Conclusion: retrieval-floor tuning and prompt-level grounding are two independent layers, not one job split between them.** The floor's role is retrieval quality (getting the right document ranked highly for real queries); preventing fabrication when nothing relevant exists is the grounding rule's job, and it does that job even when the floor lets weak matches through. Sacrificing 25 points of hit@1 to chase a floor-only fix for a problem the prompt already solves is the wrong trade — **floor stays at 0.35.**
