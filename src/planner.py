"""
Multi-step planning for BankAssist Advisor.

Not a separate execution engine -- the agent's existing tool-calling loop
(src/nodes/agent.py) already handles calling multiple tools across
iterations. What this adds is a genuine PLANNING artefact: for a turn that
needs more than one piece of information combined, produce an explicit,
logged plan BEFORE the agent starts calling tools, so the decomposition is
visible and inspectable rather than only implicit in whatever tool calls
happen to occur. capstone_build_plan.md §6: "Log the plan object itself; a
visible plan is an artefact."
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from resilience import invoke_structured_with_resilience

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
MODEL = os.environ.get("OPENAI_MODEL_AGENT", "gpt-4o-mini")


class PlanStep(BaseModel):
    step: int
    description: str
    likely_tool: str | None = Field(default=None, description="Tool name this step probably needs, if any")


class Plan(BaseModel):
    is_multi_step: bool = Field(description="True only if answering requires combining 2+ separate facts/lookups.")
    steps: list[PlanStep] = Field(description="Empty if is_multi_step is False.")
    caveat: str | None = Field(default=None, description="Any caveat to attach to the final answer, e.g. 'this is information, not a recommendation.'")


PLANNER_SYSTEM_PROMPT = """You plan (but do not execute) how to answer one associate turn for a
banking co-pilot. Available tools: get_account_summary, list_recent_transactions,
search_bank_policy, check_dispute_status, calculate_emi.

Most turns are single-step (one lookup, or none). Only set is_multi_step=true when the turn
genuinely requires combining two or more separate facts to answer -- e.g. comparing two accounts,
or a fee explanation that needs both a transaction lookup AND a policy citation. For a comparison
that could read as steering the customer towards a decision (e.g. "which account is better"),
include a caveat noting this is informational only, not a recommendation.

Do not answer the question. Only plan."""


def make_plan(turn_input: str) -> tuple[Plan, object]:
    """Returns (Plan, raw_ai_message) -- the raw message carries
    .usage_metadata for token-count logging (capstone_build_plan.md §8).
    Retries once on timeout/429 and once on malformed output
    (invoke_structured_with_resilience); raises LLMUnavailable if both
    attempts fail -- plan_node treats planning as optional and degrades
    gracefully rather than failing the whole turn over it."""
    llm = ChatOpenAI(model=MODEL, temperature=0).with_structured_output(Plan, include_raw=True)
    return invoke_structured_with_resilience(llm, [
        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
        {"role": "user", "content": turn_input},
    ])
