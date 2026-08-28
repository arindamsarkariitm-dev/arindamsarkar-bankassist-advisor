"""
Short-term and long-term memory for BankAssist Advisor.

Short-term (per session, tied to one call): last 6 turns verbatim (redacted
text, never raw -- see below), plus a rolling summary of anything older.
Session TTL: 30 minutes idle.

Long-term (per customer, survives across sessions): PREFERENCES ONLY --
language, brevity ("terse mode"), preferred account. Never balances,
account numbers, or transaction details. Stored as an opaque token
(customer_id), resolved against the live data store at call time, not
duplicated into the preference record itself.

"Verbatim" here means the REDACTED turn text (src/redaction.py), not the
raw text -- this is what makes "PII tokenised at rest, never in plaintext
memory" true by construction rather than by policy. Reference ids
(ACC-/CARD-/DSP-/TXN-) survive redaction, so context like "which account
were we just discussing" still resolves; amounts and names do not survive,
so a memory dump never contains them.

Storage: a single JSON file (data/memory_store.json), loaded/saved on each
mutation. Adequate for this capstone's scope; a real deployment would use a
session store (e.g. Redis) for short-term and a customer-profile table for
long-term, with the same schema.
"""
import json
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORE_PATH = ROOT / "data" / "memory_store.json"

SESSION_TTL_SECONDS = 30 * 60
MAX_VERBATIM_TURNS = 6
ALLOWED_PREFERENCE_KEYS = {"language", "style", "preferred_account_id"}


def _load_store() -> dict:
    if STORE_PATH.exists():
        with open(STORE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"sessions": {}, "preferences": {}}


def _save_store(store: dict) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def new_session_id() -> str:
    return str(uuid.uuid4())


def get_session(session_id: str) -> dict | None:
    """Returns the session dict, or None if it doesn't exist or has expired
    past the 30-minute idle TTL (an expired session is treated as gone, not
    silently revived)."""
    store = _load_store()
    session = store["sessions"].get(session_id)
    if not session:
        return None
    if time.time() - session["last_active"] > SESSION_TTL_SECONDS:
        return None
    return session


def start_or_resume_session(session_id: str, customer_id: str) -> dict:
    store = _load_store()
    session = store["sessions"].get(session_id)
    now = time.time()
    if not session or now - session["last_active"] > SESSION_TTL_SECONDS:
        session = {
            "session_id": session_id,
            "customer_id": customer_id,
            "created_at": now,
            "last_active": now,
            "turns": [],
            "rolling_summary": "",
        }
    session["last_active"] = now
    store["sessions"][session_id] = session
    _save_store(store)
    return session


def append_turn(session_id: str, redacted_input: str, redacted_response: str, intent: str) -> None:
    """Appends one (already-redacted) turn to short-term memory. When this
    pushes the verbatim window past MAX_VERBATIM_TURNS, the oldest turn is
    folded into the rolling summary rather than kept verbatim indefinitely."""
    store = _load_store()
    session = store["sessions"].get(session_id)
    if not session:
        return
    session["turns"].append({
        "redacted_input": redacted_input,
        "redacted_response": redacted_response,
        "intent": intent,
        "timestamp": time.time(),
    })
    while len(session["turns"]) > MAX_VERBATIM_TURNS:
        oldest = session["turns"].pop(0)
        note = f"[{oldest['intent']}] {oldest['redacted_input']} -> {oldest['redacted_response']}"
        session["rolling_summary"] = (session["rolling_summary"] + " | " + note).strip(" |")
    session["last_active"] = time.time()
    store["sessions"][session_id] = session
    _save_store(store)


def get_preferences(customer_id: str) -> dict:
    store = _load_store()
    return dict(store["preferences"].get(customer_id, {}))


def set_preference(customer_id: str, key: str, value) -> None:
    if key not in ALLOWED_PREFERENCE_KEYS:
        raise ValueError(f"'{key}' is not an allowed long-term preference key -- "
                          f"long-term memory is preferences only: {ALLOWED_PREFERENCE_KEYS}")
    store = _load_store()
    store["preferences"].setdefault(customer_id, {})[key] = value
    _save_store(store)


def forget(session_id: str, customer_id: str | None = None, clear_long_term: bool = True) -> dict:
    """The /forget command: clears short-term memory for this session, and
    (by default, matching capstone_build_plan.md §6: "/forget clears both
    stores") long-term preferences for this customer too. Returns a dump of
    what was cleared, for the before/after reset-proof evidence."""
    store = _load_store()
    cleared = {
        "session_cleared": store["sessions"].pop(session_id, None),
        "preferences_cleared": None,
    }
    if clear_long_term and customer_id:
        cleared["preferences_cleared"] = store["preferences"].pop(customer_id, None)
    _save_store(store)
    return cleared


def format_conversation_context(state: dict) -> str | None:
    """Renders short_term_turns + rolling_summary + preferences (already
    loaded into state by ingest) into a compact note for classify_intent
    and the agent -- both need this to resolve pronouns/ellipsis ("and the
    other account?") and to honour style preferences. Returns None if
    there's nothing to add (fresh session, no preferences)."""
    turns = state.get("short_term_turns") or []
    rolling_summary = state.get("rolling_summary") or ""
    preferences = state.get("preferences") or {}
    if not turns and not rolling_summary and not preferences:
        return None

    parts = []
    if rolling_summary:
        parts.append(f"Earlier in this session (summarised): {rolling_summary}")
    if turns:
        lines = [f'  - associate asked: "{t["redacted_input"]}" -> replied: "{t["redacted_response"]}"' for t in turns]
        parts.append("Recent turns this session, most recent last:\n" + "\n".join(lines))
    if preferences:
        parts.append(f"This customer's saved preferences: {preferences}")
    return "\n".join(parts)


def dump_session(session_id: str) -> dict | None:
    """Read-only snapshot, for evidence capture. Never used by the graph
    itself -- only by tests/evidence scripts."""
    store = _load_store()
    return store["sessions"].get(session_id)
