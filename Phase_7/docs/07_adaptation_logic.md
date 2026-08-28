# Phase 7 — Adaptation Logic

Three mechanisms, all reading from the same `data/feedback_store.jsonl` (redacted, per `src/feedback.py`) but each deciding something different. None involve fine-tuning — all are lookups/counts against stored feedback, evaluated fresh on every turn.

## Feedback signal

👍/👎 plus an optional reason code (`too_long`, `not_grounded`, `wrong_intent`, `unhelpful`, `too_cautious`), submitted via `graph.give_feedback(turn_result, customer_id, signal, reason_code, corrected_answer)` — the entry point Phase 8's `POST /feedback` calls directly with a prior `run_turn(...)` result. Every record is keyed by `intent` + `topic`, where `topic` is derived consistently (`feedback.derive_topic()`): the first policy `doc_id` cited, else the first tool called, else the intent itself. Stored fully redacted (`src/redaction.py`), same as every other persistent store in this project — a `customer_id_hash`, never the raw id.

## 1. Style adaptation

**What changed:** 2 `too_long` votes from the same customer → `memory.set_preference(customer_id, "style", "terse")`. The agent already reads this preference (built in Phase 6) and includes a hard length instruction when it's set.

**Why 2, not 1:** a single complaint could be about that one answer's content, not the customer's general preference; requiring 2 avoids over-fitting to a one-off.

**Bounded:** per-customer only (never affects another customer's session), and `maybe_adapt_style()` checks the preference isn't already set before re-counting, so it's idempotent — repeated `too_long` votes past the 2nd don't do anything further.

**Rollback:** `/forget` clears the preference (Phase 6 mechanism, reused as-is — no new rollback code needed). There's no automatic *relaxation* path (e.g., a 👍 doesn't turn terse mode back off) — that's a deliberate scope boundary for this capstone, named explicitly rather than silently absent: a real product would likely want an explicit "back to normal length" affordance, which belongs on the Phase 9 roadmap.

## 2. Dynamic few-shot injection

**What changed:** a 👎 with `reason_code="not_grounded"` and a `corrected_answer` gets embedded (`text-embedding-3-small`) and stored. On every subsequent turn, `agent_node` calls `feedback.find_similar_correction(turn_input)`, which embeds the new question and checks cosine similarity (threshold 0.85) against every stored correction. Above threshold, the closest one is injected into the agent's system messages as a worked example before it answers.

**Why this reuses Phase 4's machinery:** the embedding + cosine-similarity mechanism is identical in kind to the retriever's own similarity search — just applied to a much smaller, purpose-built "corrections" set instead of the policy corpus. No new infrastructure, same well-understood behaviour (including the same class of scoring/matching considerations already documented for the retriever).

**Bounded:** the similarity threshold (0.85) means an unrelated question never picks up a correction meant for something else — verified implicitly by the fact the mechanism only activated on a *semantically similar* fee question, not on unrelated account or escalation questions during testing.

**Rollback:** delete the specific line from `data/feedback_store.jsonl` (each record is independent and self-contained; there's no derived index to also invalidate), or, more simply, a corrected exemplar that turns out to be bad advice would itself get flagged by a future 👎 on whatever question retrieves it — the mechanism is self-correcting in the same loop, not just self-reinforcing.

## 3. Escalation-threshold tuning

**What changed:** `adaptation.confidence_threshold_for_topic(topic)` returns 0.8 instead of the default 0.5 once a topic has 2+ negative-feedback votes (any reason code — any "down" vote is evidence a topic has been trouble, not just `not_grounded` ones specifically). A new graph node, `confidence_gate`, runs after `verify_grounding` passes and before the answer is delivered: if the answer's own `confidence` (from `FinalAnswer`, part of the Phase 3 structured-output design) falls below the applicable threshold, the answer is suppressed and the turn escalates instead — `low_confidence_escalate_node`, which still creates a real ticket via `create_escalation_ticket`.

**A real bug found while building this, not left in:** topic derivation must be *stable* across repeated calls on "the same" question for this to work at all — the first implementation attempt used a policy question where `doc_ids_cited` (the topic's primary source) is only populated when retrieval happens to succeed that particular call, so two feedback votes and a follow-up check silently landed on different derived topics. Fixed by choosing a demo question with a structurally stable topic key (an account tool name) and documented in `evidence/07_before_after.md` rather than quietly re-run until it looked clean.

**Bounded:** re-evaluated fresh from the feedback store on every single turn — there's no persisted "flagged topics" list to go stale or need manual clearing.

**Rollback:** none needed by design. Since the threshold is a live function of `count_negative_for_topic()`, if a topic stops accumulating negative feedback (or the underlying issue causing the complaints gets fixed elsewhere in the system), the threshold silently relaxes back to default on the very next turn — no explicit "undo" action exists because none is needed.
