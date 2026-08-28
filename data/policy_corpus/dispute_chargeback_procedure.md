---
doc_id: dispute-chargeback-procedure
product: all
version: "2026.1"
effective_date: 2026-01-01
supersedes: null
status: current
---

# Dispute & Chargeback Procedure

*Synthetic policy document created for the BankAssist Advisor capstone project. Does not represent any real bank's actual procedure.*

## When to raise a dispute

A dispute may be raised for: a transaction the customer does not recognise, a duplicate charge from the same merchant, an incorrect amount charged, goods/services paid for but not received, or a subscription that was not cancelled as requested. Suspected **unauthorised** transactions (card lost/stolen, credentials compromised) are a fraud case, not a standard billing dispute, and must be escalated immediately rather than filed through the standard dispute flow.

## How a case is opened

The associate (or customer, via the app) files a case with: the transaction ID(s), the disputed amount, and a short description of the issue. The case is assigned a `case_id` and a status of `under_investigation`.

## Timeline

| Stage | Typical duration |
|---|---|
| Acknowledgement | Same day |
| Merchant/network contacted | Within 2 business days |
| Provisional credit (where applicable, per network rules) | Within 10 business days |
| Final resolution | Within 30–45 business days |

These are typical timelines, not guarantees — some cases (e.g., international merchants, complex chargebacks) take longer. The system should always state the timeline as indicative and offer to check current status via `check_dispute_status`, never promise a specific resolution date.

## What the system can and cannot say

The system **can** state a case's current status, stage, and history, and explain the general process and required evidence. It **cannot** predict or promise the outcome of an open dispute, and cannot state that a refund "will definitely" happen — outcomes depend on merchant response and network rules, which are outside the system's knowledge.

## Duplicate charges specifically

A same-merchant, same-amount, same-day charge appearing twice is a common and usually straightforward dispute category. The associate should confirm with the customer that only one purchase was made before filing, since occasionally a genuine second purchase (e.g., a reorder) can look identical to a duplicate.

## Escalation beyond SLA

If a case remains open past its SLA target date, or the customer expresses dissatisfaction with the process, escalate to the Complaint Escalation Matrix procedure.
