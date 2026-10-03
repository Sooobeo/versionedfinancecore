"""Known-answer and fail-closed checks for the consolidated Core model."""

from dataclasses import fields, replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from versioned_finance_core.contracts import (
    AccountingScope,
    KnowledgeState,
    ScenarioPurpose,
    VersionType,
)
from versioned_finance_core.financial_core.cash_components import CashView
from versioned_finance_core.financial_core.consolidated_forecast import (
    ConsolidatedBalanceSheet,
    ConsolidatedDriverInputs,
    ConsolidatedForecastPeriod,
    ConsolidatedForecastSpec,
    ConsolidatedPeriodInputs,
    aggregate_disclosed_opening_balance,
    audit_consolidated_cash_components,
    comparable_remaining_period_base,
    derive_consolidated_inputs,
    derive_consolidated_period,
    project_consolidated_free_cash_flow_path,
    project_consolidated_path,
    project_consolidated_statements,
    projected_fiscal_revenue_basis,
    reported_other_revenue,
    unlevered_cash_taxes_from_ebit,
)
from versioned_finance_core.financial_core.free_cash_flow import UnleveredCashTaxInput
from versioned_finance_core.financial_core.model_path import ModelInputEvidence

CUTOFF = datetime(2026, 5, 21, 23, 59, tzinfo=UTC)
AVAILABLE = datetime(2026, 5, 20, 12, tzinfo=UTC)


def d(value: str | int) -> Decimal:
    return Decimal(value)


def opening() -> ConsolidatedBalanceSheet:
    # Entirely synthetic. Both sides equal 350 before any forecast.
    return ConsolidatedBalanceSheet(
        cash=d(100), receivables=d(20), inventory=d(30),
        other_operating_assets=d(10), ppe_net=d(150),
        other_long_lived_assets=d(40), payables=d(25),
        accrued_operating_liabilities=d(15), tax_payable=d(5),
        debt_carrying=d(100), dividends_payable=d(5),
        other_liabilities=d(30), equity=d(170),
    )


def test_disclosed_opening_grouping_checks_exhaustiveness_and_reported_totals() -> None:
    amounts = {field.name: getattr(opening(), field.name) for field in fields(opening())}
    amounts.pop("other_long_lived_assets")
    amounts.update({"long_lived_a": d(15), "long_lived_b": d(25)})
    amounts["reported_assets"] = d(350)
    amounts["reported_liabilities_equity"] = d(350)
    grouping = {field.name: (field.name,) for field in fields(opening())}
    grouping["other_long_lived_assets"] = ("long_lived_a", "long_lived_b")
    ids = {
        name: ModelInputEvidence(f"synthetic_fact:{name}", AVAILABLE)
        for name in amounts
    }
    kwargs = {
        "asset_total_metric_id": "reported_assets",
        "liabilities_equity_total_metric_id": "reported_liabilities_equity",
        "information_cutoff": CUTOFF,
    }
    grouped = aggregate_disclosed_opening_balance(amounts, grouping, ids, **kwargs)
    assert grouped.opening == opening()
    assert grouped.opening_evidence["other_long_lived_assets"].source_or_assumption_id.startswith(
        "grouped_opening_"
    )
    assert grouped.output_id.startswith("core_grouped_opening_")
    with pytest.raises(ValueError, match="assigned exactly once"):
        aggregate_disclosed_opening_balance(
            {**amounts, "unassigned_line": d(1)}, grouping,
            {**ids, "unassigned_line": ModelInputEvidence("synthetic_extra", AVAILABLE)},
            **kwargs,
        )
    with pytest.raises(ValueError, match="reported total assets"):
        aggregate_disclosed_opening_balance(
            {**amounts, "reported_assets": d(351)}, grouping, ids, **kwargs
        )
    with pytest.raises(ValueError, match="unavailable at cutoff"):
        aggregate_disclosed_opening_balance(
            amounts, grouping,
            {**ids, "long_lived_b": ModelInputEvidence(
                "post_cutoff", datetime(2026, 5, 22, tzinfo=UTC)
            )},
            **kwargs,
        )


