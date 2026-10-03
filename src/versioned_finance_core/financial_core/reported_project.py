"""Pure reconciliation of a rounded, relative-period reported project cash row.

This is deliberately narrower than an M2 option valuation.  It audits a
single disclosed project cash sequence and makes timing hypotheses explicit;
it never supplies a status-quo world, a company hurdle rate, or financing.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, localcontext

_CALCULATION_PRECISION = 34
_IRR_BISECTION_ITERATIONS = 160
_IRR_BRACKET_EXPANSIONS = 64


def _finite_decimal(value: Decimal, field: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field} must be a Decimal")
    if not value.is_finite():
        raise ValueError(f"{field} must be finite")
    return value


def _cash_tuple(cash: Iterable[Decimal]) -> tuple[Decimal, ...]:
    result = tuple(_finite_decimal(value, "cash value") for value in cash)
    if not result:
        raise ValueError("cash must contain at least one known displayed value")
    return result


def _require_conventional_project_sign_change(cash: tuple[Decimal, ...]) -> None:
    """Accept only nonzero negatives followed by nonzero positives for IRR solving."""

    saw_negative = False
    saw_positive = False
    for value in cash:
        if value < 0:
            if saw_positive:
                raise ValueError("IRR requires one conventional negative-to-positive sign change")
            saw_negative = True
        elif value > 0:
            saw_positive = True
    if not saw_negative or not saw_positive:
        raise ValueError("IRR requires one conventional negative-to-positive sign change")


@dataclass(frozen=True, slots=True)
class ReportedProjectCashAudit:
    """Exact displayed-row and timing-hypothesis checks for one project cash row."""

    displayed_total: Decimal
    start_period_npv: Decimal
    mid_period_npv: Decimal
    end_period_npv: Decimal
    mid_period_difference_from_published: Decimal
    maximum_mid_period_rounding_effect: Decimal
    implied_irr: Decimal
    display_quantums: tuple[Decimal, ...]


def display_quantum(value: Decimal) -> Decimal:
    """Return the public display quantum encoded in a Decimal input value."""

    value = _finite_decimal(value, "displayed value")
    return Decimal(1).scaleb(value.as_tuple().exponent)


def discount_relative_cash(
    cash: Iterable[Decimal], annual_rate: Decimal, first_period_exponent: str
) -> Decimal:
    """Discount relative cash under an explicit start-, middle-, or end-period hypothesis."""

    values = _cash_tuple(cash)
    annual_rate = _finite_decimal(annual_rate, "annual_rate")
    if annual_rate <= Decimal(-1):
        raise ValueError("annual_rate must exceed -100%")
    with localcontext() as context:
        context.prec = _CALCULATION_PRECISION
        factor = Decimal(1) + annual_rate
        if first_period_exponent == "0":
            offset = Decimal(1)
        elif first_period_exponent == "0.5":
            offset = factor.sqrt()
        elif first_period_exponent == "1":
            offset = factor
        else:
            raise ValueError("first_period_exponent must be 0, 0.5 or 1")
        return sum(
            (value / (factor**index * offset) for index, value in enumerate(values)),
            Decimal(0),
        )


def implied_project_irr(cash: Iterable[Decimal]) -> Decimal:
    """Find a sign-changing project IRR; this does not establish a hurdle rate."""

    values = _cash_tuple(cash)
    _require_conventional_project_sign_change(values)
    with localcontext() as context:
        context.prec = _CALCULATION_PRECISION
        lower, upper = Decimal(0), Decimal(1)
        if discount_relative_cash(values, lower, "0.5") <= 0:
            raise ValueError("expected positive NPV at a zero rate")
        for _ in range(_IRR_BRACKET_EXPANSIONS):
            if discount_relative_cash(values, upper, "0.5") < 0:
                break
            upper *= 2
        else:
            raise ValueError("could not bracket a positive project IRR")
        for _ in range(_IRR_BISECTION_ITERATIONS):
            middle = (lower + upper) / 2
            if discount_relative_cash(values, middle, "0.5") > 0:
                lower = middle
            else:
                upper = middle
        return (lower + upper) / 2


def _maximum_mid_period_rounding_effect(
    cash: tuple[Decimal, ...], annual_rate: Decimal
) -> Decimal:
    with localcontext() as context:
        context.prec = _CALCULATION_PRECISION
        factor = Decimal(1) + annual_rate
        middle_offset = factor.sqrt()
        return sum(
            (
                (display_quantum(value) / 2) / (factor**index * middle_offset)
                for index, value in enumerate(cash)
            ),
            Decimal(0),
        )


def audit_reported_project_cash(
    cash: Iterable[Decimal],
    *,
    annual_rate: Decimal,
    published_total: Decimal,
    published_npv: Decimal,
) -> ReportedProjectCashAudit:
    """Audit public displayed rows against supplied total and NPV reference facts.

    ``published_total`` and ``published_npv`` must already be sourced case
    inputs.  The method does not infer either one, nor does it turn the relative
    row into dated Core cash components.
    """

    values = _cash_tuple(cash)
    annual_rate = _finite_decimal(annual_rate, "annual_rate")
    published_total = _finite_decimal(published_total, "published_total")
    published_npv = _finite_decimal(published_npv, "published_npv")
    if annual_rate <= Decimal(-1):
        raise ValueError("annual_rate must exceed -100%")
    with localcontext() as context:
        context.prec = _CALCULATION_PRECISION
        displayed_total = sum(values, Decimal(0))
        if displayed_total != published_total:
            raise ValueError("displayed annual project cash does not sum to the published total")
        start_period_npv = discount_relative_cash(values, annual_rate, "0")
        mid_period_npv = discount_relative_cash(values, annual_rate, "0.5")
        end_period_npv = discount_relative_cash(values, annual_rate, "1")
        difference = mid_period_npv - published_npv
        rounding_effect = _maximum_mid_period_rounding_effect(values, annual_rate)
        if abs(difference) > rounding_effect:
            raise ValueError("mid-period NPV difference exceeds displayed-row rounding bound")
        return ReportedProjectCashAudit(
            displayed_total=displayed_total,
            start_period_npv=start_period_npv,
            mid_period_npv=mid_period_npv,
            end_period_npv=end_period_npv,
            mid_period_difference_from_published=difference,
            maximum_mid_period_rounding_effect=rounding_effect,
            implied_irr=implied_project_irr(values),
            display_quantums=tuple(sorted({display_quantum(value) for value in values})),
        )
