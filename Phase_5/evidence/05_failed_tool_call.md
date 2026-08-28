# Phase 5 — Failed / Incorrect Tool Call (required exhibit)

Two real exhibits: one genuine mis-selection from an early run, with the fix and real before/after (per `capstone_build_plan.md` §5's request); one still-open gap, documented honestly rather than quietly patched.

## Exhibit 1 — fixed: `list_recent_transactions`'s default window silently missed the flagship case

**Case:** AS-01 — "Customer's asking why she was charged ₹590 on 14 July — can you check?" (today: 25 Aug 2026, so 14 July is 42 days prior)

**Before (early run, `days: int = 30` default, no date-gap guidance in the docstring):**

```
TOOL CALL: list_recent_transactions {'account_id': 'CARD-2001', 'days': 30}
TOOL RESULT: [... transactions from the last 30 days only, TXN-0076 (14 Jul) not among them ...]
TOOL CALL: list_recent_transactions {'account_id': 'CARD-2001', 'days': 30, 'contains': '₹590'}
TOOL RESULT: []

final answer_json: {"answer": "I couldn't find any transaction for ₹590 on 14 July in the recent
transactions for the credit card. I recommend checking the statement or escalating the issue for
further investigation.", "sources": [], "confidence": 0.0, "assumptions": [], "escalate": true}
```

The tool call itself was reasonable-looking — right tool, right account_id — but the default 30-day window doesn't reach a 42-day-old transaction, and the second attempt tried filtering by an amount string (`contains` matches the transaction *description* text, not a rupee amount) rather than widening the window. The system did not fabricate a wrong number — it correctly declined and offered escalation — but the underlying tool call was still a genuine miss, not a safe outcome to leave in place.

**Root cause:** (1) default lookback too short relative to the actual data window (transactions span 90 days), (2) the docstring gave the model no reason to reason about the gap between "today" and a date mentioned in the question, (3) `contains` was used for the wrong field.

**Fix:** widened the default to 90 days and rewrote the docstring to explicitly instruct computing the date gap and to clarify `contains` matches merchant/description text, not amounts (`src/tools/account_tools.py`).

**After:**

```
TOOL CALL: list_recent_transactions {'account_id': 'CARD-2001', 'days': 90}
TOOL RESULT: [... 35 transactions, including TXN-0076 ...]

final answer_json: {"answer": "The charge of ₹590 on 14 July was a \"Foreign Transaction Fee (3.5%)
on POS Purchase - Marina Bay Suites, Singapore, 12 Jul 2026.\"", "sources": ["TXN-0076"],
"confidence": 1.0, "assumptions": [], "escalate": false}
```

One tool call, correct data, correctly cited, no fabrication either before or after — the fix moved the system from "safe but unhelpful" to "safe and correct," which is the same shape of improvement Phase 4 found RAG provides on top of Phase 3's grounding rule.

## Exhibit 2 — still open: the agent sometimes narrates instead of calling

**Case:** AS-04 — "Is there a dispute open on the customer's credit card?"

**Actual response (current, after multiple prompt attempts to fix this class of behaviour):**

```
tool_calls: []
final_response: "I don't have information on any open disputes specifically related to the
customer's credit card. However, there is a dispute case on file for a duplicate charge. Would
you like me to check the status of that dispute?"
```

The agent has `check_dispute_status` available and `DSP-001` is in the directory it was given, but it answers from the directory summary (which only carries id + category, not current status) instead of calling the tool, and *offers* to check rather than checking. Two rounds of prompt tightening — first clarifying the directory is "ids only, no detail," then adding an explicit "never narrate an intention to look something up without a matching tool call this turn" instruction — measurably fixed some cases (`AMB-02`/`AMB-03` changed behaviour) but did not fully close this one.

**Why this is reported as still open rather than patched further:** further prompt-only iteration on this one case risks exactly the anti-pattern Phase 3 already identified — patching behaviour with more prompt text instead of moving the guarantee into code. The more durable fix belongs in Phase 6/8: either a code-level check that any `account_specific` route with a dispute-shaped question requires at least one `check_dispute_status` call before `finalize_answer` runs, or extending `verify_grounding` to flag relational claims ("not linked to X") the same way it already flags numeric ones. Documented here as a concrete, evidenced item for the Phase 9 improvement roadmap rather than silently prompt-patched away.
