"""A small, exact three-statement operating model for a single currency.

The caller supplies versioned, sourced inputs. This model deliberately covers
only sales, cash operating costs, working capital, tax payable, PPE, debt and
dividends. Unmodelled accounts and FX require an explicit extension, rather
than an unexplained balancing item.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import Decimal

from versioned_finance_core.financial_core.identities import (
    _exact_product,
    _exact_sum,
    cash_rollforward_residual,
    debt_face_rollforward_residual,
    projected_closing_cash,
)


def _validate_decimals(record: object) -> None:
    for field in fields(record):
        value = getattr(record, field.name)
        if not isinstance(value, Decimal) or not value.is_finite():
            raise ValueError(f"{field.name} must be a finite Decimal")


@dataclass(frozen=True, slots=True)
class BalanceSheet:
    cash: Decimal
    receivables: Decimal
    inventory: Decimal
    ppe_net: Decimal
    payables: Decimal
    tax_payable: Decimal
    debt_face: Decimal
    equity: Decimal

    def __post_init__(self) -> None:
        _validate_decimals(self)

    @property
    def assets(self) -> Decimal:
        return _exact_sum((self.cash, self.receivables, self.inventory, self.ppe_net))

    @property
    def liabilities_and_equity(self) -> Decimal:
        return _exact_sum((self.payables, self.tax_payable, self.debt_face, self.equity))

    @property
    def residual(self) -> Decimal:
        return _exact_sum((self.assets, self.liabilities_and_equity.copy_negate()))


@dataclass(frozen=True, slots=True)
class OperatingPeriodInputs:
    """Period flows and period-end operating balances, each with explicit value.

    ``interest_expense`` is an input rather than an implied average-debt rate;
    financing terms and cash interest classification must be established by the
    case. ``tax_expense`` and ``cash_taxes_paid`` stay separate. All cost, tax,
    capex, financing and dividend inputs are nonnegative magnitudes.
    """

    volume: Decimal
    selling_price: Decimal
    variable_cost_per_unit: Decimal
    cash_opex: Decimal
    depreciation: Decimal
    interest_expense: Decimal
    tax_expense: Decimal
    cash_taxes_paid: Decimal
    closing_receivables: Decimal
    closing_inventory: Decimal
    closing_payables: Decimal
    capex: Decimal
    debt_draw: Decimal
    principal_repayment: Decimal
    dividends: Decimal

    def __post_init__(self) -> None:
        _validate_decimals(self)
        for field in fields(self):
            if getattr(self, field.name) < 0:
                raise ValueError(f"{field.name} must be nonnegative")


@dataclass(frozen=True, slots=True)
class IncomeStatement:
    revenue: Decimal
    cost_of_goods_sold: Decimal
    cash_opex: Decimal
    ebitda: Decimal
    depreciation: Decimal
    ebit: Decimal
    interest_expense: Decimal
    tax_expense: Decimal
    net_income: Decimal


@dataclass(frozen=True, slots=True)
class CashFlowStatement:
    operating: Decimal
    investing: Decimal
    financing: Decimal
    closing_cash: Decimal


@dataclass(frozen=True, slots=True)
class LinkedStatementResult:
    income: IncomeStatement
    cash_flow: CashFlowStatement
    closing: BalanceSheet
    balance_residual: Decimal
    cash_residual: Decimal
    debt_residual: Decimal


def project_linked_statements(
    opening: BalanceSheet, inputs: OperatingPeriodInputs
) -> LinkedStatementResult:
    """Link one operating period without a plug or intermediate rounding.

    Inputs are a deliberately narrow accounting scope: no FX, acquisitions,
    disposals, OCI, noncash financing, other assets or other liabilities. If a
    case has any material excluded line, the caller must extend/reconcile the
    model before using its output for an analytical conclusion.
    """

    if opening.residual != 0:
        raise ValueError("opening balance sheet does not reconcile")
    for name in (
        "cash", "receivables", "inventory", "ppe_net", "payables",
        "tax_payable", "debt_face",
    ):
        if getattr(opening, name) < 0:
            raise ValueError(f"opening {name} must be nonnegative")
    if inputs.depreciation > _exact_sum((opening.ppe_net, inputs.capex)):
        raise ValueError("depreciation exceeds available PPE")
    if inputs.principal_repayment > _exact_sum((opening.debt_face, inputs.debt_draw)):
        raise ValueError("principal repayment exceeds debt face available")

    tax_payable = _exact_sum((
        opening.tax_payable, inputs.tax_expense, inputs.cash_taxes_paid.copy_negate()
    ))
    if tax_payable < 0:
        raise ValueError("cash taxes exceed tax payable available in this model")

    revenue = _exact_product(inputs.volume, inputs.selling_price)
    cost_of_goods_sold = _exact_product(inputs.volume, inputs.variable_cost_per_unit)
    ebitda = _exact_sum((
        revenue, cost_of_goods_sold.copy_negate(), inputs.cash_opex.copy_negate()
    ))
    ebit = _exact_sum((ebitda, inputs.depreciation.copy_negate()))
    net_income = _exact_sum((
        ebit, inputs.interest_expense.copy_negate(), inputs.tax_expense.copy_negate()
    ))
    income = IncomeStatement(
        revenue=revenue,
        cost_of_goods_sold=cost_of_goods_sold,
        cash_opex=inputs.cash_opex,
        ebitda=ebitda,
        depreciation=inputs.depreciation,
        ebit=ebit,
        interest_expense=inputs.interest_expense,
        tax_expense=inputs.tax_expense,
        net_income=net_income,
    )

    operating = _exact_sum((
        net_income,
        inputs.depreciation,
        opening.receivables,
        inputs.closing_receivables.copy_negate(),
        opening.inventory,
        inputs.closing_inventory.copy_negate(),
        inputs.closing_payables,
        opening.payables.copy_negate(),
        tax_payable,
        opening.tax_payable.copy_negate(),
    ))
    investing = inputs.capex.copy_negate()
    financing = _exact_sum((
        inputs.debt_draw,
        inputs.principal_repayment.copy_negate(),
        inputs.dividends.copy_negate(),
    ))
    closing_cash = projected_closing_cash(
        opening.cash, operating, investing, financing, Decimal(0)
    )
    cash_flow = CashFlowStatement(operating, investing, financing, closing_cash)
    closing = BalanceSheet(
        cash=closing_cash,
        receivables=inputs.closing_receivables,
        inventory=inputs.closing_inventory,
        ppe_net=_exact_sum((
            opening.ppe_net, inputs.capex, inputs.depreciation.copy_negate()
        )),
        payables=inputs.closing_payables,
        tax_payable=tax_payable,
        debt_face=_exact_sum((
            opening.debt_face, inputs.debt_draw, inputs.principal_repayment.copy_negate()
        )),
        equity=_exact_sum((opening.equity, net_income, inputs.dividends.copy_negate())),
    )
    return LinkedStatementResult(
        income=income,
        cash_flow=cash_flow,
        closing=closing,
        balance_residual=closing.residual,
        cash_residual=cash_rollforward_residual(
            opening.cash, operating, investing, financing, Decimal(0), closing.cash
        ),
        debt_residual=debt_face_rollforward_residual(
            opening.debt_face, inputs.debt_draw, Decimal(0),
            inputs.principal_repayment, closing.debt_face,
        ),
    )
