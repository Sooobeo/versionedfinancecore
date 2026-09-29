from collections.abc import Iterable
from decimal import Decimal, localcontext

from versioned_finance_core.financial_core.identities import Number, _decimal


def _exact_sum(values: Iterable[Decimal]) -> Decimal:
    """Sum finite decimals without rounding away smaller currency units."""

    amounts = tuple(_decimal(value) for value in values)
    if not amounts:
        return Decimal(0)
    lowest_exponent = min(value.as_tuple().exponent for value in amounts)
    highest_digit = max(value.adjusted() for value in amounts)
    # A carry can add one digit; the count term covers a sum of many rows.
    precision = max(28, highest_digit - lowest_exponent + len(str(len(amounts))) + 2)
    with localcontext() as context:
        context.prec = precision
        return sum(amounts, Decimal(0))


def _exact_product(left: Decimal, right: Decimal) -> Decimal:
    """Multiply two exact decimals at sufficient coefficient precision."""

    left, right = _decimal(left), _decimal(right)
    precision = max(28, len(left.as_tuple().digits) + len(right.as_tuple().digits) + 1)
    with localcontext() as context:
        context.prec = precision
        return left * right


def incremental_cash_flow(option_world: Number, status_quo_world: Number) -> Decimal:
    """Option-world cash flow less status-quo cash flow on the same basis."""

    return _exact_sum((_decimal(option_world), _decimal(status_quo_world).copy_negate()))

