"""Appends this turn to short-term memory, in its REDACTED form only --
never the raw turn_input or raw final_response. Runs after redact_out
would (conceptually the same redaction pass log_node uses), just before
logging, so a turn is only ever remembered in the same PII-safe form it's
logged in."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import memory  # noqa: E402
from redaction import redact_text  # noqa: E402


def save_memory_node(state: dict) -> dict:
    redacted_response = redact_text(state.get("final_response", ""))
    memory.append_turn(
        session_id=state["session_id"],
        redacted_input=state.get("redacted_input_for_log", ""),
        redacted_response=redacted_response,
        intent=state.get("intent", "unknown"),
    )
    return {}
