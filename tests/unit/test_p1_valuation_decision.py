from dataclasses import fields, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from versioned_finance_core.contracts import AccountingScope
from versioned_finance_core.contracts.enums import GateStatus
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
from versioned_finance_core.modules.m1.valuation import (
    DCF_REVIEW_CHECKS,
    CashFlowClaim,
    DcfInputs,
    DiscountRateClaim,
    ForecastCashFlow,
    RateBasis,
    ValuationEligibilityReview,
    assess_dcf_eligibility,
    dcf_inputs_from_core_cash_flows,
    value_perpetuity_dcf,
)
from versioned_finance_core.modules.m1.valuation_decision import (
    METHOD_REVIEW_CHECKS,
    CoherentScenarioValue,
    MethodChoice,
    MethodDisposition,
    SupportedParameterPoint,
    ValuationMethod,
    assess_method_selection,
    bracket_thesis_break,
    eligible_decision_value,
    evaluate_dcf_parameter_sensitivity,
    select_valuation_methods,
)


def _dcf_inputs() -> DcfInputs:
    return DcfInputs(
        cash_flow_claim=CashFlowClaim.FCFF,
        discount_rate_claim=DiscountRateClaim.WACC,
        cash_flow_basis=RateBasis.NOMINAL,
        discount_rate_basis=RateBasis.NOMINAL,
        cash_flow_currency="USD",
        discount_rate_currency="USD",
        forecast_version_id="synthetic_core_forecast_v1",
        annual_cash_flows=(ForecastCashFlow(1, Decimal(100), "core_fcff_1"),),
        annual_discount_rate=Decimal("0.10"),
        discount_rate_assumption_id="synthetic_wacc",
        terminal_next_cash_flow=Decimal(105),
        terminal_growth_rate=Decimal("0.02"),
        terminal_state_assumption_id="synthetic_terminal",
    )


def _review(checks: frozenset[str], *, reviewer: str = "independent_reviewer") -> ValuationEligibilityReview:
    return ValuationEligibilityReview(
        review_id=f"review_{reviewer}",
        reviewer_id=reviewer,
        reviewed_at=datetime(2026, 5, 23, tzinfo=UTC),
        checks={name: True for name in checks},
    )


def _choices() -> tuple[MethodChoice, ...]:
    return (
        MethodChoice(
            ValuationMethod.DCF,
            MethodDisposition.SELECTED,
            "Coherent free-cash-flow forecast is available in this synthetic test.",
            ("synthetic_forecast",),
        ),
        MethodChoice(
            ValuationMethod.TRADING_COMPS,
            MethodDisposition.EXCLUDED,
            "No economically comparable peer in this synthetic test.",
            ("synthetic_peer_review",),
        ),
    )


def test_method_choice_is_deterministic_and_requires_review() -> None:
    cutoff = datetime(2026, 5, 21, tzinfo=UTC)
    selection = select_valuation_methods(case_id="synthetic", information_cutoff=cutoff, choices=_choices())
    assert selection.output_id == select_valuation_methods(
        case_id="synthetic", information_cutoff=cutoff, choices=tuple(reversed(_choices()))
    ).output_id
    assert selection.eligibility_status is GateStatus.NOT_EVALUATED
    assert selection.selected_methods == (ValuationMethod.DCF,)
    assert assess_method_selection(selection, _review(METHOD_REVIEW_CHECKS)).status is GateStatus.PASS
    assert assess_method_selection(selection, _review(frozenset())).status is GateStatus.WITHHELD

    no_method = select_valuation_methods(
        case_id="synthetic",
        information_cutoff=cutoff,
        choices=tuple(replace(choice, disposition=MethodDisposition.EXCLUDED) for choice in _choices()),
    )
    assert assess_method_selection(no_method, _review(METHOD_REVIEW_CHECKS)).failed_checks == (
        "no_selected_valuation_method",
    )


def test_decision_amount_fails_closed_if_either_gate_or_method_mismatches() -> None:
    selection = select_valuation_methods(
        case_id="synthetic_case", information_cutoff=datetime(2026, 5, 21, tzinfo=UTC), choices=_choices()
    )
    method_pass = assess_method_selection(selection, _review(METHOD_REVIEW_CHECKS))
    dcf = value_perpetuity_dcf(_core_dcf_inputs(with_fcff=True))
    dcf_withheld = assess_dcf_eligibility(dcf, _review(frozenset()))
    with pytest.raises(ValueError, match="DCF is not eligible"):
        eligible_decision_value(dcf, dcf_withheld, selection, method_pass)
    with pytest.raises(ValueError, match="method is not eligible"):
        eligible_decision_value(
            dcf, assess_dcf_eligibility(dcf, _review(DCF_REVIEW_CHECKS)),
            selection, assess_method_selection(selection, _review(frozenset()))
        )
    assert eligible_decision_value(
        dcf, assess_dcf_eligibility(dcf, _review(DCF_REVIEW_CHECKS)),
        selection, method_pass,
    ) == dcf.total_value
    other_case = select_valuation_methods(
        case_id="other_case", information_cutoff=datetime(2026, 5, 21, tzinfo=UTC),
        choices=_choices(),
    )
    with pytest.raises(ValueError, match="case differs"):
        eligible_decision_value(
            dcf, assess_dcf_eligibility(dcf, _review(DCF_REVIEW_CHECKS)),
            other_case, assess_method_selection(other_case, _review(METHOD_REVIEW_CHECKS)),
        )


