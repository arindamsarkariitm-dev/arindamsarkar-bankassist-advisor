# Phase 3 — Prompt Decision

**Decision: adopt P3 (Structured + Grounded) as the default prompt going forward.**

## Why, precisely — not just "it matches the hypothesis"

The raw mechanical pass rate actually favours P2 (53.6% vs. P3's 46.4%) — see `evidence/03_prompt_comparison.md`. Picking P3 anyway needs a real justification, and the evidence supports one:

1. **P3 is the only variant that solves abstention/grounding**, the requirement `scenario_analysis.md` names as "the hardest requirement in either scenario." On the `unanswerable` bucket, P1 and P2 both score 0% — and P2 doesn't just fail to abstain, it flatly fabricates the existence of a credit card product that isn't in the corpus ("The bank does offer an NRI-specific credit card that includes airport lounge access..."). P3 scores 66.7% and, on inspection, its two "failures" there are near-misses on wording, not fabrication. No amount of role/policy instruction in P2 fixed this; only the explicit hard rule did.
2. **P3 gives cleaner legal-advice refusals** — P2 drifts into legal-adjacent specifics after declining (`PL-01`, `PL-02`); P3 declines and stops. Same mechanical "fail" score, materially different — and more dangerous — behaviour underneath.
3. **Most of P3's apparent underperformance is the scoring harness, not the model.** Three confirmed causes (detailed in the evidence doc): its citations correctly land in the structured `sources` field rather than inline prose, its refusal wording differs from a hardcoded string, and one test (`AS-03`) fails on Indian-vs-international number-grouping despite an identical figure. Once you read the actual answers, P3's real safety/grounding behaviour is at least as good as P2's everywhere except the one shared ambiguous-bucket bug below — and it demonstrably better on grounding.

## Trade-offs accepted, explicitly

- **Cost and latency rise.** +63% average completion tokens and +23% average latency versus P2 (both still lower than P1). Acceptable for a system whose failure mode is a wrong number told to a bank customer, not a system with a hard real-time constraint — but worth tracking against the M8 latency target (< 6s) as the full pipeline gets heavier in later phases.
- **Structured JSON output requires a parser**, and that parser needs to handle malformed JSON gracefully (Phase 8's degradation matrix already plans for this: "Malformed LLM JSON → 1 repair attempt → safe fallback message").
- **The `sources`-field-vs-answer-text gap must be fixed in the Phase 9 eval harness**, not just noted here — any grounding verification step (Phase 4's `verify_grounding` node, Phase 9's `test_grounding.py`) needs to check citations against `sources[]`, not scan the prose answer for a doc ID string.

## What does NOT get fixed by prompt choice alone, and is deferred to later phases

- **The ambiguous+escalation-keyword precedence bug** (`AMB-03`): when a case is both ambiguous and touches an escalation-trigger word like "dispute," both P2 and P3 skip the required one clarifying question and escalate immediately. This is a genuine prompt-instruction-ordering gap, shared by both surviving variants. Per `capstone_build_plan.md` §5, refusal/escalation/clarify logic is moving out of the prompt and into `policy_gate` as deterministic routing in Phase 5 anyway — that's where this gets fixed properly, with an explicit precedence rule (clarify before escalate, unless the case is unambiguously high-risk on its own), rather than patched with more prompt wording that the next rephrasing could break again.
- **Product-catalog-existence checks** (`UNA-02`, the "used-car loan" case): no prompt fixes a model treating a plausible-sounding but nonexistent product as legitimate — this needs Phase 4's retrieval to actually fail to find a matching product and signal that upstream, rather than asking the LLM to know the bank's product catalog from instructions alone.
- **Ambiguous cases with genuinely no context** (`AMB-01`, `AMB-02`): Phase 3 cannot yet distinguish "no data exists" from "data exists once you specify which account," because there's no real tool-calling. Re-measure once Phase 5 lands.

## Net assessment

P3 is chosen because it uniquely closes the one gap that matters most for this scenario (grounding/abstention), does so without a real safety regression anywhere the transcript was actually read rather than just scored, and produces the structured output Phase 4 (`verify_grounding`) and Phase 9 (`eval_harness`) both depend on. Its costs (tokens, latency) are real and worth monitoring, and its one genuine shared weakness (the ambiguous/escalate precedence bug) is already scheduled to be fixed by moving that logic into code in Phase 5 — consistent with the build plan's original reasoning for why routing belongs in `policy_gate`, not prompt text.