def inputs() -> ConsolidatedPeriodInputs:
    return ConsolidatedPeriodInputs(
        net_sales=d(200), other_revenue=d(10),
        cash_operating_expense=d(120), depreciation=d(10),
        interest_expense=d(5), cash_other_income=d(2),
        tax_expense=d(15), cash_taxes_paid=d(12),
        closing_receivables=d(25), closing_inventory=d(35),
        closing_other_operating_assets=d(12), closing_payables=d(30),
        closing_accrued_operating_liabilities=d(14), capex=d(20),
        ppe_noncash_change=d(3),
        other_long_lived_assets_investing_cash_change=d(5),
        other_long_lived_assets_noncash_change=d(4),
        debt_issuance=d(15), debt_repayment=d(5),
        debt_carrying_noncash_change=d(0),
        other_liabilities_operating_cash_change=d(2),
        other_liabilities_financing_cash_change=d(-3),
        other_liabilities_noncash_change=d(1),
        dividends_declared=d(10), dividends_paid=d(12),
        share_issuance=d(4), share_repurchases=d(6),
        other_comprehensive_income=d(6),
    )


def evidence(record: object) -> dict[str, ModelInputEvidence]:
    return {
        field.name: ModelInputEvidence(f"source_or_assumption:{field.name}", AVAILABLE)
        for field in fields(record)
    }


def spec() -> ConsolidatedForecastSpec:
    projected = inputs()
    return ConsolidatedForecastSpec(
        case_id="synthetic_case", version_id="forecast_v1",
        version_type=VersionType.ANALYST_FORECAST,
        scenario_id="analyst_base", scenario_purpose=ScenarioPurpose.ANALYST_BASE,
        accounting_scope=AccountingScope.CONSOLIDATED,
        economic_scope_id="synthetic_group", legal_entity_id=None,
        currency="USD", unit="USDm",
        opening_balance_date=date(2026, 4, 30), opening=opening(),
        opening_evidence=evidence(opening()), information_cutoff=CUTOFF,
        periods=(ConsolidatedForecastPeriod(
            period_id="FY27_STUB", period_start=date(2026, 5, 1),
            period_end=date(2027, 1, 31), inputs=projected,
            input_evidence=evidence(projected),
        ),),
    )


def drivers() -> ConsolidatedDriverInputs:
    zero = d(0)
    return ConsolidatedDriverInputs(
        comparable_prior_net_sales=d(200), comparable_prior_other_revenue=zero,
        net_sales_growth_rate=zero, other_revenue_growth_rate=zero,
        fiscal_year_net_sales_to_date=zero,
        fiscal_year_other_revenue_to_date=zero,
        fiscal_year_capex_to_date=zero,
        operating_margin_of_total_revenue=d("0.30"),
        depreciation_rate_of_total_revenue=d("0.05"),
        capex_rate_of_fiscal_net_sales=d("0.10"),
        receivables_rate_of_fiscal_net_sales=d("0.10"),
        inventory_rate_of_fiscal_net_sales=d("0.15"),
        other_operating_assets_rate_of_fiscal_net_sales=d("0.05"),
        payables_rate_of_fiscal_net_sales=d("0.125"),
        accrued_operating_liabilities_rate_of_fiscal_net_sales=d("0.075"),
        interest_expense=d(5), cash_other_income=zero,
        tax_rate_on_pretax_income=d("0.20"),
        cash_tax_rate_on_pretax_income=d("0.20"),
        ppe_noncash_change=zero,
        other_long_lived_assets_investing_cash_change=zero,
        other_long_lived_assets_noncash_change=zero,
        debt_issuance=zero, debt_repayment=zero,
        debt_carrying_noncash_change=zero,
        other_liabilities_operating_cash_change=zero,
        other_liabilities_financing_cash_change=zero,
        other_liabilities_noncash_change=zero,
        dividends_declared=zero, dividends_paid=zero,
        share_issuance=zero, share_repurchases=zero,
        other_comprehensive_income=zero,
    )


