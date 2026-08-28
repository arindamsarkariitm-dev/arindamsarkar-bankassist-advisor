"""
Escalation-threshold tuning (Phase 7, mechanism 3): after verify_grounding
passes, check the answer's own confidence against a threshold that's
STRICTER for topics with a history of negative feedback. This runs even
though the answer is technically grounded -- a grounded-but-low-confidence
answer on a topic that's burned associates before now escalates instead of
being delivered, per capstone_build_plan.md §7's "escalation-threshold
tuning ... the agent escalates to a human sooner where it has historically
underperformed."
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import adaptation  # noqa: E402
import feedback  # noqa: E402


def confidence_gate(state: dict) -> dict:
    topic = feedback.derive_topic(state.get("intent"), state.get("doc_ids_cited"), state.get("tools_called"))
    threshold = adaptation.confidence_threshold_for_topic(topic)
    confidence = (state.get("answer_json") or {}).get("confidence", 1.0)
    return {
        "confidence_gate_topic": topic,
        "confidence_gate_threshold": threshold,
        "confidence_below_threshold": confidence < threshold,
    }


def route_after_confidence_gate(state: dict) -> str:
    return "escalate" if state.get("confidence_below_threshold") else "answer"
