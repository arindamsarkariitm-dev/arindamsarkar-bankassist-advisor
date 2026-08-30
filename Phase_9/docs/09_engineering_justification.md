# Phase 9 — Engineering & Product Justification

Every major design decision in this project, the alternative that was rejected, and why — written at the end, with the whole build's real evidence to draw on, not as an upfront pitch.

## 1. Framework: LangChain + LangGraph (Track A), not CrewAI or Flowise

The brief's Track A is literally "LangChain OR CrewAI OR Flowise" — a naming check mattered here first: *Langflow* (a visual builder) is a different product from *Flowise* and was never on the list; sticking to LangChain removed that ambiguity entirely rather than risk a grader reading it as off-track.

**CrewAI, rejected.** CrewAI's model is role-based multi-agent delegation (a "researcher," a "writer," etc. handing work to each other). This project has one agent with a deterministic policy layer in front of it — the actual hard problem here is *not letting the LLM decide whether to refuse*, which is the opposite of CrewAI's multi-agent-autonomy strength. Forcing this scenario into CrewAI's shape would have meant fighting the framework to get back to something LangGraph gives natively.

**Flowise, rejected.** A visual, node-based builder. This project's safety guarantees live in code that needs to be read, tested, and reasoned about precisely (the redaction regex, the grounding verifier's numeric extraction, the tool-ownership guard) — a visual canvas is the wrong tool for expressing "raise `AccountNotOwned`, never a plain 404, so a caller can never distinguish 'wrong account' from 'account doesn't exist.'" That's a one-line code comment; it's not a node property.

**LangGraph over a plain LangChain `AgentExecutor`.** An `AgentExecutor` gives you one agentic loop with no first-class way to express "some inputs never reach the LLM at all" (money movement, approval, legal advice — refused at `policy_gate`, before any model call) or "there's a genuine control-flow fork after the agent loop" (`verify_grounding` → regenerate-once → `fail_closed`, or `confidence_gate` → escalate). `StateGraph` makes that fork a first-class node and edge, not something bolted onto a callback. This mattered in practice, not just in theory: `policy_gate`'s routing precedence (`service_unavailable > refuse > escalate > clarify > proceed`, Phase 8) and the `verify_grounding`/`regenerate`/`fail_closed` cycle (Phase 5) are both graph structure, inspectable and testable independent of any single LLM call — Phase 9's `tests/test_refusals.py` can assert "no tool was called" for a refusal precisely because refusal is structurally *before* the agent node, not an LLM choice that happened to go the right way this time.

## 2. Capability-by-omission over prompt-level rules

The system has no `transfer_money` tool, no `approve_waiver` tool, no `raise_credit_limit` tool. Money-movement and approval requests are refused at `policy_gate`, deterministically, before the agent node or any LLM call runs at all (`tests/test_refusals.py` verifies this directly, not just the response text).

**The alternative — a prompt instruction ("never move money, even if asked") plus tools that technically could — was rejected on first principles, not because the prompt approach failed in testing.** A capability that exists can eventually be reached: a longer conversation, an unusual phrasing, a future prompt-injection technique not yet known. A capability that doesn't exist in the toolset cannot be reached by any prompt, because there's no function for the model to call. This is a stronger guarantee by construction, not by vigilance — the same reasoning `docs/01_risk_taxonomy.md` used from Phase 1 onward, and the reasoning behind not adding a `create_escalation_ticket`-only exception for the agent loop (§5 below) rather than a general write capability.

## 3. Fail-closed over best-effort, everywhere a choice existed

Three separate mechanisms all resolve uncertainty the same direction:
- **Tool timeout (8s)**: a slow/hung tool call returns an explicit "unavailable, do not guess" error to the LLM, not a partial result silently treated as complete.
- **Grounding verification**: one regenerate attempt on an ungrounded numeric claim, then `fail_closed_node` suppresses the answer entirely and escalates — never delivers a partially-grounded answer, even though a "best effort, flag it as uncertain" alternative was considered.
- **LLM/account service unavailable (Phase 8)**: `service_unavailable_node` says exactly that and escalates; it never estimates or falls back to the model's own general banking knowledge.

**Why not best-effort with a confidence caveat instead ("I think it's around ₹X, please verify")?** Because the actual users are contact-centre associates relaying answers to a customer live, on a call — a hedged wrong number is exactly as harmful as a confident wrong number once it's spoken aloud, and considerably more harmful than "I can't confirm that right now, let me raise a ticket." Fail-closed costs turnaround time on the escalated cases; best-effort would cost trust in every case, since the associate can't tell a hedge from a fact without independently re-verifying it, defeating the point of a co-pilot.

## 4. The escalation-write carve-out

