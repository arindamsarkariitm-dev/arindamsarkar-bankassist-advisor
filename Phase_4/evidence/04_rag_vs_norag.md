# Phase 4 — RAG vs. No-RAG (same 10 questions, same prompt, same model)

All 10 questions run twice through the Phase 3-winning P3 prompt (`gpt-4o-mini`, `temperature=0`) — once with no context at all, once with real retrieval (floor 0.35) injected as `RETRIEVED_POLICY_CONTEXT`. Full records in `Phase_4/logs/04_rag_vs_norag.jsonl`.

## Result: without RAG, P3 is safe but useless. With RAG, it's safe and actually helpful.

| # | Question | No-RAG answer | RAG answer (cited doc_id) |
|---|---|---|---|
| 1 | Foreign transaction fee on a debit card? | "I don't have the specific foreign transaction fee... Please check the bank's fee schedule or escalate." | "**3.5%** of the transaction value, charged in INR after currency conversion..." *(fee-schedule)* |
| 2 | Late payment fee on a credit card? | "I don't have the specific late payment fee details... escalate for more information." | "**₹500 flat** if the minimum amount due is unpaid by the due date." *(fee-schedule)* |
| 3 | Daily UPI sending limit? | "I don't have the specific daily limit for UPI transactions... recommend checking with the bank's official resources." | "Up to **₹2,00,000 per day** across all UPI apps linked to their account." *(upi-neft-imps-limits)* |
| 4 | Savings interest rate under ₹1 lakh? | "I don't have the specific interest rate... recommend checking the bank's official website." | "**3.00% per annum**, calculated on the daily closing balance and credited quarterly." *(savings-interest-policy)* |
| 5 | Home loan documents needed? | Generic list: "proof of identity, proof of income... best to check with the bank for a complete checklist." | Full, correct checklist by category (identity/income/property/other) matching the actual policy doc verbatim. *(home-loan-document-checklist)* |
| 6 | Dispute resolution time? | "generally takes up to 45 days" *(plausible-sounding, not verified against our corpus)* | "**30 to 45 business days** to reach a final resolution, although some cases may take longer..." *(dispute-chargeback-procedure)* |
| 7 | Debit card annual maintenance fee? | "I don't have the specific annual maintenance fee... escalate to a team that can provide the exact fee details." | "**₹250 plus GST**." *(fee-schedule)* |
| 8 | Re-KYC frequency? | "Typically... every 1 to 5 years, depending on risk profile" *(wrong — invented range)* | "**low risk every 10 years, medium risk every 8 years, high risk every 2 years**." *(kyc-requirements)* |
| 9 | Consequences of a missed credit card payment? | Generic banking knowledge: "late fee... credit score... interest may accrue." | Specific and correct: flat late fee, credit-bureau reporting after grace period, **hardship-pathway trigger after 2+ consecutive missed minimums**. *(credit-card-terms)* |
| 10 | Options for EMI hardship? | Generic but roughly right: "restructuring... temporary moratorium... escalate to a specialized team." | Correct, specific options (moratorium, restructuring, settlement-as-last-resort) plus documentation requirement and an actual escalation. *(financial-hardship-policy)* |

## Two distinct failure patterns without RAG — worth telling apart

**Pattern A — correct abstention (7 of 10 questions).** For crisp, numeric facts (fees, rates, limits — Q1–4, 7), P3's grounding rule works even with zero retrieved context: it declines rather than guessing a number. This is real evidence the Phase 3 prompt decision was sound on its own terms.

**Pattern B — parametric-knowledge drift (3 of 10 questions: Q6, 8, 9, and softly Q10).** For process/narrative questions, the grounding rule is weaker: nothing in the rule's wording ("never state a fee amount, a date, a case status...") clearly covers "how long does a dispute take" or "what happens after a missed payment," so the model answers from its general banking knowledge instead of abstaining. **Q8 is the clearest case of real, measurable drift**: without RAG, it invents a "1 to 5 years" re-KYC range; the bank's actual policy is a specific three-tier schedule (10/8/2 years by risk level) — plausible-sounding, wrong, and exactly the kind of error a customer would have no way to detect. Q6's "45 days" happens to roughly match our real 30–45 day window, but that's luck, not grounding — it's the same failure mode as Q8, just with a less damaging outcome this time.

**This is the real "improvement over baseline" story for Phase 4**, and it's more precise than "RAG stops hallucination" — Phase 3's grounding rule already stops hallucination on hard numeric facts. What RAG adds is (a) turning safe-but-unhelpful abstentions into safe, correct, cited answers, and (b) closing the softer drift risk on narrative/process questions that the prompt-only grounding rule doesn't fully cover.
