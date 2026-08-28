# Phase 5 — Debugging Journey: What Was Actually Wrong, and What's a Scoring Artifact

Building the real graph (not simulated context injection) surfaced genuine bugs that Phases 3–4's manual-context tests couldn't have found, since those phases never let an LLM freely choose tool arguments or a search query string. This log keeps the story honest: what actually broke, what was fixed, and what's left over that isn't a real defect.

## Pass rate over the debugging session (same 28 cases throughout)

| Stage | Pass rate | What changed |
|---|---|---|
| First full run | 3/28 (10.7%) | Baseline: real graph, no fixes yet |
| + account/dispute directory given to the agent | 6/28 (21.4%) | Fixed: agent had no way to know which `account_id`/`card_id` values existed, so it called nothing rather than guess |
| + `list_recent_transactions` default window widened 30→90 days | — | Fixed: AS-01 (₹590 fee, 14 July) is 42 days before "today" — the 30-day default silently missed it |
| + refusal/escalation wording fixes | 14/28 (50.0%) | Fixed: canned messages didn't consistently include words the eval set checks for ("can't", "escalat") |
| + classify_intent refinements (directory-aware ambiguity, approval-vs-status-check) | — | Fixed two real misclassifications (AS-02 wrongly flagged ambiguous; AS-05 wrongly flagged as a new approval request instead of a status check) |
| + JSON `ensure_ascii=False` fix | 17/28 (60.7%) | **The most consequential single fix** — see below |
| + timeout executor fix (not a scorer change, a real latency bug) | 17/28 (60.7%, unchanged) | Fixed: the 8s per-tool timeout wasn't actually bounding turn latency |

## The most important bug: `verify_grounding` was silently discarding correct answers

`json.dumps(result, default=str)` defaults to `ensure_ascii=True`, which escapes `₹` (U+20B9, non-ASCII) into the literal 6 characters `₹`. `verify_grounding`'s number-extraction regex then merged the trailing `9` of that escape sequence with the real digits that followed — `₹500` became the token `9500` in the grounding check's view of the tool output, so a correctly grounded `₹500` in the answer could never be found there. The system was working — the LLM was genuinely reading the right tool output and answering correctly — and the safety layer built to protect against fabrication was instead discarding good answers and forcing needless "I don't have that information" deflections or unnecessary regenerate cycles. Fixed by passing `ensure_ascii=False`, and separately by normalizing both sides of the comparison to floats (stripping `₹`, commas, `%`) rather than comparing raw substrings — the same class of fix Phase 3 and Phase 4 both needed for the same underlying reason (formatting differences, not factual differences).

This is worth stating plainly: **an eval harness with a false-negative bug is worse than no eval harness**, because it looks like evidence of a safety problem when the safety problem is actually in the checker. Every "ungrounded" result in this project's Phase 3/4/5 evidence was re-inspected by reading the actual answer text before being reported as a real finding, for exactly this reason.

## What's left, and why it's not chased further here

- **AS-03** (`₹3,121,480` vs. the eval's expected `31,21,480`): same number, Indian vs. international digit grouping. Known, accepted, documented pattern from Phase 3/4 — not a grounding failure.
- **AS-05, ESC-\* details**: citations correctly land in the structured `sources`/ticket fields rather than always being restated in prose — the same "scorer checks prose text only" limitation identified in Phase 3.
- **PL-01/PL-02**: deliberately kept "I can't give legal advice" (matching the money-movement/approval refusals' voice) over "I'm not able to give legal advice" (what the eval set happens to check for) — a conscious choice for a consistent refusal voice across categories over chasing one eval string.
- **UNA-01–03**: all three correctly abstain and correctly avoid fabricating a number or confirming a nonexistent product — they fail only on exact-phrase checks (`"don't have"` vs. `"couldn't find"`) or an overly literal `must_not_contain` (banning the bare word "Diamond", which the response uses only to echo the question back, not to claim the product exists).
- **AS-04** (still genuinely open): documented as the required failed/incorrect-tool-call exhibit in `evidence/05_failed_tool_call.md`, rather than patched away.