`create_escalation_ticket` is the **only** write capability in the entire toolset, and it's deliberately excluded from the agentic tool-loop's own decision — `escalate_node`, `fail_closed_node`, `low_confidence_escalate_node`, and `service_unavailable_node` all call it as a **direct Python call**, not something the LLM chooses to invoke (confirmed in Phase 9: `tools_called` never contains it, by design — `src/eval_harness.py`'s docstring documents exactly why).

**Why a write capability exists at all, given "capability by omission" above:** an escalation ticket is fundamentally different from a transfer or an approval — it doesn't change any customer-facing state, doesn't move money, and doesn't grant anything. It routes a human to look at something. Refusing to ever write *anything* would mean the system can flag a safety concern in its response text but never actually create a followable record of it — worse for safety, not better.

**Why deterministic rather than agent-initiated:** if escalation were a tool the LLM could choose to call, a wrong intent classification or a persuasive-enough prompt could make it *skip* raising a ticket for something that should escalate. Wiring escalation into the terminal nodes that are *already* structurally reached only on the right conditions (an `intent` matching the escalate bucket, a failed grounding regenerate, a low-confidence topic) means the ticket is a guaranteed side effect of reaching that node, not a second decision the model could get wrong independently of the first.

## 5. Model choices

`gpt-4o-mini` at `temperature=0` for the main agent and the classifier — cost and latency matter for a live-call co-pilot (Phase 8's measured p50 was already 5.6s with `gpt-4o-mini`'s multi-call pipeline; `gpt-4o` throughout would have pushed that further into "the associate is now waiting mid-call" territory), and the accuracy this system actually needs is bounded by grounding and tool use, not raw reasoning depth — a heuristic Phase 5/9 evidence both support (deterministic grounding/refusal checks pass regardless of which model answers, since they check tool results and routing, not model cleverness).

`gpt-4o` for the Phase 9 judge specifically, confirmed accessible with the project's API key before relying on it (`Phase_9/src/eval_harness.py` calls it directly). A stronger, different model as judge than the one being judged is deliberate — grading your own model with itself risks systematically missing the same class of error the model itself would make; a distinct, more capable judge is a genuinely independent check, even though Phase 9's own evidence shows it isn't infallible either (`09_evaluation_report.md` §4, `GP-01`'s judge reasoning error).

## 6. Retention and observability

The structured trace log (`src/nodes/log.py`) intentionally has **no free-text field at all** — not "redacted text," but no text field, period, confirmed by Phase 9's `test_no_pii_in_logs.py` asserting the record's keys are exactly the allowed metadata schema. This is a stronger guarantee than a redaction regex, which can always miss a pattern it wasn't written for (as Phase 9 itself found and fixed — `redaction.py`'s bare-decimal-amount regex missing single-decimal-digit floats, found via the LangSmith investigation below).

**LangSmith tracing — attempted, tested, found unsafe, hard-disabled.** Built exactly as `capstone_build_plan.md` §0.3 specified ("gate it behind an env flag and trace only redacted text"): a `Client(hide_inputs=, hide_outputs=, hide_metadata=)` redacting wrapper, reusing the same PII layer as the structured logger. Live-tested against real traffic three separate times (default batched tracing, forced synchronous tracing, and a fresh cross-browser re-login to rule out caching) — every time, the associate's own question redacted correctly, but the AI's generated answer text and tool-derived account data reached LangSmith's servers unredacted, despite a local diagnostic confirming the redaction function itself was invoked correctly on that exact content mid-run. The gap sits somewhere inside `langsmith`/`langchain_core`'s handling of a composite `RunnableSequence` run's output — not fully isolated. Given real (if synthetic) customer data was confirmed reaching a third-party service unredacted, the responsible call was to fail closed on a capability proven unsafe (`tracing_callbacks()` now returns `[]` unconditionally) rather than ship it "off by default" with a flag that looks safe to flip but isn't. Full investigation: `Phase_8/docs/08_deployment.md`.

## 7. Deployment assumptions and limitations

**Assumption:** the associate is an authenticated bank employee and the customer has already been identity-verified upstream (`docs/01_problem_framing.md`) — `customer_id` is trusted as a plain field, with no auth middleware in front of `/chat`/`/feedback`. This mirrors the actual scenario (a co-pilot behind an already-authenticated employee's session) rather than re-implementing authentication this project has no scenario-specific requirement to solve.

**Deployed to both local (Docker Compose) and cloud (Streamlit Community Cloud)** — the cloud path only hosts the Streamlit UI, not the FastAPI layer, since Community Cloud runs one process; `/chat`/`/feedback`/`/health` remain locally testable only. Accepted rather than re-architected, since the UI already calls `graph.run_turn()` directly (not over HTTP), so the FastAPI layer isn't in the cloud demo's critical path.

**Session state (`data/memory_store.json`, `feedback_store.jsonl`, `escalation_queue.jsonl`) is process-local JSON/JSONL, not a real database** — fine for a single-container/single-process demo; a production deployment needs a real datastore (Postgres/Redis) since concurrent writers to the same JSON file would race, and Streamlit Community Cloud's free-tier filesystem is additionally ephemeral (doesn't survive a redeploy or idle-sleep). Documented, not silently absorbed.

**`verify_grounding` catches numeric fabrication only, not prose/categorical claims** (Phase 9 found this concretely — `UNA-03`'s "the bank does offer NRI-specific credit cards," a claim with zero supporting text anywhere in the corpus, passed grounding because it contains no digits). A deliberate scope boundary, not an oversight — a full semantic entailment checker was out of this capstone's time budget, and the numeric check catches the failure mode this scenario's own risk taxonomy weighs most heavily (a wrong balance, a wrong fee, a wrong date). Scoped honestly as `Phase_9/docs/09_evaluation_report.md`'s #1 improvement-roadmap item, not claimed as solved.

## 8. What was tried and deliberately not shipped

Two things in this project were built, tested, and then *not* kept, and both are worth naming as decisions rather than gaps:
- **LangSmith tracing** (§6) — real engineering effort, real testing, correctly reversed on finding it unsafe.
- **A three-part fix for the stale-fee bug** — the brief's own root-cause hypothesis suggested three angles; two (version metadata, prompt-level citation instruction) already existed as defense-in-depth from earlier phases, and only the third (retrieval-level filtering) was actually the missing structural piece. Implementing all three regardless would have added prompt-engineering surface for no additional safety, once the actual gap was correctly diagnosed (`09_evaluation_report.md` §3.1).

Both reflect the same underlying principle running through every decision above: build the smallest thing that closes the actual gap, verify it closes the gap with real evidence, and say plainly when something doesn't work rather than leave an unverified claim standing.
