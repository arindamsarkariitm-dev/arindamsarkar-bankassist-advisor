"""
LangSmith tracing -- attempted, tested against live traffic, and found
unsafe. HARD-DISABLED below regardless of the env flag. Kept in the repo,
not deleted, because the investigation and the redaction logic it contains
are real evidence, not dead code to hide.

capstone_build_plan.md's instruction was "don't enable LangSmith tracing by
default... if you use it, gate it behind an env flag and trace only redacted
text." This module built exactly that gate, using LangSmith's own documented
mechanism for it: `Client(hide_inputs=fn, hide_outputs=fn, hide_metadata=fn)`,
where each function receives a run's already-serialized inputs/outputs/
metadata and returns a redacted copy before upload -- confirmed against the
installed langsmith==0.11.1 Client signature and docstring, not assumed.
_redact_value() below, reusing src/redaction.py's existing PII layer, is
verified correct in isolation by tests/test_no_pii_in_langsmith.py.

The env-var name was also deliberately chosen NOT to be LANGCHAIN_TRACING_V2
/ LANGSMITH_TRACING: setting either of those (in either namespace) switches
on LangChain's own global auto-tracer with a plain, unredacted `Client()`,
independent of any explicit callback a call site passes -- confirmed by
reading langsmith/utils.py's tracing_is_enabled(). A distinctly-named flag
avoids that path entirely.

WHERE IT FAILED, empirically (28-29 Aug 2026): live-tested against the
deployed graph with real turns, checked on LangSmith's dashboard across two
independent runs -- one with default (batched, async) tracing, one with
`Client(auto_batch_tracing=False)` (fully synchronous) -- and confirmed a
third time after logging out and reopening the trace in a completely
different, freshly-authenticated browser, ruling out client-side caching.
Result, consistent every time: the associate's own question (the "human"
message) redacted correctly. The AI's generated final-answer text and the
account-balance figure returned by a tool call did NOT -- both reached
LangSmith's servers as plain text, despite a local diagnostic proving
_redact_value() was invoked with that exact string, mid-run, and returned
the correctly redacted result. The gap sits somewhere inside how
langsmith/langchain_core persist a composite `RunnableSequence` run's final
output -- a different internal path than the one hide_outputs demonstrably
reaches -- not fully isolated despite ruling out both batching and caching
as causes. A real fix would mean intercepting LangChain's own message/
generation objects directly in a callback, before LangChain's tracer ever
hands them to LangSmith's Client, rather than relying on the Client-level
hide_* hooks this module used. Not attempted -- LangSmith was never a
literal requirement of the actual brief (see capstone-agreed-decisions.md),
and the project's own JSONL structured logger (src/nodes/log.py +
src/observability.py) already satisfies the real "logging and tracing"
requirement, verified safe throughout Phases 1-8.

Given real (synthetic) customer data was confirmed reaching a third-party
service unredacted, `tracing_callbacks()` returns `[]` unconditionally
below -- setting ENABLE_SAFE_LANGSMITH_TRACING=true no longer has any
effect. This is deliberate: fail closed on a capability proven unsafe,
consistent with every other safety decision in this project (capability by
omission for money movement, fail-closed grounding verification), rather
than leave a flag that looks safe to flip but isn't.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from dotenv import load_dotenv  # noqa: E402

from redaction import redact_text  # noqa: E402

load_dotenv(ROOT / ".env")

# Read for introspection/documentation purposes only -- no longer gates
# anything. See the module docstring for why.
ENABLED = os.environ.get("ENABLE_SAFE_LANGSMITH_TRACING", "").lower() == "true"
PROJECT_NAME = os.environ.get("LANGCHAIN_PROJECT", "bankassist-advisor")

KNOWN_UNSAFE = True  # see module docstring -- do not flip without a real fix


def _redact_value(value):
    """Recursively apply redact_text() to every string in a run's
    inputs/outputs/metadata payload, whatever shape it takes. Verified
    correct in isolation (tests/test_no_pii_in_langsmith.py) -- the bug this
    module hit was in how LangSmith applies this function to certain run
    types, not in this function itself."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: _redact_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(v) for v in value]
    return value  # numbers/bools/None -- no free text to leak


def tracing_callbacks() -> list:
    """The callbacks list callers splat into config={"callbacks": ...} at
    every LLM call site. Always [] -- see module docstring. Kept as a
    function (not just removing the call sites) so re-enabling this, if a
    real fix is ever built, is a one-line change here rather than touching
    src/resilience.py again."""
    if KNOWN_UNSAFE:
        return []
    return []  # unreachable while KNOWN_UNSAFE is True; kept explicit on purpose
