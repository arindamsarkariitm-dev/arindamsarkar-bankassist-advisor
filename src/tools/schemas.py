"""Pydantic v2 schemas for every tool's return value."""
from pydantic import BaseModel, Field


class AccountSummary(BaseModel):
    account_id: str
    type: str
    product_name: str
    status: str
    currency: str
    balance: float | None = Field(default=None, description="Set for savings/current/RD accounts")
    outstanding_principal: float | None = Field(default=None, description="Set for loan accounts")
    annual_rate_pct: float | None = None
    next_due_date: str | None = None
    maturity_date: str | None = None
    credit_limit: float | None = Field(default=None, description="Set for credit cards; a card has no stored balance field -- see list_recent_transactions for spend")


class Txn(BaseModel):
    transaction_id: str
    date: str
    direction: str
    amount: float
    currency: str
    category: str
    description: str


class PolicyChunk(BaseModel):
    doc_id: str
    version: str
    effective_date: str
    status: str
    text: str
    score: float


class DisputeCase(BaseModel):
    case_id: str
    status: str
    category: str
    filed_date: str
    resolved_date: str | None = None
    disputed_amount: float
    currency: str
    summary: str
    current_stage: str
    resolution: str | None = None


class EmiSchedule(BaseModel):
    principal: float
    annual_rate_pct: float
    months: int
    emi_amount: float
    total_payment: float
    total_interest: float


class TicketRef(BaseModel):
    ticket_id: str
    category: str
    created_at: str
    summary: str
