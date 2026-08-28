# Phase 8 — Graceful Failure Evidence

All five degradation paths from `capstone_build_plan.md` §8, each forced for real (killing/blocking the actual dependency, or a direct test of the resilience wrapper where LLM confidence/timeout values aren't reliably steerable through a real API call — same pattern as Phase 5's safeguard tests). No screenshots (this environment has no browser/screenshot tooling — see `docs/08_deployment.md`'s Limitations), but every result below is real console output from an actual forced failure, not a description of intended behaviour.

## 1. LLM timeout / 429 → 1 retry with backoff

Direct test of `src/resilience.py` with a mock LLM that raises a real `openai.APITimeoutError` on its first call:

```
=== Test 1: retry recovers a transient failure ===
result: SUCCESS after retry | calls made: 2 | elapsed: 1.5 s

=== Test 2: persistent failure raises LLMUnavailable after max_retries ===
Correctly raised LLMUnavailable after 2 calls: APITimeoutError after 2 attempt(s): Request timed out.
```

One retry recovers a transient failure (2 calls, ~1.5s backoff observed); a persistent failure is capped at exactly `max_retries + 1` attempts before giving up — never an infinite retry loop, never a partial answer returned mid-retry. Every LLM call site in `src/nodes/` (`classify_intent`, `plan_node`, `agent_node`, `finalize_answer_node`, `regenerate_answer_node`, `clarify_node`) routes through this wrapper; on final failure each one degrades to a documented safe fallback rather than crashing (see `docs/08_deployment.md`'s degradation matrix row for what each falls back to).

## 2. Vector store unavailable

Forced by pointing the live `retriever._store` at a nonexistent Chroma collection name, then asking a real policy question through the full graph:

```
Input: "What's the foreign transaction fee on a debit card?"
intent: general_product | route: proceed
final_response: "I have an answer, but my confidence in it is low for this particular
topic -- this area has had trouble before, so I'd rather get it checked. I've raised
ticket TCKT-00041."
tools_called: []
tool_error: search_bank_policy: timeout
```

No new code was needed for this one — the *existing* Phase 5 8-second tool timeout caught the broken vector store, `search_bank_policy` failed closed (no fabricated policy text), the resulting answer had confidence 0.0, and Phase 7's `confidence_gate` escalated it. This is a stricter behaviour than the original design's "account-lane only" (see `docs/08_deployment.md`'s honest-deviation note) — the whole turn escalates rather than attempting a policy-free partial answer.

## 3. Account API down

**A real gap found and fixed here, not a pre-existing safeguard.** Forced by setting `tools._data.ACCOUNTS = None` before a turn:

*Before the fix* — an unhandled `AttributeError` propagated all the way out of `graph.run_turn()` and crashed the process, because `customer_instrument_directory()` is called directly from `classify_intent`, outside the tool-call try/except that already protected every other account-data access:

```
AttributeError: 'NoneType' object has no attribute 'get'
During task with name 'classify_intent' ...
```

*After the fix* (`AccountServiceUnavailable` + `service_unavailable_node`, new in Phase 8):

```
Input: "What's the customer's savings account balance?"
intent: account_specific route: service_unavailable
final_response: "I can't retrieve your account details right now. I've raised ticket
TCKT-00042 so this can be followed up."
tools_called: None
tool_error: None
```

Exact wording match to the required behaviour ("I can't retrieve your account details right now" + escalation, no estimate attempted).

## 4. Grounding verifier fails twice

Already built and evidenced in Phase 5/7 (`fail_closed_node`, `Phase_5/evidence/05_safeguards.md`) — re-confirmed still working after all of Phase 6/7/8's changes: `verify_grounding` allows exactly one `regenerate_answer` attempt (`MAX_REGENERATE = 1` in `src/nodes/verify.py`); if the regenerated answer is *still* ungrounded, `fail_closed_node` suppresses it entirely and escalates, never delivering a partially-grounded answer.

## 5. Malformed LLM JSON → 1 repair attempt

Direct test of `invoke_structured_with_resilience` with a mock LLM whose first response fails to parse:

```
=== Test 1: repair attempt recovers malformed JSON ===
parsed: REPAIRED_RESULT | calls made: 2

=== Test 2: persistently malformed raises LLMUnavailable ===
Correctly raised LLMUnavailable after 2 calls: Structured output did not parse after 2 attempt(s): bad json
```

One repair attempt (an explicit "your previous response didn't parse, try again" follow-up message) recovers a malformed response; persistent failure is capped the same way as the timeout case, never left to retry indefinitely.

## Summary

| Failure | New code required? | Result |
|---|---|---|
| LLM timeout/429 | Yes — `src/resilience.py` didn't exist before Phase 8 | ✅ Retries once, fails closed with escalation |
| Vector store unavailable | No — Phase 5's tool timeout + Phase 7's confidence gate already covered it | ✅ Escalates (stricter than originally designed, documented) |
| Account API down | **Yes — a real crash, found and fixed in this phase** | ✅ Exact required message, no crash |
| Grounding verifier fails twice | No — Phase 5 | ✅ Still correct |
| Malformed LLM JSON | Yes — repair-retry logic didn't exist before Phase 8 | ✅ Repairs once, fails closed after |
