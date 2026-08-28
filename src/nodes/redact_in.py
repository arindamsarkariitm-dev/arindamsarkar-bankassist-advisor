"""[2] redact_in -- produce the ONLY version of the turn's input text that
logging is ever allowed to see. The real (unredacted) turn_input keeps
flowing through the rest of the graph unchanged; only redacted_input_for_log
gets written to the trace in [10]."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from redaction import redact_text  # noqa: E402


def redact_in(state: dict) -> dict:
    return {"redacted_input_for_log": redact_text(state["turn_input"])}