def test_driver_constructor_keeps_fiscal_stub_and_formula_lineage_in_core() -> None:
    assert reported_other_revenue(d(210), d(200)) == d(10)
    assert comparable_remaining_period_base(d(1000), d(250)) == d(750)
    direct = derive_consolidated_inputs(drivers())
    assert direct.net_sales == d(200)
    assert direct.cash_operating_expense == d(130)
    assert direct.depreciation == d(10)
    assert direct.capex == d(20)
    assert direct.closing_inventory == d(30)
    assert direct.tax_expense == direct.cash_taxes_paid == d(11)
    period = derive_consolidated_period(
        period_id="FY27_STUB", period_start=date(2026, 5, 1),
        period_end=date(2027, 1, 31), drivers=drivers(),
        driver_evidence=evidence(drivers()),
    )
    path = project_consolidated_path(replace(spec(), periods=(period,)))
    assert path.periods[0].result.balance_residual == d(0)
    assert path.periods[0].result.closing.cash == d(134)
    assert period.input_evidence["cash_operating_expense"].source_or_assumption_id.startswith(
        "driver_lineage_"
    )
    with pytest.raises(ValueError, match="do not reproduce"):
        replace(period, inputs=replace(period.inputs, net_sales=d(201)))
    with pytest.raises(ValueError, match="exceed reported total revenue"):
        reported_other_revenue(d(199), d(200))


def test_stub_capex_uses_full_fiscal_sales_and_subtracts_explicit_ytd_spend() -> None:
    stub = replace(
        drivers(), comparable_prior_net_sales=d(150),
        fiscal_year_net_sales_to_date=d(50), fiscal_year_capex_to_date=d(4),
    )
    direct = derive_consolidated_inputs(stub)
    assert direct.net_sales == d(150)
    assert direct.closing_inventory == d(30)
    assert direct.capex == d(16)
    with pytest.raises(ValueError, match="below actual capex"):
        derive_consolidated_inputs(replace(stub, fiscal_year_capex_to_date=d(21)))


def test_full_year_growth_base_is_chained_to_prior_stub_and_actual_ytd() -> None:
    first_drivers = replace(
        drivers(), comparable_prior_net_sales=d(150),
        comparable_prior_other_revenue=d(5),
        fiscal_year_net_sales_to_date=d(50),
        fiscal_year_other_revenue_to_date=d(2),
        fiscal_year_capex_to_date=d(4),
    )
    first = derive_consolidated_period(
        period_id="FY27_STUB", period_start=date(2026, 5, 1),
        period_end=date(2027, 1, 31), drivers=first_drivers,
        driver_evidence=evidence(first_drivers),
    )
    assert projected_fiscal_revenue_basis(first) == (d(200), d(7))
    second_drivers = replace(
        drivers(), comparable_prior_net_sales=d(200),
        comparable_prior_other_revenue=d(7),
    )
    second = derive_consolidated_period(
        period_id="FY28", period_start=date(2027, 2, 1),
        period_end=date(2028, 1, 31), drivers=second_drivers,
        driver_evidence=evidence(second_drivers),
    )
    assert project_consolidated_path(replace(spec(), periods=(first, second))).periods[-1].result.balance_residual == 0
    wrong = replace(second_drivers, comparable_prior_other_revenue=d(6))
    with pytest.raises(ValueError, match="prior other revenue"):
        project_consolidated_path(replace(
            spec(), periods=(first, derive_consolidated_period(
                period_id="FY28", period_start=date(2027, 2, 1),
                period_end=date(2028, 1, 31), drivers=wrong,
                driver_evidence=evidence(wrong),
            )),
        ))
    doubled = replace(second_drivers, fiscal_year_net_sales_to_date=d(50))
    with pytest.raises(ValueError, match="full fiscal year cannot include prior YTD"):
        project_consolidated_path(replace(
            spec(), periods=(first, derive_consolidated_period(
                period_id="FY28", period_start=date(2027, 2, 1),
                period_end=date(2028, 1, 31), drivers=doubled,
                driver_evidence=evidence(doubled),
            )),
        ))


