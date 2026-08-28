"""Runs the planner (src/planner.py) for every "proceed" turn and logs the
resulting Plan object into state. If the plan is multi-step, it's also
injected into the agent's initial context as a system note, so the tool-
calling loop is informed by its own decomposition rather than starting cold."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from observability import accumulate_tokens  # noqa: E402
from planner import make_plan  # noqa: E402
from resilience import LLMUnavailable  # noqa: E402

NO_PLAN = {"is_multi_step": False, "steps": [], "caveat": None}


def plan_node(state: dict) -> dict:
    try:
        plan, raw_message = make_plan(state["turn_input"])
    except LLMUnavailable:
        # Planning is an optimization, not a correctness requirement -- the
        # agent's tool-calling loop works fine without a plan, it just
        # loses the explicit up-front decomposition. Degrade to no plan
        # rather than failing the whole turn over a non-critical step.
        return {"plan": dict(NO_PLAN)}
    return {
        "plan": plan.model_dump(),
        "token_usage": accumulate_tokens(state, raw_message),
    }
