"""
[5]/[6]/[7]/[8] agent + tools -- the LangChain tool-calling loop, and the
final structured-answer call.

By the time control reaches here, policy_gate has already routed away
refuse/escalate/clarify cases -- this node only ever runs for "proceed"
(general_product, account_specific, chitchat). The LLM decides which of the
five non-escalation tools to call (search_bank_policy, get_account_summary,
list_recent_transactions, check_dispute_status, calculate_emi) via native
function-calling; create_escalation_ticket is deliberately NOT bound here --
escalation is policy_gate's decision, never the agent's to reach for
mid-conversation.

Safeguards (capstone_build_plan.md §5), enforced in code, not prompt text:
  - max 5 tool calls per turn
  - no identical repeated call (hash of tool name + args)
  - 8s per-tool timeout
  - allow-list: only registry tool names are ever executed
  - every tool fails closed: a ToolError becomes a ToolMessage the model
    sees as "unavailable," never a fabricated substitute
"""
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from feedback import find_similar_correction
from memory import format_conversation_context
from observability import accumulate_tokens
from resilience import LLMUnavailable, invoke_structured_with_resilience, invoke_with_retry
from tools._data import customer_instrument_directory
from tools.exceptions import ToolError
from tools.registry import build_toolset

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
MODEL = os.environ.get("OPENAI_MODEL_AGENT", "gpt-4o-mini")

MAX_TOOL_CALLS_PER_TURN = 5
TOOL_TIMEOUT_SECONDS = 8

# Module-level, long-lived executor -- deliberately NOT a `with ThreadPoolExecutor(...)`
# per call. A context manager's __exit__ calls shutdown(wait=True), which blocks until
# the submitted thread actually finishes -- so a hung tool call would still make the
# whole turn wait out its full real duration even after future.result(timeout=8) has
# already raised, defeating the point of the timeout. A shared executor lets the caller
# move on at 8s; the abandoned thread is left to finish (or hang) on its own, which is
# an accepted, well-known limitation of thread-based timeouts in Python (there is no
# safe way to force-kill a thread) -- the fix that matters is that the CALLER isn't blocked.
_TOOL_EXECUTOR = ThreadPoolExecutor(max_workers=8)

AGENT_SYSTEM_PROMPT = """You are BankAssist Advisor, an AI copilot used by contact-centre associates
at a retail bank while they are on a call with an already identity-verified customer. You are never
used by the customer directly -- the associate relays your answers to the customer in their own words.

Never narrate an intention to look something up ("let me check", "please hold on", "I'll retrieve
that") without a matching tool call in that same turn. There is no next turn where you follow up --
if the information is available via a tool, call it now; if you're only describing what you would
do, you are not answering the question. Either call the tool and answer from its result, or say
plainly that you don't have the information.

You have tools for policy lookup and the customer's own account data. Use them:
- search_bank_policy for any product/fee/process question.
- get_account_summary / list_recent_transactions / check_dispute_status for anything about the
  customer's own accounts, transactions, or disputes. You will be given the customer's own list of
  account/card/dispute-case ids below -- that list tells you WHICH ids exist, nothing more (no
  balances, no dispute status, no category detail, and critically no which account/card a dispute
  case is actually linked to). Always call the matching tool to get the actual current details
  before answering; never answer from the id list alone, and never invent an id that isn't in it.
  If a dispute case_id isn't in that list either, say you don't have one on file. This applies even
  when the question asks about disputes on a SPECIFIC account or card: if the directory lists ANY
  dispute_case entry for this customer, you cannot tell from the list alone whether it belongs to
  the account/card asked about -- call check_dispute_status on it to find out before answering
  either way, rather than assuming it doesn't apply because the list itself doesn't say.
- calculate_emi for any EMI math -- never compute it mentally. Only use it for a loan product that
  actually appears in search_bank_policy results; if the product itself isn't in the corpus, say so
  instead of computing a number for a product that may not exist.

A transaction's `description` field often has the exact rate or reason in parentheses, e.g.
"Foreign Transaction Fee (3.5%) on POS Purchase - ...". Always quote that parenthetical figure
verbatim in your answer when one is present -- do not summarise it away into just the category name.

Hard grounding rule: never state a customer-specific or product-specific fact (a balance, a fee
amount, a date, a case status, an account number) that does not appear verbatim in a tool result you
actually received. If your tools return nothing relevant, say you don't have that information and
recommend escalating, rather than answering from your own general knowledge of banking.

Be concise and professional -- the associate is relaying your answer live, on a call."""


class FinalAnswer(BaseModel):
    answer: str = Field(description="The response text for the associate.")
    sources: list[str] = Field(default_factory=list, description="doc_id / transaction_id / case_id values actually used.")
    confidence: float = Field(ge=0.0, le=1.0)
    assumptions: list[str] = Field(default_factory=list)
    escalate: bool = Field(description="True if this should still be escalated despite being answerable.")


