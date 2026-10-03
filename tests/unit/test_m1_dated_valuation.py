"""Synthetic known answers for dated M1 valuation over Core cash flows."""

from dataclasses import fields, replace
from datetime import UTC, date, datetime
from decimal import Decimal, localcontext

import pytest

from versioned_finance_core.contracts.enums import AccountingScope, GateStatus, KnowledgeState
from versioned_finance_core.financial_core.free_cash_flow import (
    UnleveredCashTaxInput,
    project_free_cash_flow_path,
)
from versioned_finance_core.financial_core.linked_statements import (
    BalanceSheet,
    OperatingPeriodInputs,
)
from versioned_finance_core.financial_core.model_path import (
    ModelInputEvidence,
    ModelPathSpec,
    ModelPeriod,
    project_model_path,
)
from versioned_finance_core.modules.m1.valuation import (
    DCF_REVIEW_CHECKS,
    EQUITY_BRIDGE_REVIEW_CHECKS,
    CashFlowClaim,
    DatedClaimBalance,
    DiscountRateClaim,
    DiscountTiming,
    LeasePolicyEvidence,
    LeaseValuationTreatment,
    RateBasis,
    TerminalOperatingEconomics,
    ValuationEligibilityReview,
    aggregate_dated_claim_balances,
    assess_dated_equity_bridge_eligibility,
    assess_dcf_eligibility,
    bridge_enterprise_to_equity_dated,
    bridge_enterprise_to_equity_partial,
    dcf_inputs_from_core_cash_flows,
    eligible_valuation_amount,
    terminal_operating_economics_from_forecast,
    value_perpetuity_dcf,
)

AVAILABLE = datetime(2026, 5, 20, tzinfo=UTC)
CUTOFF = datetime(2026, 5, 21, 23, 59, tzinfo=UTC)
VALUE_DATE = date(2026, 5, 21)


def _core_path():
    operating = OperatingPeriodInputs(
        volume=Decimal(10), selling_price=Decimal(20), variable_cost_per_unit=Decimal(8),
        cash_opex=Decimal(40), depreciation=Decimal(10), interest_expense=Decimal(5),
        tax_expense=Decimal(13), cash_taxes_paid=Decimal(10),
        closing_receivables=Decimal(25), closing_inventory=Decimal(35),
        closing_payables=Decimal(30), capex=Decimal(20), debt_draw=Decimal(15),
        principal_repayment=Decimal(5), dividends=Decimal(10),
    )
    evidence = {
        field.name: ModelInputEvidence(f"source_{field.name}", AVAILABLE)
        for field in fields(operating)
    }
    path = project_model_path(ModelPathSpec(
        case_id="synthetic_dated", version_id="forecast_v1",
        accounting_scope=AccountingScope.CONSOLIDATED,
        economic_scope_id="synthetic_group", legal_entity_id=None,
        currency="USD", unit="USD_million",
        opening_balance_date=date(2026, 4, 30),
        opening=BalanceSheet(
            Decimal(100), Decimal(20), Decimal(30), Decimal(150),
            Decimal(25), Decimal(5), Decimal(100), Decimal(170),
        ),
        opening_balance_evidence=ModelInputEvidence("opening_source", AVAILABLE),
        information_cutoff=CUTOFF,
        periods=(
            ModelPeriod("fy27_remainder", date(2026, 5, 1), date(2027, 1, 31),
                        operating, evidence),
            ModelPeriod("fy28", date(2027, 2, 1), date(2028, 1, 31),
                        operating, evidence),
        ),
    ))
    return project_free_cash_flow_path(path, unlevered_cash_taxes=(
        UnleveredCashTaxInput(
            "fy27_remainder", Decimal(16), "synthetic_tax_method",
            ModelInputEvidence("tax_source_27", AVAILABLE),
        ),
        UnleveredCashTaxInput(
            "fy28", Decimal(16), "synthetic_tax_method",
            ModelInputEvidence("tax_source_28", AVAILABLE),
        ),
    ))


