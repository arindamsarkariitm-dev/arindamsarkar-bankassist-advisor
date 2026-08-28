"""
Observability helpers: per-node latency timing and token-usage accumulation
across a turn. capstone_build_plan.md §8's structured-logging spec lists
"node latencies" and "token counts" alongside the fields src/nodes/log.py
already captured (trace_id, session_hash, intent, risk_level, tools
called, doc_ids, refusal/escalation codes, confidence, outcome) -- this
module is what actually produces those two.

instrument_node() wraps every node generically at registration time in
graph.py, so latency capture doesn't require touching each node's own
code. Token usage can't be captured that generically (a wrapper sees a
node's state diff, not what LLM calls happened inside it), so the handful
of LLM-calling nodes each call accumulate_tokens() explicitly and return
the running total in their own state update.
"""
import time
from functools import wraps


def instrument_node(name, fn):
    @wraps(fn)
    def wrapped(state):
        t0 = time.perf_counter()
        result = fn(state) or {}
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        node_latencies = dict(state.get("node_latencies", {}))
        # += , not =, because nodes in a loop (agent, tools, verify_grounding)
        # run more than once per turn -- the trace should show total time
        # spent in that node across the whole turn, not just the last visit.
        node_latencies[name] = round(node_latencies.get(name, 0) + elapsed_ms, 2)
        result["node_latencies"] = node_latencies
        return result
    return wrapped


def accumulate_tokens(state: dict, ai_message) -> dict:
    """Call with the raw AIMessage (has .usage_metadata) from any LLM call.
    Returns the new running total for the node to put in its state update
    as `token_usage`."""
    usage = getattr(ai_message, "usage_metadata", None) or {}
    totals = dict(state.get("token_usage") or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
    totals["prompt_tokens"] += usage.get("input_tokens", 0) or 0
    totals["completion_tokens"] += usage.get("output_tokens", 0) or 0
    totals["total_tokens"] += usage.get("total_tokens", 0) or 0
    return totals
