from collections.abc import Iterable
from decimal import Decimal, localcontext

Number = int | str | Decimal


def _decimal(value: Number) -> Decimal:
    if isinstance(value, float):
        raise TypeError("binary float is not a canonical financial input")
    result = value if isinstance(value, Decimal) else Decimal(str(value))
    if not result.is_finite():
        raise ValueError("non-finite decimal value")
    return result


def _exact_sum(values: Iterable[Number]) -> Decimal:
    """Sum finite decimal inputs without the caller's display precision rounding cash."""

    amounts = tuple(_decimal(value) for value in values)
    if not amounts:
        return Decimal(0)
    lowest_exponent = min(value.as_tuple().exponent for value in amounts)
    highest_digit = max(value.adjusted() for value in amounts)
    precision = max(28, highest_digit - lowest_exponent + len(str(len(amounts))) + 2)
    with localcontext() as context:
        context.prec = precision
        return sum(amounts, Decimal(0))


def _exact_product(left: Number, right: Number) -> Decimal:
    """Multiply finite decimal coefficients exactly, including large KRW amounts."""

    left, right = _decimal(left), _decimal(right)
    precision = max(28, len(left.as_tuple().digits) + len(right.as_tuple().digits) + 1)
    with localcontext() as context:
        context.prec = precision
        return left * right


def projected_closing_cash(
    opening_cash: Number,
    operating_cash_flow: Number,
    investing_cash_flow: Number,
    financing_cash_flow: Number,
    fx_and_other: Number,
) -> Decimal:
    """Single canonical definition for a cash roll-forward's calculated close."""

    return _exact_sum(
        value for value in (
            opening_cash, operating_cash_flow, investing_cash_flow,
            financing_cash_flow, fx_and_other,
        )
    )


def cash_rollforward_residual(
    opening_cash: Number,
    operating_cash_flow: Number,
    investing_cash_flow: Number,
    financing_cash_flow: Number,
    fx_and_other: Number,
    closing_cash: Number,
) -> Decimal:
    """Residual is zero when the reported cash identity reconciles."""

    return _exact_sum((
        projected_closing_cash(
            opening_cash, operating_cash_flow, investing_cash_flow,
            financing_cash_flow, fx_and_other,
        ),
        _decimal(closing_cash).copy_negate(),
    ))


def debt_face_rollforward_residual(
    opening_face: Number,
    draw_or_issue: Number,
    pik_fx_and_other: Number,
    principal_repayment: Number,
    closing_face: Number,
) -> Decimal:
    """Residual is zero when the debt face-value identity reconciles."""

    return _exact_sum((
        _decimal(opening_face),
        _decimal(draw_or_issue),
        _decimal(pik_fx_and_other),
        _decimal(principal_repayment).copy_negate(),
        _decimal(closing_face).copy_negate(),
    ))


def sources_uses_residual(sources: Iterable[Number], uses: Iterable[Number]) -> Decimal:
    """Residual is zero when sources equal uses."""

    return _exact_sum((
        *(_decimal(value) for value in sources),
        *(_decimal(value).copy_negate() for value in uses),
    ))

