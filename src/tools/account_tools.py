"""
Account-lane tools: get_account_summary, list_recent_transactions,
check_dispute_status. All three are read-only against the mock data store.

Each is produced by a factory (make_*_tool(customer_id)) that CLOSES OVER
the session's verified customer_id -- customer_id is never an LLM-visible
tool argument, so no prompt injection can substitute a different customer.
The account_id / case_id ownership check happens in code here, not in the
prompt, per capstone_build_plan.md §5.
"""
from datetime import datetime, timedelta

from langchain_core.tools import tool

from . import _data
from .exceptions import AccountNotOwned, NotFound
from .schemas import AccountSummary, DisputeCase, Txn


def make_get_account_summary_tool(customer_id: str):
    @tool
    def get_account_summary(account_id: str) -> dict:
        """Look up a customer's own account OR card (savings, recurring
        deposit, home loan, or credit/debit card) by its id. Returns
        balance (or outstanding principal for a loan, or credit_limit for a
        card -- cards have no stored balance field; use
        list_recent_transactions for a card's recent spend), product name,
        status, and rate/due-date details. Only works for instruments
        belonging to the currently authenticated customer."""
        if not _data.customer_owns_instrument(customer_id, account_id):
            raise AccountNotOwned(account_id)
        record, kind = _data.get_account_or_card(account_id)
        if not record:
            raise NotFound(account_id)
        fields = {k: v for k, v in record.items() if k in AccountSummary.model_fields}
        fields.setdefault("account_id", account_id)
        fields.setdefault("type", kind)
        fields.setdefault("currency", "INR")  # not stored on card records; all accounts/cards here are INR
        return AccountSummary(**fields).model_dump(exclude_none=True)

    return get_account_summary


def make_list_recent_transactions_tool(customer_id: str):
    @tool
    def list_recent_transactions(account_id: str, days: int = 90, contains: str | None = None) -> list[dict]:
        """List a customer's own transactions on an account or card, within
        the last `days` days (default 90). If the associate mentions a
        specific date, pass a `days` value large enough to cover it -- e.g.
        if today is 25 Aug and the associate says "14 July", that's ~42
        days ago, so the default (90) already covers it, but don't assume;
        compute the gap and widen `days` if needed rather than getting an
        empty result and guessing. Optionally filter to descriptions
        containing `contains` (case-insensitive substring of the merchant/
        description text -- NOT the amount; amounts are separate fields, so
        filter by merchant name, not by a rupee figure). Only works for
        instruments belonging to the currently authenticated customer."""
        if not _data.customer_owns_instrument(customer_id, account_id):
            raise AccountNotOwned(account_id)
        cutoff = datetime.now().date() - timedelta(days=days)
        results = []
        for t in _data.TRANSACTIONS:
            if t["instrument_id"] != account_id:
                continue
            if datetime.strptime(t["date"], "%Y-%m-%d").date() < cutoff:
                continue
            if contains and contains.lower() not in t["description"].lower():
                continue
            results.append(Txn(**{k: v for k, v in t.items() if k in Txn.model_fields}).model_dump())
        results.sort(key=lambda r: r["date"], reverse=True)
        return results

    return list_recent_transactions


def make_check_dispute_status_tool(customer_id: str):
    @tool
    def check_dispute_status(case_id: str) -> dict:
        """Look up the status of a customer's own dispute/chargeback case by
        case_id. Returns stage, category, disputed amount, and (if resolved)
        the resolution. Only works for cases belonging to the currently
        authenticated customer."""
        dispute = _data.DISPUTES.get(case_id)
        if not dispute or dispute.get("customer_id") != customer_id:
            raise AccountNotOwned(case_id)
        fields = {k: v for k, v in dispute.items() if k in DisputeCase.model_fields}
        return DisputeCase(**fields).model_dump(exclude_none=True)

    return check_dispute_status
