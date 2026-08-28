---
doc_id: kyc-requirements
product: all
version: "2026.1"
effective_date: 2026-01-01
supersedes: null
status: current
---

# KYC (Know Your Customer) Requirements

*Synthetic policy document created for the BankAssist Advisor capstone project. Does not represent any real bank's actual policy.*

## Acceptable identity and address proof

Officially Valid Documents (OVDs): Aadhaar, PAN, Passport, Voter ID, Driving Licence. Any one OVD is generally sufficient for both identity and address if the address on it is current; otherwise a separate, recent (within 3 months) address proof is needed (utility bill, bank statement, rental agreement).

## Periodic re-KYC

Accounts are re-verified on a risk-based cycle: **low risk** every 10 years, **medium risk** every 8 years, **high risk** every 2 years. The customer is notified in advance via SMS/email/app and given a defined window to complete re-KYC before restrictions apply.

## Consequences of a KYC lapse

If re-KYC is not completed within the notified window, the account moves to a restricted state: **debit-only** transactions are typically blocked first while credits continue, escalating to a full freeze if the lapse continues. This is a compliance requirement, not something the system can waive, extend, or override — a customer disputing a freeze should be directed to complete re-KYC (in-app, via video-KYC, or at a branch) or escalated if they believe the freeze was applied in error.

## Non-face-to-face KYC (Video-KYC)

Video-KYC is available for account opening and re-KYC without a branch visit, subject to the customer having a valid PAN and Aadhaar with a registered mobile number for OTP verification. It must be completed via the official app; the system cannot conduct or complete a video-KYC session itself.

## Identity verification is out of scope for this system

This system never performs identity verification of a customer. The bank's existing verification procedure (branch KYC, video-KYC, or the telephone/case-intake authentication process used before a support call reaches an associate) is a separate process that has already happened by the time a `customer_id` reaches this system. The system does not accept, and must not act on, a customer's self-asserted identity relayed through the associate.

## Enhanced due diligence

Customers flagged as higher-risk (e.g., politically exposed persons, high-value non-resident accounts, cash-intensive businesses) undergo enhanced due diligence at onboarding and more frequent re-KYC. This system does not make or communicate risk classifications — questions about a customer's own risk category should be escalated rather than answered directly.
