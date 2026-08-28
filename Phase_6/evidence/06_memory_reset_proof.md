# Phase 6 — Memory Reset (`/forget`) Proof

Real run: the 3-turn "topic switch" session (`evidence/06_multiturn_transcripts.md`, Conversation 3) plus a manually-set `style: terse` preference, then `/forget` sent as the 4th turn on the same `session_id`. Full record: `Phase_6/logs/06_memory_reset_proof.json`.

## Before `/forget`

```json
{
  "session": {
    "session_id": "47371bf1-8997-445d-bd6f-b968571aa87e",
    "customer_id": "CUST-0001",
    "turns": [
      {
        "redacted_input": "What's the customer's savings account balance?",
        "redacted_response": "The balance in the customer's Regular Savings Account is [AMOUNT].",
        "intent": "account_specific"
      },
      {
        "redacted_input": "What's the late payment fee on a credit card?",
        "redacted_response": "I don't have the information about the late payment fee on a credit card. I recommend escalating this for further assistance.",
        "intent": "general_product"
      },
      {
        "redacted_input": "Going back to her account -- what's the balance again?",
        "redacted_response": "The balance in the customer's Regular Savings Account is [AMOUNT].",
        "intent": "account_specific"
      }
    ],
    "rolling_summary": ""
  },
  "preferences": { "style": "terse" }
}
```

Note what's already true here, before any reset happens: every stored turn shows `[AMOUNT]` where the real figure (₹184,230.50) was — the redaction-at-rest guarantee from `docs/06_memory_policy.md` holds even in the pre-reset state, not just after.

## The `/forget` turn

**Input:** `/forget`
**Response:** `"Done -- I've cleared this session's memory and this customer's saved preferences."`

## After `/forget`

```json
{
  "session": null,
  "preferences": {}
}
```

Both stores are gone: `memory.dump_session()` returns `None` (not an empty-but-present record — the session key itself is removed), and `memory.get_preferences()` returns an empty dict (the `style: terse` preference, which existed in a different store entirely from the session, is also gone — confirming `/forget` clears both stores as specified, not just the one the triggering turn happened to touch).
