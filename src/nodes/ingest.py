"""[1] ingest -- attach session context. customer_id and locale must already
be verified upstream (by whatever authenticates the associate's session,
e.g. the FastAPI layer in Phase 8) and are never inferred from the turn
text itself -- see the deployment assumption in docs/01_problem_framing.md.

Phase 6 addition: starts/resumes the session's short-term memory and loads
the customer's long-term preferences. A session past its 30-minute idle TTL
is treated as gone, not silently revived -- start_or_resume_session handles
that by starting a fresh one."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import memory  # noqa: E402

FORGET_COMMANDS = {"/forget"}


def ingest(state: dict) -> dict:
    if not state.get("customer_id"):
        raise ValueError("ingest: customer_id missing from session context -- refusing to proceed")
    if not state.get("session_id"):
        raise ValueError("ingest: session_id missing -- every turn must belong to a session")

    is_forget = state["turn_input"].strip().lower() in FORGET_COMMANDS
    if is_forget:
        return {"locale": state.get("locale", "en-IN"), "is_forget_command": True}

    session = memory.start_or_resume_session(state["session_id"], state["customer_id"])
    preferences = memory.get_preferences(state["customer_id"])
    return {
        "locale": state.get("locale", "en-IN"),
        "is_forget_command": False,
        "short_term_turns": session["turns"],
        "rolling_summary": session["rolling_summary"],
        "preferences": preferences,
    }
