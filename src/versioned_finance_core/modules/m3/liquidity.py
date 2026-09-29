from collections.abc import Iterable
from decimal import Decimal

from versioned_finance_core.financial_core.identities import Number, _decimal


def ending_accessible_cash(
    opening_accessible_cash: Number,
    eligible_inflows: Iterable[Number],
    eligible_outflows: Iterable[Number],
) -> Decimal:
    """Roll accessible cash using explicitly eligible sources and uses."""

    inflows = sum((_decimal(value) for value in eligible_inflows), Decimal(0))
    outflows = sum((_decimal(value) for value in eligible_outflows), Decimal(0))
    return _decimal(opening_accessible_cash) + inflows - outflows


def refinancing_gap(gross_requirement: Number, eligible_sources: Iterable[Number]) -> Decimal:
    """Non-negative amount of an uncovered refinancing requirement."""

    sources = sum((_decimal(value) for value in eligible_sources), Decimal(0))
    return max(Decimal(0), _decimal(gross_requirement) - sources)