def test_known_answer_full_statements_cash_debt_tax_dividends_and_fcff() -> None:
    path = project_consolidated_path(spec())
    result = path.periods[0].result
    assert result.income.total_revenue == d(210)
    assert result.income.operating_income == d(80)
    assert result.income.net_income == d(62)
    assert result.cash_flow.operating == d(69)
    assert result.cash_flow.investing == d(-25)
    assert result.cash_flow.financing == d(-7)
    assert result.closing.cash == d(137)
    assert result.closing.ppe_net == d(163)
    assert result.closing.debt_carrying == d(110)
    assert result.closing.tax_payable == d(8)
    assert result.closing.dividends_payable == d(3)
    assert result.closing.equity == d(226)
    assert result.closing.assets == result.closing.liabilities_and_equity == d(421)
    assert all((
        result.balance_residual == 0, result.cash_residual == 0,
        result.debt_residual == 0, result.tax_residual == 0,
        result.ppe_residual == 0, result.dividend_payable_residual == 0,
    ))

    without_tax = project_consolidated_free_cash_flow_path(path)
    assert without_tax.periods[0].fcff is KnowledgeState.UNKNOWN
    assert without_tax.periods[0].fcff_output_id is None
    taxed = project_consolidated_free_cash_flow_path(
        path, unlevered_cash_taxes=(UnleveredCashTaxInput(
            "FY27_STUB", d(18), "synthetic_tax_method",
            ModelInputEvidence("synthetic_tax_assumption", AVAILABLE),
        ),),
    )
    assert taxed.periods[0].change_in_operating_working_capital == d(6)
    assert taxed.periods[0].fcff == d(46)
    assert taxed.periods[0].fcfe == d(51)
    assert taxed.periods[0].fcff_output_id.startswith("core_fcff_")
    assert taxed.baseline.model_path_sha256 == path.content_sha256
    audit = audit_consolidated_cash_components(path, taxed)[0]
    assert audit.total_for(CashView.FCFF) == d(46)
    assert audit.total_for(CashView.FCFE) == d(51)
    assert audit.total_for(CashView.CFADS) is KnowledgeState.NOT_APPLICABLE
    capex_component = next(
        component for component in audit.components
        if component.component_id == "capital_expenditure"
    )
    assert capex_component.included_in_fcff and capex_component.included_in_fcfe
    assert audit.output_id.startswith("core_cash_inclusion_")
    with pytest.raises(ValueError, match="differ from Core statements"):
        audit_consolidated_cash_components(
            path, replace(taxed, periods=(replace(
                taxed.periods[0], operating_cash_flow=d(70)
            ),)),
        )

    proxy = unlevered_cash_taxes_from_ebit(
        path, tax_rate=d("0.25"),
        evidence=ModelInputEvidence("synthetic_analyst_cash_tax_proxy", AVAILABLE),
        method_id="synthetic_ebit_times_cash_tax_rate",
    )
    assert proxy[0].amount == d(20)
    assert project_consolidated_free_cash_flow_path(
        path, unlevered_cash_taxes=proxy
    ).periods[0].fcff == d(44)


def test_output_id_is_reproducible_and_sensitive_to_a_sourced_driver() -> None:
    original = project_consolidated_path(spec())
    assert project_consolidated_path(spec()).content_sha256 == original.content_sha256
    changed_period = replace(
        spec().periods[0],
        inputs=replace(inputs(), net_sales=d(201)),
    )
    changed = project_consolidated_path(replace(spec(), periods=(changed_period,)))
    assert changed.content_sha256 != original.content_sha256
    assert changed.periods[0].result.income.net_income == d(63)
    assert changed.periods[0].result.closing.cash == d(138)
    assert changed.periods[0].result.balance_residual == 0


