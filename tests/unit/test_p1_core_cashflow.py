from dataclasses import fields, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from versioned_finance_core.contracts import AccountingScope, KnowledgeState
from versioned_finance_core.financial_core import (
    BalanceSheet,
    ModelInputEvidence,
    ModelPathSpec,
    ModelPeriod,
    OperatingPeriodInputs,
    UnleveredCashTaxInput,
    project_free_cash_flow_path,
    project_model_path,
)

KST = timezone(timedelta(hours=9))
CUTOFF = datetime(2026, 2, 1, tzinfo=KST)
AVAILABLE = datetime(2026, 1, 15, tzinfo=KST)


def d(value: str | int) -> Decimal:
    return Decimal(value)


def spec() -> ModelPathSpec:
    inputs = OperatingPeriodInputs(
        volume=d(10), selling_price=d(20), variable_cost_per_unit=d(8),
        cash_opex=d(40), depreciation=d(10), interest_expense=d(5),
        tax_expense=d(13), cash_taxes_paid=d(10),
        closing_receivables=d(25), closing_inventory=d(35),
        closing_payables=d(30), capex=d(20), debt_draw=d(15),
        principal_repayment=d(5), dividends=d(10),
    )
    evidence = {
        field.name: ModelInputEvidence(f"assumption_{field.name}", AVAILABLE)
        for field in fields(inputs)
    }
    return ModelPathSpec(
        case_id="synthetic_case",
        version_id="forecast_v1",
        accounting_scope=AccountingScope.CONSOLIDATED,
        economic_scope_id="synthetic_group",
        legal_entity_id=None,
        currency="KRW",
        unit="KRW_million",
        opening_balance_date=date(2025, 12, 31),
        opening=BalanceSheet(d(100), d(20), d(30), d(150), d(25), d(5), d(100), d(170)),
        opening_balance_evidence=ModelInputEvidence("opening_source", AVAILABLE),
        information_cutoff=CUTOFF,
        periods=(ModelPeriod(
            "fy2026", date(2026, 1, 1), date(2026, 12, 31), inputs, evidence
        ),),
    )


def tax(*, amount: str = "16", available_at: datetime = AVAILABLE) -> UnleveredCashTaxInput:
    return UnleveredCashTaxInput(
        period_id="fy2026",
        amount=d(amount),
        tax_method_id="synthetic_unlevered_tax_schedule_v1",
        evidence=ModelInputEvidence("synthetic_unlevered_tax_assumption", available_at),
    )


def test_known_answer_fcfe_and_fcff_with_distinct_tax_bases() -> None:
    path = project_model_path(spec())
    result = project_free_cash_flow_path(path, unlevered_cash_taxes=(tax(),))
    period = result.periods[0]
    assert period.operating_cash_flow == d(60)
    assert period.capital_expenditure == d(20)
    assert period.net_debt_financing == d(10)
    assert period.change_in_operating_working_capital == d(5)
    assert period.fcfe == d(50)  # 60 - 20 + 15 - 5, before dividends
    assert period.fcff == d(39)  # 70 + 10 - 5 - 20 - 16
    assert period.fcfe == path.closing.cash - path.opening.cash + d(10)
    assert period.fcff != period.fcfe
    assert period.fcfe_output_id.startswith("core_fcfe_")
    assert period.fcff_output_id is not None and period.fcff_output_id.startswith("core_fcff_")
    assert result.baseline.model_path_sha256 == path.content_sha256
    assert result.baseline.accounting_scope is AccountingScope.CONSOLIDATED
    assert result.baseline.unit == "KRW_million"


def test_missing_unlevered_tax_is_unknown_not_zero_and_fcfe_remains_available() -> None:
    result = project_free_cash_flow_path(project_model_path(spec()))
    period = result.periods[0]
    assert period.fcfe == d(50)
    assert period.unlevered_cash_taxes is KnowledgeState.UNKNOWN
    assert period.fcff is KnowledgeState.UNKNOWN
    assert period.fcff_output_id is None
    explicit_zero = project_free_cash_flow_path(
        project_model_path(spec()), unlevered_cash_taxes=(tax(amount="0"),)
    )
    assert explicit_zero.periods[0].fcff == d(55)
    assert explicit_zero.periods[0].fcff_output_id is not None


def test_negative_fcfe_is_preserved_as_liquidity_signal() -> None:
    original = spec()
    first = original.periods[0]
    inputs = replace(first.inputs, capex=d(200))
    evidence = dict(first.input_evidence)
    stressed = replace(original, periods=(replace(first, inputs=inputs, input_evidence=evidence),))
    period = project_free_cash_flow_path(project_model_path(stressed)).periods[0]
    assert period.fcfe == d(-130)


def test_tax_method_and_source_change_ids_without_changing_core_baseline() -> None:
    path = project_model_path(spec())
    first = project_free_cash_flow_path(path, unlevered_cash_taxes=(tax(),))
    assert project_free_cash_flow_path(path, unlevered_cash_taxes=(tax(),)).output_id == first.output_id
    changed_tax = project_free_cash_flow_path(path, unlevered_cash_taxes=(tax(amount="17"),))
    changed_method = project_free_cash_flow_path(
        path, unlevered_cash_taxes=(replace(tax(), tax_method_id="new_method"),)
    )
    assert changed_tax.baseline.output_id == first.baseline.output_id
    assert changed_tax.periods[0].fcff_output_id != first.periods[0].fcff_output_id
    assert changed_method.output_id != first.output_id
    assert changed_tax.periods[0].fcfe_output_id == first.periods[0].fcfe_output_id


def test_tax_vintage_and_period_matching_fail_closed() -> None:
    path = project_model_path(spec())
    with pytest.raises(ValueError, match="unavailable at cutoff"):
        project_free_cash_flow_path(
            path, unlevered_cash_taxes=(
                tax(available_at=datetime(2026, 2, 2, tzinfo=KST)),
            )
        )
    with pytest.raises(ValueError, match="duplicate unlevered tax period"):
        project_free_cash_flow_path(path, unlevered_cash_taxes=(tax(), tax()))
    with pytest.raises(ValueError, match="absent from Core path"):
        project_free_cash_flow_path(
            path, unlevered_cash_taxes=(replace(tax(), period_id="fy2027"),)
        )
    with pytest.raises(ValueError, match="nonnegative"):
        tax(amount="-1")


def test_tampered_linked_statement_cannot_produce_fcf() -> None:
    path = project_model_path(spec())
    period = path.periods[0]
    altered_cash_flow = replace(period.result.cash_flow, operating=d(61))
    tampered = replace(
        path,
        periods=(replace(period, result=replace(period.result, cash_flow=altered_cash_flow)),),
    )
    with pytest.raises(ValueError, match="does not reproduce from retained Core inputs"):
        project_free_cash_flow_path(tampered)


def test_source_or_scope_change_changes_core_cashflow_ids() -> None:
    original = spec()
    first = project_free_cash_flow_path(project_model_path(original))
    changed_scope = project_free_cash_flow_path(
        project_model_path(replace(original, economic_scope_id="new_scope"))
    )
    changed_unit = project_free_cash_flow_path(
        project_model_path(replace(original, unit="KRW_thousand"))
    )
    assert changed_scope.periods[0].fcfe_output_id != first.periods[0].fcfe_output_id
    assert changed_unit.periods[0].fcfe_output_id != first.periods[0].fcfe_output_id
