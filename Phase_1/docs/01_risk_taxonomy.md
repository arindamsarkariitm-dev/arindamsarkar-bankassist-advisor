# Risk Taxonomy — BankAssist Advisor

Every case below must be escalated (Safety Requirement 3: "Escalate ambiguous or high-risk cases"), not troubleshot by the system. Ambiguity that doesn't fit a category below still gets **one** clarifying question, then escalation rather than an assumption.

| Risk category | Definition / trigger signals | Required system behaviour | Example (as relayed by the associate) |
|---|---|---|---|
| **Suspected fraud / unauthorised transaction** | Customer reports transactions they don't recognise; card or account compromise signals | Escalate immediately, no troubleshooting attempt, `create_escalation_ticket` to the fraud team, never ask the customer to "double-check" first | "Customer says there are three transactions she doesn't recognise." |
| **Dispute** | Customer wants to formally contest a charge | Explain the dispute *process* and *status* only; never predict the outcome; escalate/route to the dispute desk if no case exists yet | "Customer wants to dispute a ₹1,200 charge from a merchant she doesn't recognise." |
| **Hardship / collections** | Signs of financial distress, missed payments, requests for leniency | Explain hardship-policy *criteria*; escalate to the hardship/collections team; never promise a waiver or restructuring | "Customer says she can't make this month's EMI." |
| **Deceased account holder** | Associate indicates the account holder has passed away | Refuse to discuss further account details with the caller; escalate to the bereavement/estate team immediately; do not continue the original query | "Associate: the customer on the line says her father, the account holder, passed away last week." |
| **Regulatory complaint** | Customer invokes a regulator, ombudsman, or formal complaint | Escalate to the complaints/compliance team; do not argue the merits; log the complaint verbatim (redacted) | "Customer says she's filing a complaint with the banking ombudsman." |
| **Vulnerable customer** | Signs of diminished capacity, confusion, or elder/financial-abuse indicators relayed by the associate | Escalate to a specialist team; flag for extra care; the system never makes its own capacity judgement | "Associate flags that the customer sounds confused about basic account details." |
| **Distress signals** | Expressions of severe financial or emotional distress | Escalate; offer the bank's support resources; never attempt to counsel or reassure beyond that | "Customer says she's at the end of her rope over this fee." |

**Design note:** these seven categories map directly to the `classify_intent` node's risk-level output and the `policy_gate` routing table in `capstone_build_plan.md` §2. Every category above produces a real `create_escalation_ticket` call — the escalation queue is the one deliberate write in the system (§2's design rules). None of them are satisfied by a sentence in the response text alone; Phase 9's `test_escalation.py` checks that a ticket is actually produced for each.