def _inputs():
    core = _core_path()
    economics = TerminalOperatingEconomics(
        next_year_unlevered_nopat=Decimal(100), sustainable_roic=Decimal("0.10"),
        growth_rate=Decimal("0.02"), assumption_id="terminal_economics_v1",
        basis_source_ids=("terminal_operating_source",), available_at=AVAILABLE,
        rationale="Synthetic sustainable NOPAT with g/ROIC reinvestment",
    )
    return core, dcf_inputs_from_core_cash_flows(
        core,
        case_id="synthetic_dated", forecast_version_id="forecast_v1",
        accounting_scope=AccountingScope.CONSOLIDATED,
        economic_scope_id="synthetic_group", legal_entity_id=None,
        currency="USD", unit="USD_million",
        cash_flow_claim=CashFlowClaim.FCFF,
        discount_rate_claim=DiscountRateClaim.WACC,
        rate_basis=RateBasis.NOMINAL,
        annual_discount_rate=Decimal("0.10"),
        discount_rate_assumption_id="synthetic_wacc_v1",
        discount_rate_available_at=AVAILABLE,
        terminal_next_cash_flow=economics.next_year_fcff,
        terminal_growth_rate=Decimal("0.02"),
        terminal_state_assumption_id="terminal_economics_v1",
        terminal_state_available_at=AVAILABLE,
        discount_timing=DiscountTiming.ACT_365_FIXED,
        valuation_date=VALUE_DATE,
        discount_rate_basis_source_ids=("risk_free_source", "erp_source"),
        terminal_state_basis_source_ids=("terminal_operating_source",),
        discount_rate_rationale="Synthetic nominal USD WACC basis",
        terminal_cash_flow_rationale="Synthetic NOPAT less g/ROIC reinvestment",
        terminal_economics=economics,
    )


def _claim(amount: str, name: str, as_of: date) -> DatedClaimBalance:
    return DatedClaimBalance(
        Decimal(amount), f"source_{name}", as_of, AVAILABLE,
        AccountingScope.CONSOLIDATED, "synthetic_group", None,
        "USD", "USD_million",
    )


def _lease_policy(*, consistent: bool = True) -> LeasePolicyEvidence:
    return LeasePolicyEvidence(
        LeaseValuationTreatment.OPERATING_COST_INCLUDED,
        "synthetic_lease_policy", ("lease_source",), AVAILABLE,
        lease_cost_in_fcff=True,
        lease_liability_in_debt_like_claims=not consistent,
        lease_financing_in_wacc=False,
    )


def _bridge(as_of: date, *, consistent_lease: bool = True):
    _, inputs = _inputs()
    dcf = value_perpetuity_dcf(inputs)
    bridge = bridge_enterprise_to_equity_dated(
        dcf,
        excess_cash=_claim("50", "excess_cash", as_of),
        nonoperating_assets=_claim("20", "nonoperating_assets", as_of),
        debt_like_claims=_claim("100", "debt_like", as_of),
        minority_interest=_claim("10", "nci", as_of),
        other_senior_claims=_claim("0", "other", as_of),
        lease_policy=_lease_policy(consistent=consistent_lease),
    )
    return dcf, bridge


def _review(checks: frozenset[str]) -> ValuationEligibilityReview:
    return ValuationEligibilityReview(
        "synthetic_review", "synthetic_independent_reviewer", CUTOFF,
        {name: True for name in checks},
    )


def test_act_365_fixed_discounts_stub_without_annualizing_core_fcff() -> None:
    core, inputs = _inputs()
    dcf = value_perpetuity_dcf(inputs)
    assert inputs.annual_cash_flows[0].amount == core.periods[0].fcff
    assert inputs.annual_cash_flows[0].output_id == core.periods[0].fcff_output_id
    assert dcf.valuation_date == VALUE_DATE
    assert abs(dcf.period_year_fractions[0] - Decimal(255) / Decimal(365)) < Decimal("1E-27")
    assert abs(dcf.period_year_fractions[1] - Decimal(620) / Decimal(365)) < Decimal("1E-27")
    assert dcf.terminal_value_at_horizon == Decimal(1000)
    assert dcf.eligibility_status is GateStatus.NOT_EVALUATED
    assert dcf.output_id == value_perpetuity_dcf(inputs).output_id
    assert ("discount_rate_basis_source_1", "risk_free_source") in dcf.input_lineage
    with localcontext() as decimal_context:
        decimal_context.prec = 16
        assert value_perpetuity_dcf(inputs).output_id == dcf.output_id