def _tool_call_hash(name: str, args: dict) -> str:
    raw = json.dumps({"name": name, "args": args}, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def agent_node(state: dict) -> dict:
    tools = [t for t in build_toolset(state["customer_id"]) if t.name != "create_escalation_ticket"]
    llm = ChatOpenAI(model=MODEL, temperature=0).bind_tools(tools)

    messages = state.get("messages")
    if not messages:
        directory = customer_instrument_directory(state["customer_id"])
        directory_note = (
            f"This customer's accounts/cards on file: {json.dumps(directory)}"
            if directory else "This customer has no accounts/cards on file."
        )
        messages = [SystemMessage(content=AGENT_SYSTEM_PROMPT), SystemMessage(content=directory_note)]
        context_note = format_conversation_context(state)
        if context_note:
            messages.append(SystemMessage(content=context_note))
        plan = state.get("plan") or {}
        if plan.get("is_multi_step"):
            steps_text = "; ".join(f"{s['step']}. {s['description']}" for s in plan.get("steps", []))
            plan_note = f"Your plan for this turn: {steps_text}."
            if plan.get("caveat"):
                plan_note += f" Caveat to include in your final answer: {plan['caveat']}"
            messages.append(SystemMessage(content=plan_note))
        if (state.get("preferences") or {}).get("style") == "terse":
            messages.append(SystemMessage(content=(
                "TERSE MODE IS ON for this associate. Hard limit: 2 sentences maximum, no preamble, "
                "no bulleted breakdown of sub-categories -- pick only the single most important fact "
                "and state it. If the full answer genuinely needs more than that, say the short "
                "version and add \"more detail available on request\" rather than listing everything."
            )))
        exemplar = find_similar_correction(state["turn_input"])
        if exemplar:
            messages.append(SystemMessage(content=(
                "A past answer to a very similar question was marked not-grounded by an associate "
                f"and corrected. Similar past question: {exemplar['redacted_question']!r}. "
                f"Corrected answer: {exemplar['redacted_correction']!r}. Follow the same grounding "
                "discipline that correction demonstrates for this question too."
            )))
        messages.append({"role": "user", "content": state["turn_input"]})

    try:
        ai_message: AIMessage = invoke_with_retry(llm, messages)
        return {"messages": messages + [ai_message], "token_usage": accumulate_tokens(state, ai_message)}
    except LLMUnavailable:
        # No tool_calls on this message -> should_continue_tool_loop sends
        # control straight to finalize_answer, which will produce the safe
        # fallback answer_json since there's nothing grounded to work with.
        return {"messages": messages + [AIMessage(content="")]}


def tools_node(state: dict) -> dict:
    tools_by_name = {t.name: t for t in build_toolset(state["customer_id"]) if t.name != "create_escalation_ticket"}
    messages = list(state["messages"])
    last_ai_message = messages[-1]

    tool_call_count = state.get("tool_call_count", 0)
    tool_call_hashes = list(state.get("tool_call_hashes", []))
    tools_called = list(state.get("tools_called", []))
    doc_ids_cited = list(state.get("doc_ids_cited", []))
    tool_error = None

    for call in last_ai_message.tool_calls:
        name, args, call_id = call["name"], call["args"], call["id"]

        if name not in tools_by_name:  # allow-list, enforced in code
            content = json.dumps({"error": f"'{name}' is not an available tool."})
        elif tool_call_count >= MAX_TOOL_CALLS_PER_TURN:
            content = json.dumps({"error": "Tool-call limit for this turn reached (max 5). Answer with what you have."})
        elif _tool_call_hash(name, args) in tool_call_hashes:
            content = json.dumps({"error": "This exact call was already made this turn; reuse that earlier result."})
        else:
            call_hash = _tool_call_hash(name, args)
            try:
                future = _TOOL_EXECUTOR.submit(tools_by_name[name].invoke, args)
                result = future.result(timeout=TOOL_TIMEOUT_SECONDS)
                # ensure_ascii=False is load-bearing, not cosmetic: with the default
                # True, "₹500" (an ASCII-escaped rupee sign) mangles verify_grounding's
                # number extraction into a spurious "9500", so a correctly grounded ₹500
                # answer can never match anything in the tool output and gets discarded.
                content = json.dumps(result, default=str, ensure_ascii=False)
                tool_call_count += 1
                tool_call_hashes.append(call_hash)
                tools_called.append(name)
                if name == "search_bank_policy":
                    doc_ids_cited.extend(r["doc_id"] for r in result)
            except FutureTimeoutError:
                content = json.dumps({"error": "Tool call timed out. Treat this data as unavailable."})
                tool_error = f"{name}: timeout"
            except ToolError as e:
                content = json.dumps({"error": f"Unavailable: {type(e).__name__}. Treat this data as unavailable -- do not guess."})
                tool_error = f"{name}: {type(e).__name__}: {e}"
            except Exception as e:  # noqa: BLE001 -- fail closed on literally anything unexpected
                content = json.dumps({"error": "Unavailable due to an unexpected error. Treat this data as unavailable."})
                tool_error = f"{name}: {type(e).__name__}: {e}"

        messages.append(ToolMessage(content=content, tool_call_id=call_id))

    return {
        "messages": messages,
        "tool_call_count": tool_call_count,
        "tool_call_hashes": tool_call_hashes,
        "tools_called": tools_called,
        "doc_ids_cited": doc_ids_cited,
        "tool_error": tool_error,
    }


def should_continue_tool_loop(state: dict) -> str:
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    return "finalize_answer"


SAFE_FALLBACK_ANSWER = {
    "answer": "I'm having trouble putting together a confirmed answer right now, so I don't want to guess.",
    "sources": [], "confidence": 0.0, "assumptions": [], "escalate": True,
}


def finalize_answer_node(state: dict) -> dict:
    llm = ChatOpenAI(model=MODEL, temperature=0).with_structured_output(FinalAnswer, include_raw=True)
    messages = list(state["messages"]) + [
        {"role": "user", "content": "Produce your final structured answer now, following the hard grounding rule."}
    ]
    try:
        result, raw_message = invoke_structured_with_resilience(llm, messages)
    except LLMUnavailable:
        # confidence=0.0 flows straight into the EXISTING confidence_gate
        # (Phase 7) and escalates from there -- no new routing needed, the
        # safe fallback is just an answer_json a real answer would never
        # legitimately produce.
        return {"answer_json": dict(SAFE_FALLBACK_ANSWER)}
    return {
        "answer_json": result.model_dump(),
        "token_usage": accumulate_tokens(state, raw_message),
    }