def _point(value: str, ident: str, *, available: datetime | None = None) -> SupportedParameterPoint:
    return SupportedParameterPoint(
        Decimal(value), ident, (f"source_{ident}",),
        available or datetime(2026, 5, 20, tzinfo=UTC), "synthetic evidence bound",
    )


def test_dcf_sensitivity_is_sourced_cutoff_safe_and_keeps_forecast_fixed() -> None:
    inputs = _dcf_inputs()
    cutoff = datetime(2026, 5, 21, tzinfo=UTC)
    result = evaluate_dcf_parameter_sensitivity(
        inputs,
        information_cutoff=cutoff,
        discount_rates=(_point("0.10", "synthetic_wacc"), _point("0.12", "stress_wacc")),
        terminal_growth_rates=(_point("0.02", "synthetic_terminal"), _point("0.01", "stress_growth")),
    )
    assert result.base_dcf_output_id == value_perpetuity_dcf(inputs).output_id
    assert len(result.cells) == 4
    assert result.eligibility_status is GateStatus.NOT_EVALUATED
    assert next(cell.value for cell in result.cells if cell.discount_rate == Decimal("0.12") and cell.terminal_growth_rate == Decimal("0.01")) < value_perpetuity_dcf(inputs).total_value

    with pytest.raises(ValueError, match="unavailable at cutoff"):
        evaluate_dcf_parameter_sensitivity(
            inputs, information_cutoff=cutoff,
            discount_rates=(_point("0.10", "synthetic_wacc", available=cutoff + timedelta(seconds=1)),),
            terminal_growth_rates=(_point("0.02", "synthetic_terminal"),),
        )
    with pytest.raises(ValueError, match="base rate"):
        evaluate_dcf_parameter_sensitivity(
            inputs, information_cutoff=cutoff,
            discount_rates=(_point("0.12", "stress_wacc"),),
            terminal_growth_rates=(_point("0.02", "synthetic_terminal"),),
        )


def test_thesis_break_is_bracket_only_and_requires_a_crossing() -> None:
    lower = CoherentScenarioValue(
        "core_baseline", "core_scenario_1", "same_store_sales", Decimal("0.01"),
        "dcf_1", Decimal(90), "EQUITY_VALUE",
    )
    upper = CoherentScenarioValue(
        "core_baseline", "core_scenario_2", "same_store_sales", Decimal("0.03"),
        "dcf_2", Decimal(110), "EQUITY_VALUE",
    )
    result = bracket_thesis_break(
        upper, lower, decision_value=Decimal(100), decision_value_source_id="market_price_source"
    )
    assert result.lower_driver_value == Decimal("0.01")
    assert result.upper_driver_value == Decimal("0.03")
    assert result.eligibility_status is GateStatus.NOT_EVALUATED
    assert result.output_id == bracket_thesis_break(
        lower, upper, decision_value=Decimal(100), decision_value_source_id="market_price_source"
    ).output_id
    with pytest.raises(ValueError, match="do not bracket"):
        bracket_thesis_break(
            lower, upper, decision_value=Decimal(120), decision_value_source_id="market_price_source"
        )


def _core_path():
    available = datetime(2026, 1, 15, tzinfo=UTC)
    inputs = OperatingPeriodInputs(
        volume=Decimal(10), selling_price=Decimal(20), variable_cost_per_unit=Decimal(8),
        cash_opex=Decimal(40), depreciation=Decimal(10), interest_expense=Decimal(5),
        tax_expense=Decimal(13), cash_taxes_paid=Decimal(10),
        closing_receivables=Decimal(25), closing_inventory=Decimal(35),
        closing_payables=Decimal(30), capex=Decimal(20), debt_draw=Decimal(15),
        principal_repayment=Decimal(5), dividends=Decimal(10),
    )
    evidence = {
        field.name: ModelInputEvidence(f"assumption_{field.name}", available)
        for field in fields(inputs)
    }
    spec = ModelPathSpec(
        case_id="synthetic_case", version_id="synthetic_forecast_v1",
        accounting_scope=AccountingScope.CONSOLIDATED,
        economic_scope_id="synthetic_group", legal_entity_id=None,
        currency="USD", unit="USD_million",
        opening_balance_date=date(2025, 12, 31),
        opening=BalanceSheet(
            Decimal(100), Decimal(20), Decimal(30), Decimal(150),
            Decimal(25), Decimal(5), Decimal(100), Decimal(170),
        ),
        opening_balance_evidence=ModelInputEvidence("opening_source", available),
        information_cutoff=datetime(2026, 2, 1, tzinfo=UTC),
        periods=(ModelPeriod("fy2026", date(2026, 1, 1), date(2026, 12, 31), inputs, evidence),),
    )
    return project_model_path(spec)


