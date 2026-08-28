---
doc_id: complaint-escalation-matrix
product: all
version: "2026.1"
effective_date: 2026-01-01
supersedes: null
status: current
---

# Complaint Escalation Matrix

*Synthetic policy document created for the BankAssist Advisor capstone project. Does not represent any real bank's actual escalation process.*

## Levels

| Level | Owner | Typical response time |
|---|---|---|
| Level 1 | Contact-centre / branch (first point of contact) | 3 business days |
| Level 2 | Regional Nodal Officer | 7 business days from Level 1 escalation |
| Level 3 | Principal Nodal Officer (head office) | 15 business days from Level 2 escalation |
| External | Banking Ombudsman (regulator) | Per regulator's own timeline; customer may approach directly if unresolved after 30 days or unsatisfied with the bank's final response |

## When the system must escalate rather than respond

Any of the following, relayed by the associate, is escalated immediately rather than answered or "smoothed over": the customer explicitly says they want to file a complaint, invokes a regulator or the Banking Ombudsman, expresses that a prior complaint was not resolved to their satisfaction, or shows clear signs of distress (see the Risk Taxonomy). The system does not attempt to talk the customer out of escalating or argue the merits of their complaint.

## What gets logged

A `create_escalation_ticket` call captures: the category (e.g., `regulatory_complaint`), a redacted summary of the issue, and any related case IDs (e.g., an unresolved dispute this complaint stems from). It does not capture the customer's verbatim words with PII intact — the redaction layer strips names, account numbers, and contact details before the ticket is written, consistent with the system's PII-in-logs policy.

## What the system can tell the customer

The current level and typical timeline for their complaint, and that they always retain the right to escalate externally to the Banking Ombudsman regardless of the bank's internal timeline. It cannot promise a specific resolution or timeline shorter than the matrix above.
