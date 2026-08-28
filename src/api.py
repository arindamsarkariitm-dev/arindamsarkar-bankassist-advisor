"""
FastAPI layer for BankAssist Advisor. Thin wrapper around src/graph.py --
all the actual logic (routing, tools, memory, adaptation, resilience)
lives there; this module is just the HTTP surface capstone_build_plan.md
§8 asks for: POST /chat, POST /feedback, GET /health.
"""
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC_DIR))

from fastapi import FastAPI, HTTPException  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from graph import give_feedback, run_turn  # noqa: E402

app = FastAPI(title="BankAssist Advisor API", version="1.0.0")

# In-memory store of recent turn results, keyed by trace_id, so /feedback
# can be given just a trace_id rather than the whole turn payload back --
# a real deployment would use a short-TTL cache (e.g. Redis) for this
# instead of a process-local dict.
_RECENT_TURNS: dict[str, dict] = {}
_RECENT_TURNS_MAX = 500


class ChatRequest(BaseModel):
    turn_input: str
    customer_id: str
    session_id: str | None = None
    locale: str = "en-IN"


class ChatResponse(BaseModel):
    trace_id: str
    session_id: str
    final_response: str
    intent: str | None = None
    route: str | None = None
    escalation_code: str | None = None
    refusal_code: str | None = None


class FeedbackRequest(BaseModel):
    trace_id: str
    customer_id: str
    signal: str  # "up" | "down"
    reason_code: str | None = None
    corrected_answer: str | None = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    result = run_turn(req.turn_input, req.customer_id, session_id=req.session_id, locale=req.locale)
    trace_id = result.get("trace", {}).get("trace_id", result["session_id"])

    _RECENT_TURNS[trace_id] = result
    if len(_RECENT_TURNS) > _RECENT_TURNS_MAX:
        _RECENT_TURNS.pop(next(iter(_RECENT_TURNS)))

    return ChatResponse(
        trace_id=trace_id,
        session_id=result["session_id"],
        final_response=result.get("final_response", ""),
        intent=result.get("intent"),
        route=result.get("route"),
        escalation_code=result.get("escalation_code"),
        refusal_code=result.get("refusal_code"),
    )


@app.post("/feedback")
def feedback(req: FeedbackRequest):
    turn_result = _RECENT_TURNS.get(req.trace_id)
    if not turn_result:
        raise HTTPException(status_code=404, detail="Unknown or expired trace_id -- feedback must reference a recent /chat response.")
    outcome = give_feedback(
        turn_result, req.customer_id, req.signal, req.reason_code, req.corrected_answer,
    )
    return {"stored": True, "style_adapted_now": outcome["style_adapted_now"]}