def _core_dcf_inputs(*, with_fcff: bool) -> DcfInputs:
    path = _core_path()
    taxes = (
        UnleveredCashTaxInput(
            "fy2026", Decimal(16), "synthetic_tax_method",
            ModelInputEvidence("synthetic_tax_assumption", datetime(2026, 1, 15, tzinfo=UTC)),
        ),
    ) if with_fcff else ()
    cash_flows = project_free_cash_flow_path(path, unlevered_cash_taxes=taxes)
    return dcf_inputs_from_core_cash_flows(
        cash_flows,
        case_id="synthetic_case",
        forecast_version_id="synthetic_forecast_v1",
        accounting_scope=AccountingScope.CONSOLIDATED,
        economic_scope_id="synthetic_group",
        legal_entity_id=None,
        currency="USD",
        unit="USD_million",
        cash_flow_claim=CashFlowClaim.FCFF,
        discount_rate_claim=DiscountRateClaim.WACC,
        rate_basis=RateBasis.NOMINAL,
        annual_discount_rate=Decimal("0.10"),
        discount_rate_assumption_id="synthetic_wacc",
        discount_rate_available_at=datetime(2026, 1, 15, tzinfo=UTC),
        terminal_next_cash_flow=Decimal(40),
        terminal_growth_rate=Decimal("0.02"),
        terminal_state_assumption_id="synthetic_terminal",
        terminal_state_available_at=datetime(2026, 1, 15, tzinfo=UTC),
    )


def test_dcf_consumes_pinned_core_fcff_without_m1_derivation() -> None:
    inputs = _core_dcf_inputs(with_fcff=True)
    assert inputs.annual_cash_flows[0].amount == Decimal(39)
    assert inputs.annual_cash_flows[0].output_id.startswith("core_fcff_")
    result = value_perpetuity_dcf(inputs)
    assert result.operating_baseline_output_id == inputs.operating_baseline_output_id
    assert ("core_cash_flow_path", inputs.core_cash_flow_path_output_id) in result.input_lineage
    assert ("cash_flow_period_1", inputs.annual_cash_flows[0].output_id) in result.input_lineage
    with pytest.raises(ValueError, match="unresolved"):
        _core_dcf_inputs(with_fcff=False)


def test_fcfe_adapter_uses_core_output_and_cutoff_rejects_late_assumption() -> None:
    path = project_free_cash_flow_path(_core_path())
    kwargs = {
        "case_id": "synthetic_case",
        "forecast_version_id": "synthetic_forecast_v1",
        "accounting_scope": AccountingScope.CONSOLIDATED,
        "economic_scope_id": "synthetic_group",
        "legal_entity_id": None,
        "currency": "USD",
        "unit": "USD_million",
        "cash_flow_claim": CashFlowClaim.FCFE,
        "discount_rate_claim": DiscountRateClaim.COST_OF_EQUITY,
        "rate_basis": RateBasis.NOMINAL,
        "annual_discount_rate": Decimal("0.10"),
        "discount_rate_assumption_id": "synthetic_cost_of_equity",
        "discount_rate_available_at": datetime(2026, 1, 15, tzinfo=UTC),
        "terminal_next_cash_flow": Decimal(50),
        "terminal_growth_rate": Decimal("0.02"),
        "terminal_state_assumption_id": "synthetic_terminal",
        "terminal_state_available_at": datetime(2026, 1, 15, tzinfo=UTC),
    }
    inputs = dcf_inputs_from_core_cash_flows(path, **kwargs)
    assert inputs.annual_cash_flows[0].amount == Decimal(50)
    assert value_perpetuity_dcf(inputs).value_claim == "EQUITY_VALUE"
    with pytest.raises(ValueError, match="after the Core information cutoff"):
        dcf_inputs_from_core_cash_flows(
            path, **{**kwargs, "discount_rate_available_at": datetime(2026, 2, 2, tzinfo=UTC)}
        )
    with pytest.raises(ValueError, match="currency differs"):
        dcf_inputs_from_core_cash_flows(path, **{**kwargs, "currency": "KRW"})
    with pytest.raises(ValueError, match="forecast_version_id differs"):
        dcf_inputs_from_core_cash_flows(path, **{**kwargs, "forecast_version_id": "wrong"})
    with pytest.raises(ValueError, match="economic_scope_id differs"):
        dcf_inputs_from_core_cash_flows(path, **{**kwargs, "economic_scope_id": "wrong"})
    with pytest.raises(ValueError, match="nominal discount-rate basis"):
        dcf_inputs_from_core_cash_flows(path, **{**kwargs, "rate_basis": RateBasis.REAL})
