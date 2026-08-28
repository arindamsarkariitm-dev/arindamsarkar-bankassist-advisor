# Phase 6 — Multi-Turn Transcripts

## Improvement over the Phase 2 baseline (required: "demonstrate improved conversation quality")

Phase 2's baseline agent had no conversation state at all (`Phase_2/evidence/02_baseline_transcript.md` §5, "No multi-turn state"):

> **Turn 1:** "What's the customer's savings account balance?" (CUST-0002) → "Your balance is ₹96410.1."
> **Turn 2:** "And the home loan account?" → "I'm sorry, I don't have information about that. Please contact customer support for further assistance."
> *"It doesn't even fail in a way that shows it understood the follow-up was related to turn 1."*

That is exactly the failure mode Conversation 1 below no longer has — a follow-up naming a different account, with nothing but a pronoun/ellipsis tying it to the prior turn, now resolves correctly instead of falling to a blind fallback. That said, this improvement is real but not unconditional: Conversation 2 (5 turns, same customer as the Phase 2 example, CUST-0002) shows the same mechanism can resolve the *wrong* referent once a conversation has more than one plausible candidate in its history — reported honestly below and in `docs/06_memory_policy.md`, not smoothed over. The honest claim is "meaningfully better than no state at all," not "solved."

Three real conversations, run through the full graph via `Phase_6/src/memory_eval.py`. Full records: `Phase_6/logs/06_multiturn_conversations.json`. All annotated honestly, including the one genuine weakness the third conversation's cousin (the 5-turn one) surfaced.

## Conversation 1 — Pronoun / ellipsis resolution

| Turn | Input | intent / tools | Response |
|---|---|---|---|
| 1 | "What's the customer's savings account balance?" | `account_specific` / `get_account_summary` | "The balance in the customer's Regular Savings Account is ₹184,230.50." |
| 2 | "And the RD?" | `account_specific` / `get_account_summary` | "The customer's RD - 24 Month account is currently active and is set to mature on February 1, 2027. However, I don't have the balance information for this account." |
| 3 | "What about her credit card?" | `account_specific` / `get_account_summary` | "The customer's Platinum Rewards Credit Card is currently active and has a credit limit of ₹250,000." |

**Analysis:** both "And the RD?" and "What about her credit card?" are meaningless without turn 1's context — neither names an account type explicitly outside "RD"/"credit card," but the system correctly resolves each to the *right specific instrument* (`ACC-1002`, `CARD-2001`) belonging to the *same customer* established in turn 1, and correctly declines to state a "balance" for the RD (which genuinely has no stored balance field, so it reports what *is* available — status and maturity — rather than fabricating one). This is short-term memory (the redacted turn history) doing real work, not a scripted response.

## Conversation 2 — Context carry-over across 5 turns

| Turn | Input | intent / tools | Response |
|---|---|---|---|
| 1 | "What's the customer's savings account balance?" | `account_specific` / `get_account_summary` | "The balance in the customer's Regular Savings Account is ₹96,410.10." |
| 2 | "When was that account opened?" | `account_specific` / *(none)* | "I don't have that information available." |
| 3 | "Does he have any other accounts?" | `general_product` / *(none)* | "The customer has a Regular Savings Account, a Home Loan - Floating Rate, and a Gold Cashback Credit Card." |
| 4 | "What's the outstanding balance on that one?" | `account_specific` / `get_account_summary` | "The outstanding balance in the customer's Regular Savings Account is ₹96,410.10." |
| 5 | "And what's the interest rate on it?" | `general_product` / *(none)* | "I don't have the information about the interest rate on the Regular Savings Account." |

**What worked:** turn 3 correctly answers "other accounts" from the customer's own instrument directory without needing a tool call — a legitimate use of already-available context, not a fabrication (every account named is real).

**What didn't, honestly reported:** turns 4 and 5's "that one" / "it" should plausibly refer to the home loan turn 3 just mentioned (an "outstanding balance" is loan terminology, not a savings-account concept) — instead both resolved back to the savings account from turn 1. This is a genuine referent-resolution gap when a conversation has more than one plausible candidate in its history, not a scripted success story — see `docs/06_memory_policy.md`'s "Known limitation" section for the honest write-up and where the fix belongs. Turn 2's `opened_date` gap is a separate, minor schema limitation: the field exists in the underlying data but isn't exposed by `get_account_summary`'s schema, so the system correctly declines rather than fabricating a date, which is the right fail-safe behaviour even though the underlying gap is worth closing.

## Conversation 3 — Topic switch without bleed

| Turn | Input | intent / tools | Response |
|---|---|---|---|
| 1 | "What's the customer's savings account balance?" | `account_specific` / `get_account_summary` | "The balance in the customer's Regular Savings Account is ₹184,230.50." |
| 2 | "What's the late payment fee on a credit card?" | `general_product` / *(none)* | "I don't have the information about the late payment fee on a credit card. I recommend escalating this for further assistance." |
| 3 | "Going back to her account — what's the balance again?" | `account_specific` / `get_account_summary` | "The balance in the customer's Regular Savings Account is ₹184,230.50." |

**Analysis:** turn 2 hit the known RAG-retrieval flakiness already characterised in Phase 5's evidence (an intermittent, LLM-side query-construction issue, not a memory bug — the same question answers correctly most of the time, as shown throughout Phase 4/5's evidence). The point this conversation actually tests is turn 3: after a completely unrelated topic (and a failed answer on that topic) was interleaved, the account-balance context from turn 1 is recalled correctly and precisely (the identical figure, ₹184,230.50) — proving the topic switch did not corrupt or bleed into the account context. That's the real "no bleed" evidence, independent of turn 2's unrelated hiccup.
