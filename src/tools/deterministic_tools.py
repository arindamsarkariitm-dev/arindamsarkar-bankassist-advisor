"""Deterministic-lane tool: calculate_emi. Pure arithmetic, no data lookup --
exists specifically so the LLM delegates EMI math instead of doing it
mentally (a wrong-tool-selection trace where the model computes EMI itself
is the clean Phase 5 failure exhibit capstone_build_plan.md §2 asks for)."""
from langchain_core.tools import tool

from .exceptions import InvalidArguments
from .schemas import EmiSchedule


@tool
def calculate_emi(principal: float, annual_rate_pct: float, months: int) -> dict:
    """Calculate the EMI (equated monthly installment) for a loan given the
    principal amount, the annual interest rate as a percentage, and the
    tenure in months. Use this for any EMI math -- never compute it
    mentally, and never use it for a loan product that doesn't exist in the
    bank's catalog (check search_bank_policy first)."""
    if principal <= 0:
        raise InvalidArguments("principal must be positive")
    if months <= 0:
        raise InvalidArguments("months must be positive")
    if annual_rate_pct < 0:
        raise InvalidArguments("annual_rate_pct cannot be negative")

    monthly_rate = annual_rate_pct / 12 / 100
    if monthly_rate == 0:
        emi = principal / months
    else:
        factor = (1 + monthly_rate) ** months
        emi = principal * monthly_rate * factor / (factor - 1)

    total_payment = emi * months
    total_interest = total_payment - principal

    return EmiSchedule(
        principal=principal,
        annual_rate_pct=annual_rate_pct,
        months=months,
        emi_amount=round(emi, 2),
        total_payment=round(total_payment, 2),
        total_interest=round(total_interest, 2),
    ).model_dump()
