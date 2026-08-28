"""
The BankAssist Advisor LangGraph StateGraph -- the spine described in
capstone_build_plan.md §2, built for real in Phase 5, extended with
short-term/long-term memory + planning in Phase 6, and adaptive behaviour
(few-shot injection in `agent`, confidence_gate) in Phase 7.

    ingest -> [is_forget_command?]
        -> yes: forget_node -----------------------------------> log -> END
        -> no:  redact_in -> classify_intent -> policy_gate
                    -> refuse_node ------------------------------> save_memory -> log -> END
                    -> escalate_node ----------------------------> save_memory -> log -> END
                    -> clarify_node ------------------------------> save_memory -> log -> END
                    -> plan_node -> agent <-> tools (loop, bounded)
                          -> finalize_answer -> verify_grounding
                                -> confidence_gate
                                      -> answer_to_response --------> save_memory -> log -> END
                                      -> low_confidence_escalate ----> save_memory -> log -> END
                                -> regenerate_answer -> verify_grounding (loop, max 1x)
                                -> fail_closed_node --------------> save_memory -> log -> END

Run this module directly for a quick manual smoke test.
"""
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC_DIR))

from langgraph.graph import END, START, StateGraph  # noqa: E402

import adaptation  # noqa: E402
import memory  # noqa: E402
from nodes.agent import agent_node, finalize_answer_node, should_continue_tool_loop, tools_node  # noqa: E402
from nodes.classify import classify_intent  # noqa: E402
from nodes.confidence_gate import confidence_gate, route_after_confidence_gate  # noqa: E402
from nodes.ingest import ingest  # noqa: E402
from nodes.log import log_node  # noqa: E402
from observability import instrument_node  # noqa: E402
from nodes.plan import plan_node  # noqa: E402
from nodes.policy_gate import policy_gate  # noqa: E402
from nodes.redact_in import redact_in  # noqa: E402
from nodes.save_memory import save_memory_node  # noqa: E402
from nodes.terminal import (  # noqa: E402
    answer_to_response_node,
    clarify_node,
    escalate_node,
    fail_closed_node,
    forget_node,
    low_confidence_escalate_node,
    refuse_node,
    service_unavailable_node,
)
from nodes.verify import regenerate_answer_node, route_after_grounding_check, verify_grounding  # noqa: E402
from state import GraphState  # noqa: E402


