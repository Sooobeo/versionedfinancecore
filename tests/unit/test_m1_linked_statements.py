from dataclasses import replace
from decimal import Decimal

import pytest

from versioned_finance_core.financial_core.linked_statements import (
    BalanceSheet,
    OperatingPeriodInputs,
    project_linked_statements,
)


def d(value: str | int) -> Decimal:
    return Decimal(value)


def opening_sheet() -> BalanceSheet:
    return BalanceSheet(d(100), d(20), d(30), d(150), d(25), d(5), d(100), d(170))


def period_inputs() -> OperatingPeriodInputs:
    return OperatingPeriodInputs(
        volume=d(10),
        selling_price=d(20),
        variable_cost_per_unit=d(8),
        cash_opex=d(40),
        depreciation=d(10),
        interest_expense=d(5),
        tax_expense=d(13),
        cash_taxes_paid=d(10),
        closing_receivables=d(25),
        closing_inventory=d(35),
        closing_payables=d(30),
        capex=d(20),
        debt_draw=d(15),
        principal_repayment=d(5),
        dividends=d(10),
    )


def test_known_answer_links_income_working_capital_tax_debt_and_cash() -> None:
    result = project_linked_statements(opening_sheet(), period_inputs())

    assert result.income.revenue == d(200)
    assert result.income.cost_of_goods_sold == d(80)
    assert result.income.ebitda == d(80)
    assert result.income.net_income == d(52)
    assert result.cash_flow.operating == d(60)
    assert result.cash_flow.investing == d(-20)
    assert result.cash_flow.financing == d(0)
    assert result.closing.cash == d(140)
    assert result.closing.tax_payable == d(8)
    assert result.closing.ppe_net == d(160)
    assert result.closing.debt_face == d(110)
    assert result.closing.equity == d(212)
    assert result.balance_residual == result.cash_residual == result.debt_residual == d(0)
    assert result.closing.assets == result.closing.liabilities_and_equity == d(360)


def test_perturbing_sales_moves_net_income_cash_and_equity_without_a_plug() -> None:
    base = project_linked_statements(opening_sheet(), period_inputs())
    revised = project_linked_statements(
        opening_sheet(), replace(period_inputs(), selling_price=d(21))
    )

    assert revised.income.revenue - base.income.revenue == d(10)
    assert revised.income.net_income - base.income.net_income == d(10)
    assert revised.closing.cash - base.closing.cash == d(10)
    assert revised.closing.equity - base.closing.equity == d(10)
    assert revised.balance_residual == d(0)


def test_rejects_nonreconciling_opening_sheet_and_unfunded_repayment() -> None:
    with pytest.raises(ValueError, match="opening balance sheet"):
        project_linked_statements(replace(opening_sheet(), equity=d(171)), period_inputs())
    with pytest.raises(ValueError, match="repayment exceeds"):
        project_linked_statements(
            opening_sheet(), replace(period_inputs(), principal_repayment=d(116))
        )


def test_rejects_tax_prepayment_not_represented_by_balance_sheet() -> None:
    with pytest.raises(ValueError, match="cash taxes exceed"):
        project_linked_statements(
            opening_sheet(), replace(period_inputs(), cash_taxes_paid=d(19))
        )


@pytest.mark.parametrize("field", ["volume", "selling_price", "cash_opex", "capex"])
def test_rejects_float_negative_and_missing_drivers(field: str) -> None:
    with pytest.raises(ValueError, match=f"{field} must be a finite Decimal"):
        replace(period_inputs(), **{field: 1.1})
    with pytest.raises(ValueError, match=f"{field} must be nonnegative"):
        replace(period_inputs(), **{field: d(-1)})
    with pytest.raises(ValueError, match=f"{field} must be a finite Decimal"):
        replace(period_inputs(), **{field: None})


def test_negative_cash_is_visible_as_a_deficit_and_not_clamped_to_zero() -> None:
    result = project_linked_statements(
        opening_sheet(), replace(period_inputs(), capex=d(200))
    )
    assert result.closing.cash == d(-40)
    assert result.balance_residual == d(0)


def test_linked_cash_and_equity_preserve_minor_unit_on_large_opening_balance() -> None:
    large = d("10000000000000000000000000000000000000000")
    opening = BalanceSheet(large, d(0), d(0), d(0), d(0), d(0), d(0), large)
    zero = d(0)
    inputs = OperatingPeriodInputs(
        volume=d(1), selling_price=d("0.01"), variable_cost_per_unit=zero,
        cash_opex=zero, depreciation=zero, interest_expense=zero,
        tax_expense=zero, cash_taxes_paid=zero, closing_receivables=zero,
        closing_inventory=zero, closing_payables=zero, capex=zero,
        debt_draw=zero, principal_repayment=zero, dividends=zero,
    )
    result = project_linked_statements(opening, inputs)
    expected = d("10000000000000000000000000000000000000000.01")
    assert result.closing.cash == result.closing.equity == expected
    assert result.balance_residual == result.cash_residual == 0