def test_dated_dcf_requires_source_basis_and_terminal_economics_consistency() -> None:
    _, inputs = _inputs()
    with pytest.raises(ValueError, match="discount_rate_basis_source_ids"):
        value_perpetuity_dcf(replace(inputs, discount_rate_basis_source_ids=()))
    with pytest.raises(ValueError, match="terminal cash flow differs"):
        value_perpetuity_dcf(replace(inputs, terminal_next_cash_flow=Decimal(81)))
    with pytest.raises(ValueError, match="after valuation_date"):
        value_perpetuity_dcf(replace(
            inputs, discount_rate_available_at=datetime(2026, 5, 22, tzinfo=UTC),
            information_cutoff=datetime(2026, 5, 23, tzinfo=UTC),
        ))


def test_terminal_economics_helper_uses_final_annual_core_ebit_and_g_over_roic() -> None:
    core = _core_path()
    economics = terminal_operating_economics_from_forecast(
        core,
        sustainable_ebit_growth=Decimal("0.02"),
        terminal_growth_rate=Decimal("0.02"),
        unlevered_cash_tax_rate=Decimal("0.24"),
        sustainable_roic=Decimal("0.10"),
        assumption_id="synthetic_terminal",
        ebit_growth_assumption_id="synthetic_ebit_growth",
        cash_tax_rate_assumption_id="synthetic_tax_rate",
        roic_assumption_id="synthetic_roic",
        growth_assumption_id="synthetic_g",
        basis_source_ids=("synthetic_external_terminal_source",),
        available_at=AVAILABLE,
        rationale="Synthetic EBIT normalization and sustainable reinvestment",
    )
    assert economics.next_year_ebit == Decimal("71.40")
    assert economics.next_year_unlevered_nopat == Decimal("54.2640")
    assert economics.reinvestment_rate == Decimal("0.2")
    assert economics.next_year_fcff == Decimal("43.41120")
    assert economics.final_core_fcff == core.periods[-1].fcff
    assert economics.final_core_fcff_output_id == core.periods[-1].fcff_output_id
    assert economics.transition_difference == economics.next_year_fcff - core.periods[-1].fcff
    with localcontext() as decimal_context:
        decimal_context.prec = 50
        assert economics.transition_ratio == economics.next_year_fcff / core.periods[-1].fcff
    assert replace(economics, final_core_fcff=Decimal(0)).transition_ratio is KnowledgeState.NM
    assert core.periods[-1].fcff_output_id in economics.basis_source_ids
    with pytest.raises(ValueError, match="full annual"):
        terminal_operating_economics_from_forecast(
            replace(core, baseline=replace(core.baseline, periods=core.baseline.periods[:1]),
                    periods=core.periods[:1]),
            sustainable_ebit_growth=Decimal("0.02"),
            terminal_growth_rate=Decimal("0.02"),
            unlevered_cash_tax_rate=Decimal("0.24"),
            sustainable_roic=Decimal("0.10"),
            assumption_id="synthetic_terminal",
            ebit_growth_assumption_id="synthetic_ebit_growth",
            cash_tax_rate_assumption_id="synthetic_tax_rate",
            roic_assumption_id="synthetic_roic",
            growth_assumption_id="synthetic_g",
            basis_source_ids=("synthetic_external_terminal_source",),
            available_at=AVAILABLE,
            rationale="Synthetic stub only",
        )