def build_graph():
    g = StateGraph(GraphState)

    # Every node is wrapped with instrument_node so per-node latency is
    # captured generically (capstone_build_plan.md §8's "node latencies"),
    # without having to hand-instrument each node's own code.
    g.add_node("ingest", instrument_node("ingest", ingest))
    g.add_node("forget_node", instrument_node("forget_node", forget_node))
    g.add_node("redact_in", instrument_node("redact_in", redact_in))
    g.add_node("classify_intent", instrument_node("classify_intent", classify_intent))
    g.add_node("policy_gate", instrument_node("policy_gate", policy_gate))
    g.add_node("plan_node", instrument_node("plan_node", plan_node))
    g.add_node("service_unavailable_node", instrument_node("service_unavailable_node", service_unavailable_node))
    g.add_node("refuse_node", instrument_node("refuse_node", refuse_node))
    g.add_node("escalate_node", instrument_node("escalate_node", escalate_node))
    g.add_node("clarify_node", instrument_node("clarify_node", clarify_node))
    g.add_node("agent", instrument_node("agent", agent_node))
    g.add_node("tools", instrument_node("tools", tools_node))
    g.add_node("finalize_answer", instrument_node("finalize_answer", finalize_answer_node))
    g.add_node("verify_grounding", instrument_node("verify_grounding", verify_grounding))
    g.add_node("regenerate_answer", instrument_node("regenerate_answer", regenerate_answer_node))
    g.add_node("confidence_gate", instrument_node("confidence_gate", confidence_gate))
    g.add_node("answer_to_response", instrument_node("answer_to_response", answer_to_response_node))
    g.add_node("low_confidence_escalate", instrument_node("low_confidence_escalate", low_confidence_escalate_node))
    g.add_node("fail_closed", instrument_node("fail_closed", fail_closed_node))
    g.add_node("save_memory", instrument_node("save_memory", save_memory_node))
    g.add_node("log", instrument_node("log", log_node))

    g.add_edge(START, "ingest")
    g.add_conditional_edges("ingest", lambda s: "forget" if s.get("is_forget_command") else "continue", {
        "forget": "forget_node",
        "continue": "redact_in",
    })
    g.add_edge("redact_in", "classify_intent")
    g.add_edge("classify_intent", "policy_gate")

    g.add_conditional_edges("policy_gate", lambda s: s["route"], {
        "service_unavailable": "service_unavailable_node",
        "refuse": "refuse_node",
        "escalate": "escalate_node",
        "clarify": "clarify_node",
        "proceed": "plan_node",
    })
    g.add_edge("plan_node", "agent")

    g.add_conditional_edges("agent", should_continue_tool_loop, {
        "tools": "tools",
        "finalize_answer": "finalize_answer",
    })
    g.add_edge("tools", "agent")
    g.add_edge("finalize_answer", "verify_grounding")

    g.add_conditional_edges("verify_grounding", route_after_grounding_check, {
        "ok": "confidence_gate",
        "regenerate": "regenerate_answer",
        "fail_closed": "fail_closed",
    })
    g.add_edge("regenerate_answer", "verify_grounding")

    g.add_conditional_edges("confidence_gate", route_after_confidence_gate, {
        "answer": "answer_to_response",
        "escalate": "low_confidence_escalate",
    })

    g.add_edge("service_unavailable_node", "save_memory")
    g.add_edge("refuse_node", "save_memory")
    g.add_edge("escalate_node", "save_memory")
    g.add_edge("clarify_node", "save_memory")
    g.add_edge("answer_to_response", "save_memory")
    g.add_edge("low_confidence_escalate", "save_memory")
    g.add_edge("fail_closed", "save_memory")
    g.add_edge("save_memory", "log")
    g.add_edge("forget_node", "log")
    g.add_edge("log", END)

    return g.compile()


APP = build_graph()


def run_turn(turn_input: str, customer_id: str, session_id: str | None = None, locale: str = "en-IN") -> dict:
    """session_id: pass None to start a new session (a new id is generated
    and returned in result['session_id']); pass a prior turn's session_id
    to continue that same conversation with its short-term memory intact."""
    session_id = session_id or memory.new_session_id()
    result = APP.invoke({
        "turn_input": turn_input, "customer_id": customer_id,
        "session_id": session_id, "locale": locale,
    })
    result["session_id"] = session_id
    return result


def give_feedback(turn_result: dict, customer_id: str, signal: str, reason_code: str | None = None,
                   corrected_answer: str | None = None) -> dict:
    """Phase 8's POST /feedback will call this directly with the result of
    a prior run_turn(...) call. Mirrors what a real client has on hand
    right after seeing a response -- the full turn result, not just an id."""
    return adaptation.process_feedback(
        session_id=turn_result["session_id"], customer_id=customer_id,
        turn_input=turn_result.get("turn_input", ""), final_response=turn_result.get("final_response", ""),
        intent=turn_result.get("intent"), doc_ids_cited=turn_result.get("doc_ids_cited"),
        tools_called=turn_result.get("tools_called"), signal=signal,
        reason_code=reason_code, corrected_answer=corrected_answer,
    )


if __name__ == "__main__":
    sid = None
    for turn in [
        "Customer's asking why she was charged ₹590 on 14 July — can you check?",
        "And what's her savings account balance?",
    ]:
        result = run_turn(turn, "CUST-0001", session_id=sid)
        sid = result["session_id"]
        print(f"> {turn}")
        print("  intent:", result.get("intent"), "| route:", result.get("route"))
        print("  final_response:", result.get("final_response"))
        print()
