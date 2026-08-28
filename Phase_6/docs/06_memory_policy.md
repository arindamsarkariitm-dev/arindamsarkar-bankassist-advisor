# Phase 6 — Memory Policy

## What exists, and why

**Short-term memory (per session):** the last 6 turns of a conversation, kept verbatim in **redacted** form (never raw text — see below), plus a rolling summary of anything older than that window. Scoped to one `session_id`, created fresh when an associate opens a case and starts talking to BankAssist Advisor.

**Long-term memory (per customer, survives across sessions):** preferences only — `language`, `style` (e.g. terse mode), `preferred_account_id`. Nothing else is allowed into long-term storage; `src/memory.py`'s `set_preference()` enforces an explicit allow-list and raises rather than silently accepting an unknown key. **Never** balances, account numbers, transaction details, or dispute specifics — those live in the account store (`data/`), not in memory, and are always looked up fresh via a tool call, never cached into a preference record.

## Why "verbatim" doesn't mean "raw"

Short-term turns are stored using the *same redacted text* `src/redaction.py` already produces for logging (`redact_text()`), not the original input/response. This is a deliberate design choice, not an oversight: it makes "PII tokenised at rest, never in plaintext memory" true by construction, rather than a policy someone has to remember to follow. Concretely:

- Amounts (`₹184,230.50` → `[AMOUNT]`) and customer names (`Priya Menon` → `[CUSTOMER_NAME]`) never survive into stored memory.
- Reference ids (`ACC-1001`, `CARD-2001`, `DSP-001`) **do** survive redaction (see `_SAFE_ID_RE` in `src/redaction.py`) — this is what lets pronoun/ellipsis resolution ("and the RD?") still work without needing raw PII in the store.

Verified directly: a real session dump before `/forget` shows `"The balance ... is [AMOUNT]"` in stored memory, never the actual figure (see `evidence/06_memory_reset_proof.md`).

## Retention and reset rules

| Rule | Behaviour |
|---|---|
| Session TTL | 30 minutes idle. `memory.get_session()` returns `None` for anything past that, even if the record still physically exists — an expired session is treated as gone, not silently revived. Verified directly by simulating a 31-minute-old `last_active` timestamp. |
| `/forget` | Clears **both** stores: this session's short-term turns AND this customer's long-term preferences (`clear_long_term=True` by default, per this policy — a customer asking to be forgotten should not have stale preferences resurface next session). Returns a real before/after dump as proof; see `evidence/06_memory_reset_proof.md`. |
| What survives a session | Only long-term preferences (opt-in, customer-scoped, non-sensitive). Short-term turns do not survive past the TTL or a `/forget`. |
| Who can access it | The graph itself, scoped to the session's own `customer_id` — there is no cross-customer read path. `memory.dump_session()` and `memory.get_preferences()` are read-only functions used only by evidence/test scripts in this project, never exposed as an agent tool (the agent never gets a "read raw memory" capability — it only ever sees the pre-formatted, already-redacted context note built by `format_conversation_context()`). |

## Known limitation, found during Phase 6 testing

The 5-turn conversation in `evidence/06_multiturn_transcripts.md` surfaces a real referent-resolution weakness: after turn 3 mentions a home loan (among other accounts), turns 4-5's "that one" / "it" resolve back to the savings account from turn 1 rather than the more recently-mentioned home loan. Short-term memory correctly makes the *information* available (both accounts are in the turn history), but nothing currently biases the LLM toward the most recently discussed referent when more than one candidate exists across a longer conversation. Documented here rather than quietly patched — a candidate fix (weighting recency more explicitly in `format_conversation_context()`, or asking one clarifying question when a pronoun has multiple plausible referents in history) belongs on the Phase 9 improvement roadmap, evidenced against this exact case rather than a synthetic one.
