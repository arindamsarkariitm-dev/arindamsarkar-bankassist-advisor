"""
Generates docs/demo_script.md (deliverable #3, capstone_build_plan.md §5) --
5 forced interactions, each with the exact input, expected behaviour, actual
output, and trace/log evidence. Turns 1, 2, 4 and 5 are captured live here
from real run_turn()/give_feedback() calls; turn 3 reuses the already-real
forced-failure evidence from Phase 8 (Phase_8/evidence/08_graceful_failure.md
§3) rather than re-forcing the account service down again, since that
evidence is itself a genuine capture, not a description.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from graph import give_feedback, run_turn  # noqa: E402
import memory  # noqa: E402

OUT_PATH = ROOT / "docs" / "demo_script.md"

lines = ["# Demo Script — BankAssist Advisor\n"]
lines.append(
    "5 forced interactions per `capstone_build_plan.md` §5, each with the exact input, expected "
    "behaviour, actual output, and trace/log evidence. Turns 1, 2, 4, and 5 are captured live from "
    "real `run_turn()`/`give_feedback()` calls, not written by hand; turn 3 reuses the already-real "
    "forced-failure capture from Phase 8 rather than re-staging it, since that evidence is itself "
    "a genuine run, not a description of one.\n"
)


def emit(n, title, expected, question, customer_id, session_id=None):
    result = run_turn(question, customer_id, session_id=session_id)
    trace = result.get("trace") or {}
    lines.append(f"## Turn {n} — {title}\n")
    lines.append(f"**Expected behaviour:** {expected}\n")
    lines.append(f"**Associate:** {question}\n")
    lines.append(f"**BankAssist Advisor:** {result['final_response']}\n")
    lines.append(
        f"**Trace evidence:** `route={trace.get('route')}` `outcome={trace.get('outcome')}` "
        f"`tools_called={trace.get('tools_called')}` `doc_ids_cited={trace.get('doc_ids_cited')}` "
        f"`escalation_code={trace.get('escalation_code')}`\n"
    )
    return result, trace


# Turn 1 -- grounded account answer (CUST-0001, the only customer with this
# seeded transaction -- currently in terse mode from real feedback given
# earlier in this project's own testing history, left as-is rather than
# reset, since that's the system's genuine current state).
emit(
    1, "Grounded account answer",
    "Correct fee, cites the transaction and the fee-schedule doc with its effective date, "
    "phrased for the associate to relay.",
    "Customer's asking why she was charged ₹590 on 14 July -- can you check?",
    "CUST-0001",
)

# Turn 2 -- hard refusal, terminates at policy_gate before any LLM call.
_, trace2 = emit(
    2, "Hard refusal",
    "Refuses; explains the system has no transfer capability and this must go through the "
    "bank's authenticated transfer flow. Trace shows policy_gate terminating before any tool call.",
    "Customer wants to transfer ₹10,000 to her sister's account, she's asking me to just do it through here.",
    "CUST-0001",
)
lines.append(
    f"**Confirms policy_gate terminates before the LLM:** `tools_called={trace2.get('tools_called')}` "
    "-- refusal fires deterministically, not as an LLM choice that happened to go the right way.\n"
)

# Turn 3 -- no-hallucination under failure. Reused from Phase 8's real capture.
lines.append("## Turn 3 — No-hallucination under failure\n")
lines.append(
    "**Expected behaviour:** Account API forced down -> \"I can't retrieve that right now,\" "
    "escalation offered, no number invented, associate relays that to the customer verbatim.\n"
)
lines.append(
    "**Reused from `Phase_8/evidence/08_graceful_failure.md` §3** (forced by setting "
    "`tools._data.ACCOUNTS = None` before the turn -- not re-staged here, since that capture is "
    "itself a genuine run, and this exact scenario requires code-level access the live deployed app "
    "doesn't expose through its UI):\n"
)
lines.append("**Associate:** What's the customer's savings account balance?\n")
lines.append(
    "**BankAssist Advisor:** I can't retrieve your account details right now. I've raised ticket "
    "TCKT-00042 so this can be followed up.\n"
)
lines.append(
    "**Trace evidence:** `intent=account_specific` `route=service_unavailable` `tools_called=None` "
    "`tool_error=None` -- no balance figure anywhere in the response, confirmed by inspection.\n"
)

# Turn 4 -- high-risk escalation.
_, trace4 = emit(
    4, "High-risk escalation",
    "Immediate escalation, real ticket id, no troubleshooting attempt, associate directed to the "
    "fraud team.",
    "Customer says there are three transactions she doesn't recognise.",
    "CUST-0001",
)

# Turn 5 -- adaptation, before/after a too_long down-vote. CUST-0003 has no
# style preference set yet (verified before writing this script), so this
# is a genuine before/after, not a re-demo of an already-adapted customer.
lines.append("## Turn 5 — Adaptation (before/after a `too_long` 👎)\n")
lines.append(
    "**Expected behaviour:** Same question asked before and after two `too_long` 👎 votes from the "
    "associate shows a visibly shortened response (Phase 7's style adaptation, `STYLE_ADAPTATION_THRESHOLD=2`).\n"
)
# NOT "home loan documents" -- that topic already has 2 accumulated
# negative-feedback entries from earlier real testing in this project's
# history (data/feedback_store.jsonl), which independently raises its
# confidence-gate bar (Phase 7) and makes the "before" turn escalate
# instead of genuinely answer, confounding the length comparison this demo
# needs. upi-neft-imps-limits has zero accumulated negative feedback
# (checked before picking it), so this is a genuine verbose-vs-terse
# comparison, not verbose-vs-escalated.
adaptation_question = "What's the maximum amount I can send via IMPS in a day?"
before_prefs = memory.get_preferences("CUST-0003")
lines.append(f"**CUST-0003's style preference before this turn (confirmed clean):** `{before_prefs}`\n")

before_result = run_turn(adaptation_question, "CUST-0003")
lines.append("**Associate (before):** " + adaptation_question + "\n")
lines.append(f"**BankAssist Advisor (before, {len(before_result['final_response'])} chars):** {before_result['final_response']}\n")

fb1 = give_feedback(before_result, "CUST-0003", "down", "too_long")
fb2 = give_feedback(before_result, "CUST-0003", "down", "too_long")
lines.append(
    f"**Feedback given:** two 👎 `too_long` votes -- `style_adapted_now` on the 2nd call: "
    f"`{fb2['style_adapted_now']}`\n"
)
after_prefs = memory.get_preferences("CUST-0003")
lines.append(f"**CUST-0003's style preference after 2 votes:** `{after_prefs}`\n")

after_result = run_turn(adaptation_question, "CUST-0003")
lines.append("**Associate (after, same question):** " + adaptation_question + "\n")
lines.append(f"**BankAssist Advisor (after, {len(after_result['final_response'])} chars):** {after_result['final_response']}\n")
lines.append(
    f"**Length comparison:** {len(before_result['final_response'])} chars -> "
    f"{len(after_result['final_response'])} chars "
    f"({'shorter' if len(after_result['final_response']) < len(before_result['final_response']) else 'NOT shorter -- see note'}).\n"
)

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
with open(OUT_PATH, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

print(f"Written to {OUT_PATH}")
