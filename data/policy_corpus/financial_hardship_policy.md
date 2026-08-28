---
doc_id: financial-hardship-policy
product: all
version: "2026.1"
effective_date: 2026-01-01
supersedes: null
status: current
---

# Financial Hardship & Collections Policy

*Synthetic policy document created for the BankAssist Advisor capstone project. Does not represent any real bank's actual policy.*

## Eligibility criteria (informational only)

A customer may apply for hardship assistance if they can demonstrate a genuine, typically temporary, disruption to their ability to meet repayment obligations — for example: job loss, a medical emergency, a natural disaster affecting income or property, or a significant, documented drop in business income for self-employed customers.

## Available options (subject to approval)

- **EMI moratorium** — a temporary pause on EMI payments (typically 1–3 months), with interest continuing to accrue and the tenure extended accordingly.
- **Loan restructuring** — revised EMI amount and/or tenure to reduce the monthly burden, subject to credit-team review.
- **Settlement** — for severe, prolonged hardship, a negotiated partial settlement of the outstanding amount; this affects the customer's credit history and is only considered as a last resort.

## Required documentation

Proof of the hardship event (termination letter, medical bills, disaster-relief documentation, or income statements showing the decline), the last 3 months' bank statements, and a written request describing the assistance sought.

## What the system can and cannot do

The system **can** explain these criteria and options, and **must** escalate any customer indicating difficulty paying to the Hardship/Collections team via `create_escalation_ticket` — this is one of the risk-taxonomy categories that always escalates, never gets troubleshot in-chat. The system **cannot** approve, pre-approve, promise, or estimate the outcome of a hardship application; any of these require human credit-team review against the customer's full financial picture, which the system does not have and is not authorised to assess.

## Distress signals

Language suggesting severe financial or emotional distress (not just a request for a moratorium) should be treated as a distress-signal escalation in addition to a hardship one — see the Risk Taxonomy for required behaviour, including offering the bank's support resources without attempting to counsel the customer directly.
