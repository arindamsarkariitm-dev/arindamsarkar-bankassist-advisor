"""
[9] verify_grounding -- every number in the answer must appear verbatim in
a tool result actually received this turn. One regenerate attempt if not;
fail closed (suppress the answer, escalate) if the regenerate still isn't
grounded. capstone_build_plan.md §2/§9.

Heuristic scope: catches digit-based facts (amounts, percentages, dates,
ids) via regex, not prose claims in general -- documented limitation, not
a full semantic entailment checker. Good enough to catch the class of bug
this project cares about (a fabricated or stale numeric fact), which is
exactly what capstone_build_plan.md §9's test_grounding.py checks for too.
"""
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import ToolMessage
from langchain_openai import ChatOpenAI

from observability import accumulate_tokens
from resilience import LLMUnavailable, invoke_structured_with_resilience

from .agent import FinalAnswer

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
MODEL = os.environ.get("OPENAI_MODEL_AGENT", "gpt-4o-mini")

_NUMBER_RE = re.compile(r"₹?[\d][\d,]*\.?\d*%?")
MAX_REGENERATE = 1


def _numeric_tokens(text: str) -> list[str]:
    return [t for t in _NUMBER_RE.findall(text) if any(c.isdigit() for c in t)]


def _normalize_number(token: str) -> float | None:
    """₹184,230.50 / 184230.5 / 3.5% must all compare equal -- the raw JSON
    a tool returns (184230.5) never has the ₹/comma formatting a fluent
    answer uses (₹184,230.50). Comparing as normalized floats, not raw
    substrings, is what actually fixes the false-negative this caused: a
    correctly grounded answer (AS-02, real balance ₹184,230.50) was being
    discarded and regenerated into a needless "I don't have that
    information" deflection, purely because "₹184,230.50" is not a literal
    substring of {"balance": 184230.5}."""
    cleaned = token.replace("₹", "").replace(",", "").replace("%", "").strip()
    try:
        return round(float(cleaned), 2)
    except ValueError:
        return None


def _tool_output_text(state: dict) -> str:
    return " ".join(m.content for m in state.get("messages", []) if isinstance(m, ToolMessage))


def _tool_output_numbers(state: dict) -> set[float]:
    context_text = _tool_output_text(state)
    values = {_normalize_number(t) for t in _NUMBER_RE.findall(context_text)}
    values.discard(None)
    return values


def verify_grounding(state: dict) -> dict:
    answer_text = state["answer_json"]["answer"]
    raw_numbers = _numeric_tokens(answer_text)
    tool_numbers = _tool_output_numbers(state)

    ungrounded = []
    for raw in raw_numbers:
        value = _normalize_number(raw)
        if value is not None and value not in tool_numbers:
            ungrounded.append(raw)

    return {"grounding_ok": len(ungrounded) == 0, "_ungrounded_numbers": ungrounded}


def regenerate_answer_node(state: dict) -> dict:
    from .agent import SAFE_FALLBACK_ANSWER  # local import: avoids a circular import at module load time

    ungrounded = state.get("_ungrounded_numbers", [])
    llm = ChatOpenAI(model=MODEL, temperature=0).with_structured_output(FinalAnswer, include_raw=True)
    messages = list(state["messages"]) + [{
        "role": "user",
        "content": (
            f"Your previous answer stated these figures, which do not appear in any tool "
            f"result you received: {ungrounded}. Re-answer, using ONLY figures that "
            f"literally appear in a tool result. If you cannot support the answer without "
            f"them, say you don't have that information and recommend escalating instead."
        ),
    }]
    try:
        result, raw_message = invoke_structured_with_resilience(llm, messages)
    except LLMUnavailable:
        # This is already the one allowed regenerate attempt -- if the LLM
        # itself is unavailable here, fail closed the same way finalize_answer
        # does rather than trying yet another call.
        return {
            "answer_json": dict(SAFE_FALLBACK_ANSWER),
            "regenerate_count": state.get("regenerate_count", 0) + 1,
        }
    return {
        "answer_json": result.model_dump(),
        "token_usage": accumulate_tokens(state, raw_message),
        "regenerate_count": state.get("regenerate_count", 0) + 1,
    }


def route_after_grounding_check(state: dict) -> str:
    if state.get("grounding_ok"):
        return "ok"
    if state.get("regenerate_count", 0) < MAX_REGENERATE:
        return "regenerate"
    return "fail_closed"