def test_terminal_transition_must_match_pinned_final_core_cash_flow() -> None:
    core, inputs = _inputs()
    economics = terminal_operating_economics_from_forecast(
        core,
        sustainable_ebit_growth=Decimal("0.02"),
        terminal_growth_rate=Decimal("0.02"),
        unlevered_cash_tax_rate=Decimal("0.24"),
        sustainable_roic=Decimal("0.10"),
        assumption_id="terminal_economics_v1",
        ebit_growth_assumption_id="synthetic_ebit_growth",
        cash_tax_rate_assumption_id="synthetic_tax_rate",
        roic_assumption_id="synthetic_roic",
        growth_assumption_id="synthetic_g",
        basis_source_ids=("terminal_operating_source",),
        available_at=AVAILABLE,
        rationale="Synthetic terminal transition",
    )
    pinned = replace(
        inputs,
        terminal_economics=economics,
        terminal_next_cash_flow=economics.next_year_fcff,
        terminal_state_basis_source_ids=economics.basis_source_ids,
    )
    result = value_perpetuity_dcf(pinned)
    assert result.output_id
    with pytest.raises(ValueError, match="terminal transition differs"):
        value_perpetuity_dcf(replace(
            pinned,
            terminal_economics=replace(economics, final_core_fcff=Decimal(100)),
        ))
    with pytest.raises(ValueError, match="terminal transition differs"):
        value_perpetuity_dcf(replace(
            pinned,
            terminal_economics=replace(economics, final_core_fcff_output_id="wrong_core_id"),
        ))


def test_april_claim_snapshot_and_inconsistent_lease_policy_withhold_bridge() -> None:
    dcf, bridge = _bridge(date(2026, 4, 30), consistent_lease=False)
    assert bridge.eligibility_status is GateStatus.WITHHELD
    assert bridge.failed_structural_checks == (
        "claim_balance_as_of_date", "lease_valuation_treatment",
    )
    assert abs(bridge.equity_value - (dcf.total_value - Decimal(40))) < Decimal("1E-25")
    dcf_review = assess_dcf_eligibility(dcf, _review(
        DCF_REVIEW_CHECKS | frozenset({
            "dated_discount_timing_reviewed", "interim_cash_treatment_reviewed",
            "terminal_cash_flow_economics_reviewed",
        })
    ))
    bridge_review = assess_dated_equity_bridge_eligibility(
        bridge, dcf_review,
        _review(EQUITY_BRIDGE_REVIEW_CHECKS | frozenset({"lease_policy_and_claim_basis_reviewed"})),
    )
    assert bridge_review.status is GateStatus.WITHHELD
    with pytest.raises(ValueError, match="not eligible"):
        eligible_valuation_amount(bridge, bridge_review)


def test_unknown_claims_remain_unknown_in_partial_bridge() -> None:
    _, inputs = _inputs()
    dcf = value_perpetuity_dcf(inputs)
    partial = bridge_enterprise_to_equity_partial(
        dcf,
        excess_cash=KnowledgeState.UNKNOWN,
        nonoperating_assets=KnowledgeState.UNKNOWN,
        debt_like_claims=_claim("100", "debt", date(2026, 4, 30)),
        minority_interest=_claim("10", "nci", date(2026, 4, 30)),
        other_senior_claims=KnowledgeState.UNKNOWN,
        lease_policy=_lease_policy(),
    )
    assert abs(partial.known_subtotal - (dcf.total_value - Decimal(110))) < Decimal("1E-25")
    assert partial.equity_value is None
    assert partial.unknown_components == (
        "excess_cash", "nonoperating_assets", "other_senior_claims",
    )
    assert partial.failed_structural_checks == (
        "debt_like_claims_as_of_date", "minority_interest_as_of_date",
    )
    assert partial.eligibility_status is GateStatus.WITHHELD
    assert partial.output_id == bridge_enterprise_to_equity_partial(
        dcf,
        excess_cash=KnowledgeState.UNKNOWN,
        nonoperating_assets=KnowledgeState.UNKNOWN,
        debt_like_claims=_claim("100", "debt", date(2026, 4, 30)),
        minority_interest=_claim("10", "nci", date(2026, 4, 30)),
        other_senior_claims=KnowledgeState.UNKNOWN,
        lease_policy=_lease_policy(),
    ).output_id


