from decimal import Decimal

import pytest

from versioned_finance_core.financial_core import (
    audit_reported_project_cash,
    discount_relative_cash,
    implied_project_irr,
)


def test_reported_project_cash_audit_preserves_display_precision_and_known_answer() -> None:
    cash = (Decimal("-100.0"), Decimal("110.0"))
    annual_rate = Decimal("0.10")
    published_npv = discount_relative_cash(cash, annual_rate, "0.5")

    result = audit_reported_project_cash(
        cash,
        annual_rate=annual_rate,
        published_total=Decimal("10.0"),
        published_npv=published_npv,
    )

    assert result.displayed_total == Decimal("10.0")
    assert result.mid_period_npv == published_npv
    assert result.mid_period_difference_from_published == Decimal(0)
    assert result.display_quantums == (Decimal("0.1"),)
    assert result.maximum_mid_period_rounding_effect > Decimal(0)
    assert result.implied_irr.quantize(Decimal("0.001")) == Decimal("0.100")


def test_reported_project_cash_audit_rejects_missing_or_nonreconciling_cash() -> None:
    with pytest.raises(ValueError, match="at least one known"):
        audit_reported_project_cash(
            (),
            annual_rate=Decimal("0.10"),
            published_total=Decimal(0),
            published_npv=Decimal(0),
        )

    with pytest.raises(ValueError, match="does not sum"):
        audit_reported_project_cash(
            (Decimal("-100.0"), Decimal("110.0")),
            annual_rate=Decimal("0.10"),
            published_total=Decimal("31.0"),
            published_npv=Decimal(0),
        )


def test_reported_project_cash_audit_rejects_nonfinite_rates_and_nonconventional_irr() -> None:
    with pytest.raises(ValueError, match="finite"):
        audit_reported_project_cash(
            (Decimal("NaN"),),
            annual_rate=Decimal("0.10"),
            published_total=Decimal(0),
            published_npv=Decimal(0),
        )

    with pytest.raises(ValueError, match="exceed -100%"):
        discount_relative_cash((Decimal("-100.0"), Decimal("110.0")), Decimal(-1), "0.5")

    with pytest.raises(ValueError, match="conventional negative-to-positive"):
        implied_project_irr((Decimal("-100.0"), Decimal("300.0"), Decimal("-250.0")))