def test_unmatched_noncash_change_cannot_be_hidden_in_cash() -> None:
    result = project_consolidated_statements(
        opening(), replace(inputs(), other_comprehensive_income=d(0))
    )
    assert result.cash_residual == 0
    assert result.balance_residual == d(6)
    with pytest.raises(ValueError, match="financial identities"):
        project_consolidated_path(replace(
            spec(), periods=(replace(
                spec().periods[0],
                inputs=replace(inputs(), other_comprehensive_income=d(0)),
            ),),
        ))


def test_missing_or_late_driver_and_opening_evidence_are_rejected() -> None:
    with pytest.raises(ValueError, match="input_evidence must match every field"):
        replace(spec().periods[0], input_evidence={"net_sales": evidence(inputs())["net_sales"]})
    changed = evidence(opening())
    changed["cash"] = ModelInputEvidence("post_cutoff", datetime(2026, 5, 22, tzinfo=UTC))
    with pytest.raises(ValueError, match="opening evidence unavailable"):
        project_consolidated_path(replace(spec(), opening_evidence=changed))
    changed_period = evidence(inputs())
    changed_period["net_sales"] = ModelInputEvidence(
        "post_cutoff", datetime(2026, 5, 22, tzinfo=UTC)
    )
    with pytest.raises(ValueError, match="input unavailable at cutoff"):
        project_consolidated_path(replace(
            spec(), periods=(replace(spec().periods[0], input_evidence=changed_period),)
        ))


@pytest.mark.parametrize("field_name", ["net_sales", "capex", "debt_issuance"])
def test_missing_float_and_negative_material_inputs_are_rejected(field_name: str) -> None:
    for bad, message in ((None, "a finite Decimal"), (1.2, "a finite Decimal"),
                         (d(-1), "nonnegative")):
        with pytest.raises(ValueError, match=f"{field_name} must be {message}"):
            replace(inputs(), **{field_name: bad})


def test_cash_tax_and_dividend_boundaries_and_late_unlevered_tax() -> None:
    with pytest.raises(ValueError, match="cash taxes exceed"):
        project_consolidated_statements(
            opening(), replace(inputs(), cash_taxes_paid=d(21))
        )
    with pytest.raises(ValueError, match="dividends paid exceed"):
        project_consolidated_statements(
            opening(), replace(inputs(), dividends_paid=d(16))
        )
    path = project_consolidated_path(spec())
    with pytest.raises(ValueError, match="unlevered tax evidence unavailable"):
        project_consolidated_free_cash_flow_path(
            path, unlevered_cash_taxes=(UnleveredCashTaxInput(
                "FY27_STUB", d(18), "synthetic_tax_method",
                ModelInputEvidence("post_cutoff", datetime(2026, 5, 22, tzinfo=UTC)),
            ),),
        )
    with pytest.raises(ValueError, match="tax-rate evidence unavailable"):
        unlevered_cash_taxes_from_ebit(
            path, tax_rate=d("0.24"),
            evidence=ModelInputEvidence(
                "post_cutoff", datetime(2026, 5, 22, tzinfo=UTC)
            ),
            method_id="synthetic_tax_proxy",
        )
    loss_period = replace(
        spec().periods[0], inputs=replace(inputs(), cash_operating_expense=d(250))
    )
    loss_path = project_consolidated_path(replace(spec(), periods=(loss_period,)))
    with pytest.raises(ValueError, match="negative EBIT"):
        unlevered_cash_taxes_from_ebit(
            loss_path, tax_rate=d("0.24"),
            evidence=ModelInputEvidence("synthetic_rate", AVAILABLE),
            method_id="synthetic_tax_proxy",
        )