def test_dated_claim_aggregation_preserves_component_lineage_and_scope() -> None:
    april = date(2026, 4, 30)
    nci = aggregate_dated_claim_balances(
        (_claim("6352000000", "nonredeemable_nci", april),
         _claim("293000000", "redeemable_nci", april)),
        aggregate_name="wmt_april_nci", information_cutoff=CUTOFF,
    )
    assert nci.amount == Decimal(6645000000)
    assert nci.component_source_ids == (
        "source_nonredeemable_nci", "source_redeemable_nci",
    )
    assert nci.source_id.startswith("m1_claim_aggregate_")
    assert nci.source_id == aggregate_dated_claim_balances(
        (_claim("293000000", "redeemable_nci", april),
         _claim("6352000000", "nonredeemable_nci", april)),
        aggregate_name="wmt_april_nci", information_cutoff=CUTOFF,
    ).source_id
    debt = aggregate_dated_claim_balances(
        tuple(_claim(amount, name, april) for amount, name in (
            ("10673000000", "short_borrowings"), ("3896000000", "current_debt"),
            ("36887000000", "long_debt"), ("851000000", "current_finance_lease"),
            ("5822000000", "long_finance_lease"),
        )),
        aggregate_name="wmt_april_debt_finance_lease", information_cutoff=CUTOFF,
    )
    assert debt.amount == Decimal(58129000000)
    _, inputs = _inputs()
    partial = bridge_enterprise_to_equity_partial(
        value_perpetuity_dcf(inputs),
        excess_cash=KnowledgeState.UNKNOWN,
        nonoperating_assets=KnowledgeState.UNKNOWN,
        debt_like_claims=debt,
        minority_interest=nci,
        other_senior_claims=KnowledgeState.UNKNOWN,
        lease_policy=_lease_policy(),
    )
    assert ("minority_interest_component_1", "source_nonredeemable_nci") in (
        partial.input_lineage
    )
    assert ("debt_like_claims_component_1", "source_current_debt") in (
        partial.input_lineage
    )
    with pytest.raises(ValueError, match="as_of_date differs"):
        aggregate_dated_claim_balances(
            (_claim("1", "older", april), _claim("2", "later", VALUE_DATE)),
            aggregate_name="mixed_dates", information_cutoff=CUTOFF,
        )
    with pytest.raises(ValueError, match="unavailable at information cutoff"):
        aggregate_dated_claim_balances(
            (replace(_claim("1", "late", april),
                     available_at=datetime(2026, 5, 22, tzinfo=UTC)),),
            aggregate_name="late_claim", information_cutoff=CUTOFF,
        )


def test_synthetic_same_date_bridge_still_requires_separate_review() -> None:
    dcf, bridge = _bridge(VALUE_DATE)
    assert bridge.failed_structural_checks == ()
    assert bridge.eligibility_status is GateStatus.NOT_EVALUATED
    incomplete = assess_dcf_eligibility(dcf, _review(DCF_REVIEW_CHECKS))
    assert incomplete.status is GateStatus.WITHHELD
    assert "interim_cash_treatment_reviewed" in incomplete.failed_checks
    full_dcf = assess_dcf_eligibility(dcf, _review(
        DCF_REVIEW_CHECKS | frozenset({
            "dated_discount_timing_reviewed", "interim_cash_treatment_reviewed",
            "terminal_cash_flow_economics_reviewed",
        })
    ))
    full_bridge = assess_dated_equity_bridge_eligibility(
        bridge, full_dcf,
        _review(EQUITY_BRIDGE_REVIEW_CHECKS | frozenset({"lease_policy_and_claim_basis_reviewed"})),
    )
    assert full_bridge.status is GateStatus.PASS
    assert eligible_valuation_amount(bridge, full_bridge) == bridge.equity_value
