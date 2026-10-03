"""Core-owned free cash flow from a version-pinned linked operating path.

The narrow linked-statement model treats ``interest_expense`` as cash interest
inside operating cash flow. FCFE therefore starts with that cash flow and adds
net borrowing before dividends. FCFF requires a separate, evidenced estimate
of *unlevered cash taxes*; the levered tax expense or taxes paid in the linked
statements cannot be silently reused for that purpose.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date
from decimal import Decimal

from versioned_finance_core.contracts import KnowledgeState
from versioned_finance_core.financial_core.identities import _exact_sum
from versioned_finance_core.financial_core.linked_statements import (
    BalanceSheet,
)
from versioned_finance_core.financial_core.model_path import (
    ModelInputEvidence,
    ModelPathResult,
    OperatingBaselineRef,
    operating_baseline_ref,
)

FREE_CASH_FLOW_SCHEMA_VERSION = 1


def _output_id(prefix: str, payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()}"


def _working_capital(balance: BalanceSheet) -> Decimal:
    return _exact_sum(
        (balance.receivables, balance.inventory, balance.payables.copy_negate())
    )


@dataclass(frozen=True, slots=True)
class UnleveredCashTaxInput:
    """Case-governed unlevered tax cash amount for one model period."""

    period_id: str
    amount: Decimal
    tax_method_id: str
    evidence: ModelInputEvidence

    def __post_init__(self) -> None:
        if not isinstance(self.period_id, str) or not self.period_id.strip():
            raise ValueError("period_id is required")
        if not isinstance(self.amount, Decimal) or not self.amount.is_finite():
            raise ValueError("unlevered cash taxes must be a finite Decimal")
        if self.amount < 0:
            raise ValueError("unlevered cash taxes must be nonnegative")
        if not isinstance(self.tax_method_id, str) or not self.tax_method_id.strip():
            raise ValueError("tax_method_id is required")
        if not isinstance(self.evidence, ModelInputEvidence):
            raise TypeError("evidence must be ModelInputEvidence")


@dataclass(frozen=True, slots=True)
class FreeCashFlowPeriod:
    period_id: str
    period_start: date
    period_end: date
    operating_cash_flow: Decimal
    capital_expenditure: Decimal
    net_debt_financing: Decimal
    dividends: Decimal
    change_in_operating_working_capital: Decimal
    ebit: Decimal
    depreciation: Decimal
    unlevered_cash_taxes: Decimal | KnowledgeState
    fcfe: Decimal
    fcff: Decimal | KnowledgeState
    fcfe_output_id: str
    fcff_output_id: str | None


@dataclass(frozen=True, slots=True)
class FreeCashFlowPathResult:
    baseline: OperatingBaselineRef
    periods: tuple[FreeCashFlowPeriod, ...]
    output_id: str


def project_free_cash_flow_path(
    path: ModelPathResult,
    *,
    unlevered_cash_taxes: tuple[UnleveredCashTaxInput, ...] = (),
) -> FreeCashFlowPathResult:
    """Project FCFE and conditionally FCFF without a tax or financing plug.

    Every cash flow ID is pinned to the reconciled Core baseline. A missing
    unlevered tax schedule produces ``UNKNOWN`` FCFF for that period, never a
    zero tax assumption. Cash flow arithmetic does not confer valuation or
    publication eligibility on the source model.
    """

    baseline = operating_baseline_ref(path)
    if path.opening.residual != 0:
        raise ValueError("opening balance sheet does not reconcile")
    if not isinstance(unlevered_cash_taxes, tuple) or any(
        not isinstance(item, UnleveredCashTaxInput) for item in unlevered_cash_taxes
    ):
        raise TypeError("unlevered_cash_taxes must be a tuple of UnleveredCashTaxInput")
    tax_by_period: dict[str, UnleveredCashTaxInput] = {}
    valid_periods = {period.period_id for period in path.periods}
    for tax in unlevered_cash_taxes:
        if tax.period_id not in valid_periods:
            raise ValueError(f"unlevered tax period is absent from Core path: {tax.period_id}")
        if tax.period_id in tax_by_period:
            raise ValueError(f"duplicate unlevered tax period: {tax.period_id}")
        if tax.evidence.available_at > path.information_cutoff:
            raise ValueError(f"unlevered tax evidence unavailable at cutoff: {tax.period_id}")
        tax_by_period[tax.period_id] = tax

    opening = path.opening
    projected: list[FreeCashFlowPeriod] = []
    for period in path.periods:
        inputs = period.inputs
        statement = period.result
        change_nwc = _exact_sum(
            (_working_capital(statement.closing), _working_capital(opening).copy_negate())
        )
        net_debt = _exact_sum((inputs.debt_draw, inputs.principal_repayment.copy_negate()))
        fcfe = _exact_sum((
            statement.cash_flow.operating, inputs.capex.copy_negate(), net_debt
        ))
        if fcfe != _exact_sum((
            statement.closing.cash, opening.cash.copy_negate(), inputs.dividends
        )):
            raise ValueError(f"FCFE does not reconcile to cash and dividends: {period.period_id}")

        common = {
            "schema_version": FREE_CASH_FLOW_SCHEMA_VERSION,
            "baseline_output_id": baseline.output_id,
            "period_id": period.period_id,
            "period_start": period.period_start.isoformat(),
            "period_end": period.period_end.isoformat(),
            "currency": baseline.currency,
            "unit": baseline.unit,
        }
        fcfe_id = _output_id("core_fcfe", {
            **common,
            "formula": "CFO - capex + debt_draw - principal_repayment",
            "operating_cash_flow": str(statement.cash_flow.operating),
            "capex": str(inputs.capex),
            "net_debt_financing": str(net_debt),
            "fcfe": str(fcfe),
        })
        tax = tax_by_period.get(period.period_id)
        if tax is None:
            unlevered_tax: Decimal | KnowledgeState = KnowledgeState.UNKNOWN
            fcff: Decimal | KnowledgeState = KnowledgeState.UNKNOWN
            fcff_id = None
        else:
            unlevered_tax = tax.amount
            fcff = _exact_sum((
                statement.income.ebit,
                inputs.depreciation,
                change_nwc.copy_negate(),
                inputs.capex.copy_negate(),
                tax.amount.copy_negate(),
            ))
            fcff_id = _output_id("core_fcff", {
                **common,
                "formula": "EBIT + depreciation - delta_operating_nwc - capex - unlevered_cash_taxes",
                "ebit": str(statement.income.ebit),
                "depreciation": str(inputs.depreciation),
                "change_in_operating_working_capital": str(change_nwc),
                "capex": str(inputs.capex),
                "unlevered_cash_taxes": str(tax.amount),
                "tax_method_id": tax.tax_method_id,
                "tax_evidence_id": tax.evidence.source_or_assumption_id,
                "tax_evidence_available_at": tax.evidence.available_at.astimezone(UTC).isoformat(),
                "fcff": str(fcff),
            })
        projected.append(FreeCashFlowPeriod(
            period_id=period.period_id,
            period_start=period.period_start,
            period_end=period.period_end,
            operating_cash_flow=statement.cash_flow.operating,
            capital_expenditure=inputs.capex,
            net_debt_financing=net_debt,
            dividends=inputs.dividends,
            change_in_operating_working_capital=change_nwc,
            ebit=statement.income.ebit,
            depreciation=inputs.depreciation,
            unlevered_cash_taxes=unlevered_tax,
            fcfe=fcfe,
            fcff=fcff,
            fcfe_output_id=fcfe_id,
            fcff_output_id=fcff_id,
        ))
        opening = statement.closing

    frozen = tuple(projected)
    return FreeCashFlowPathResult(
        baseline=baseline,
        periods=frozen,
        output_id=_output_id("core_free_cash_flow_path", {
            "schema_version": FREE_CASH_FLOW_SCHEMA_VERSION,
            "baseline_output_id": baseline.output_id,
            "period_cash_flow_ids": [
                (period.fcfe_output_id, period.fcff_output_id) for period in frozen
            ],
        }),
    )
