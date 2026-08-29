"""
Optional, opt-in LangSmith tracing -- redacts PII before anything reaches
LangSmith's cloud, unlike LangChain's default auto-instrumentation.

capstone_build_plan.md's instruction is "don't enable LangSmith tracing by
default... if you use it, gate it behind an env flag and trace only redacted
text." This module is that gate.

Deliberately does NOT use the standard LANGCHAIN_TRACING_V2 / LANGSMITH_TRACING
env-var names. Verified by reading the installed langsmith SDK
(langsmith/utils.py's tracing_is_enabled(), called from langchain_core's
tracers/context.py): setting either of those names -- in either the
LANGCHAIN_ or LANGSMITH_ namespace -- switches on LangChain's own *global*
auto-tracer, which uses a plain, unredacted `Client()` and fires independently
of whatever explicit callbacks a call site passes. Two tracers would then run
side by side: ours (redacted) and LangChain's own (raw), which would defeat
the entire point. Using a distinctly-named flag that doesn't start with
LANGCHAIN_ or LANGSMITH_ guarantees the *only* tracer that can ever run here
is the redacting one built below.

The redaction hook is LangSmith's own documented mechanism for this
(`Client(hide_inputs=..., hide_outputs=..., hide_metadata=...)`-- "a function
applied to serialized run inputs/outputs/metadata before sending to the
API"), not a bespoke interception -- confirmed against the installed
langsmith==0.11.1 Client signature and docstring, not assumed from memory.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from dotenv import load_dotenv  # noqa: E402
from langchain_core.tracers import LangChainTracer  # noqa: E402
from langsmith import Client  # noqa: E402

from redaction import redact_text  # noqa: E402

load_dotenv(ROOT / ".env")

ENABLED = os.environ.get("ENABLE_SAFE_LANGSMITH_TRACING", "").lower() == "true"
PROJECT_NAME = os.environ.get("LANGCHAIN_PROJECT", "bankassist-advisor")


def _redact_value(value):
    """Recursively apply redact_text() to every string in a run's
    inputs/outputs/metadata payload, whatever shape it takes -- LangSmith
    serializes these to plain dicts/lists/strings/numbers before this hook
    runs, so a generic recursive walk covers every run type (chat messages,
    tool calls, structured-output payloads) without needing to know that
    shape in advance."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: _redact_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(v) for v in value]
    return value  # numbers/bools/None -- no free text to leak


_tracer = None
if ENABLED:
    _redacting_client = Client(
        hide_inputs=_redact_value,
        hide_outputs=_redact_value,
        hide_metadata=_redact_value,
    )
    _tracer = LangChainTracer(project_name=PROJECT_NAME, client=_redacting_client)


def tracing_callbacks() -> list:
    """The callbacks list to pass at every LLM call site, e.g.
    `llm.invoke(messages, config={"callbacks": tracing_callbacks()})`.
    Empty when tracing is disabled (the default) -- callers can splat this
    in unconditionally, no if-check needed at each call site."""
    return [_tracer] if _tracer is not None else []
