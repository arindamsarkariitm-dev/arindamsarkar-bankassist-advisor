# Phase 5 — Tool Selection Matrix

All 28 golden-test-set cases run through the real LangGraph pipeline (not simulated context injection like Phases 3–4) via `Phase_5/src/graph_eval.py`. Full records: `Phase_5/logs/phase5_tool_traces.jsonl`. Final run: **17/28 (60.7%)** on the mechanical scorer — see `evidence/05_regression_summary.md` for why that number understates real behaviour, and `evidence/05_failed_tool_call.md` for the one still-open genuine gap.

## Correct tool selection, by category

| Question type | Tool called | Example case | Verified correct? |
|---|---|---|---|
| Product/fee/policy question | `search_bank_policy` | GP-01–05, UNA-01–03 | Yes — every `general_product`/`unanswerable` case correctly called the policy tool, never an account tool |
| Account balance | `get_account_summary` | AS-02, AS-03 | Yes — correct `account_id` selected from the customer's own directory |
| Transaction lookup | `list_recent_transactions` | AS-01 | Yes — correctly widened `days` to cover a 42-day-old transaction (see failed-call exhibit) |
| Dispute status | `check_dispute_status` | AS-05 | Yes — correct `case_id` |
| Money movement / approval / legal advice | **none** | PM-01–03, PA-01–03, PL-01–02 | Correct — `policy_gate` routes these to `refuse_node` before the agent (and its tools) are ever reached |
| Fraud / hardship / complaint / deceased / distress | **none** (only `create_escalation_ticket`, via `escalate_node`) | ESC-01–04 | Correct — `policy_gate` routes to `escalate_node` directly; the agent's tool set deliberately excludes `create_escalation_ticket`, so escalation is never the agent's own decision mid-conversation |
| Ambiguous, no context needed | none (asks a clarifying question) | AMB-01 | Yes — `clarify_node` correctly named the customer's actual account types by name |

## Correct EMI-specific selection

Not exercised by the golden set directly (no in-corpus loan-EMI case), but verified separately: asked for the EMI on an existing home-loan-shaped request, the agent calls `calculate_emi` rather than computing the figure mentally — this was true from the first working run onward, with no tuning required, because `calculate_emi`'s docstring explicitly instructs "never compute it mentally."

## Correct routing away from the agent entirely

The clearest evidence that routing (not just tool choice) is deterministic: **zero** of the 8 `prohibited_*` cases and **zero** of the 4 `high_risk_escalate` cases ever reached the `agent` node at all — confirmed by `tool_calls: []` for all 12 in the trace log, because `policy_gate` (pure code, no LLM in the loop at that point) redirected them before the agent node runs. This is the concrete mechanism behind "refusal rules moved out of the prompt and into policy_gate" from `capstone_build_plan.md` §5.
