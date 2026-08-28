"""Shared, read-only access to the synthetic data files. Loaded once at
import time -- these are the mock account API and mock dispute store the
tools in this package query against."""
import json
from pathlib import Path

from .exceptions import AccountServiceUnavailable

ROOT = Path(__file__).resolve().parents[2]  # .../Capstone_Project_Arindam Sarkar
DATA_DIR = ROOT / "data"


def _load(name):
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


_CUSTOMERS_FILE = _load("customers.json")
CUSTOMERS = {c["customer_id"]: c for c in _CUSTOMERS_FILE["customers"]}
ACCOUNTS = {a["account_id"]: a for a in _CUSTOMERS_FILE["accounts"]}
CARDS = {c["card_id"]: c for c in _CUSTOMERS_FILE["cards"]}

TRANSACTIONS = _load("transactions.json")["transactions"]

DISPUTES = {d["case_id"]: d for d in _load("disputes.json")["disputes"]}


def get_customer(customer_id):
    return CUSTOMERS.get(customer_id)


def get_account(account_id):
    return ACCOUNTS.get(account_id)


def get_account_or_card(instrument_id):
    """Accounts and cards are stored separately (see customers.json), but
    the associate refers to both as "an account" colloquially -- callers
    that need to look up whatever a customer_instrument_directory id
    resolves to (account OR card) should use this rather than get_account
    alone, which only ever finds accounts."""
    if instrument_id in ACCOUNTS:
        return ACCOUNTS[instrument_id], "account"
    if instrument_id in CARDS:
        return CARDS[instrument_id], "card"
    return None, None


def customer_owns_instrument(customer_id, instrument_id):
    """True if instrument_id (an account_id or card_id) belongs to customer_id."""
    cust = get_customer(customer_id)
    if not cust:
        return False
    return instrument_id in cust.get("accounts", []) or instrument_id in cust.get("cards", [])


def customer_instrument_directory(customer_id):
    """A safe, non-sensitive summary of which account_id/card_id values exist
    for this customer -- id, type, and product name only, no balances or
    transaction data. This is what an associate's screen would already show
    before looking anything up; giving the agent the same visibility is what
    lets it reference the correct account_id/card_id in a tool call instead
    of either guessing one or refusing to call any tool at all.

    Called directly from classify_intent/agent_node/clarify_node, not just
    from inside a tool call -- so unlike a normal tool, an unexpected failure
    here can't rely on tools_node's try/except to catch it. Any lookup error
    is deliberately converted to AccountServiceUnavailable rather than left
    to propagate as a raw, unhandled exception that would crash the whole
    turn (capstone_build_plan.md §8, "Account API down")."""
    try:
        cust = get_customer(customer_id)
        if not cust:
            return []
        directory = []
        for account_id in cust.get("accounts", []):
            acc = ACCOUNTS.get(account_id, {})
            directory.append({"id": account_id, "kind": "account", "type": acc.get("type"), "product_name": acc.get("product_name")})
        for card_id in cust.get("cards", []):
            card = CARDS.get(card_id, {})
            directory.append({"id": card_id, "kind": "card", "type": card.get("type"), "product_name": card.get("product_name")})
        for case_id, dispute in DISPUTES.items():
            if dispute.get("customer_id") == customer_id:
                directory.append({"id": case_id, "kind": "dispute_case", "type": dispute.get("category"), "product_name": None})
        return directory
    except AccountServiceUnavailable:
        raise
    except Exception as e:  # noqa: BLE001 -- fail closed on literally anything unexpected
        raise AccountServiceUnavailable(f"customer_instrument_directory: {type(e).__name__}: {e}") from e
