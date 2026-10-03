"""Known-answer and fail-closed tests for M1 valuation evidence controls."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal, localcontext

import pytest

from versioned_finance_core.contracts.enums import AccountingScope, GateStatus, KnowledgeState
from versioned_finance_core.modules.m1.valuation import (
    CashFlowClaim,
    DcfInputs,
    DiscountRateClaim,
    DiscountTiming,
    ForecastCashFlow,
    RateBasis,
    value_perpetuity_dcf,
)
from versioned_finance_core.modules.m1.valuation_controls import (
    DatedStubEvidence,
    HistoricalLeaseCashTaxEvidence,
    HistoricalLeaseCashTaxModelPolicy,
    assess_dated_dcf_stub_boundary,
    diagnose_historical_lease_and_cash_tax,
)


def _dated_dcf(valuation_date: date) -> object:
    """Build a minimal dated, Core-pinned DCF without deriving any FCF here."""

    available = datetime.combine(valuation_date, datetime.min.time(), tzinfo=UTC)
    return value_perpetuity_dcf(
        DcfInputs(
            cash_flow_claim=CashFlowClaim.FCFF,
            discount_rate_claim=DiscountRateClaim.WACC,
            cash_flow_basis=RateBasis.NOMINAL,
            discount_rate_basis=RateBasis.NOMINAL,
            cash_flow_currency="USD",
            discount_rate_currency="USD",
            forecast_version_id="synthetic_v1",
            annual_cash_flows=(
                ForecastCashFlow(1, Decimal(100), "core_fcff_1", date(2027, 1, 31)),
            ),
            annual_discount_rate=Decimal("0.10"),
            discount_rate_assumption_id="synthetic_wacc",
            terminal_next_cash_flow=Decimal(100),
            terminal_growth_rate=Decimal("0.02"),
            terminal_state_assumption_id="synthetic_terminal",
            case_id="synthetic_case",
            operating_baseline_output_id="core_baseline",
            core_cash_flow_path_output_id="core_path",
            discount_timing=DiscountTiming.ACT_365_FIXED,
            valuation_date=valuation_date,
            first_forecast_period_start=date(2026, 5, 1),
            information_cutoff=datetime(2026, 5, 21, 23, 59, tzinfo=UTC),
            discount_rate_available_at=available,
            terminal_state_available_at=available,
            discount_rate_basis_source_ids=("wacc_source",),
            terminal_state_basis_source_ids=("terminal_source",),
            accounting_scope=AccountingScope.CONSOLIDATED,
            economic_scope_id="synthetic_group",
            legal_entity_id="synthetic_group",
            unit="USD_MILLION",
            discount_rate_rationale="Synthetic dated WACC.",
            terminal_cash_flow_rationale="Synthetic terminal FCFF.",
        )
    )


def _historical_evidence() -> HistoricalLeaseCashTaxEvidence:
    return HistoricalLeaseCashTaxEvidence(
        period_start=date(2025, 2, 1),
        period_end=date(2026, 1, 31),
        available_at=datetime(2026, 3, 13, 6, 0, tzinfo=UTC),
        source_ids=("wmt_fy26_10k_html",),
        unit="USD_MILLION",
        total_depreciation_and_amortization=Decimal(14203),
        finance_lease_rou_amortization=Decimal(888),
        operating_lease_cost=Decimal(2434),
        finance_lease_interest=Decimal(383),
        finance_lease_income_statement_interest=Decimal(481),
        operating_lease_cash_paid=Decimal(2315),
        finance_lease_operating_cash_paid=Decimal(377),
        finance_lease_financing_cash_paid=Decimal(891),
        income_tax_provision=Decimal(7199),
        cash_taxes_paid=Decimal(5364),
        pretax_income=Decimal(29469),
    )


def test_historical_lease_cash_tax_known_answer_stays_forward_unknown() -> None:
    diagnostic = diagnose_historical_lease_and_cash_tax(
        _historical_evidence(),
        HistoricalLeaseCashTaxModelPolicy(
            total_da_booked_to_ppe_depreciation=True,
            cash_tax_rate_equals_tax_expense_rate=True,
        ),
    )

    assert diagnostic.da_excluding_disclosed_finance_lease_rou_amortization == Decimal(13315)
    assert diagnostic.finance_lease_cash_paid == Decimal(1268)
    assert diagnostic.cash_tax_minus_provision == Decimal(-1835)
    assert diagnostic.finance_lease_income_statement_interest_minus_note_interest == Decimal(98)
    with localcontext() as decimal_context:
        decimal_context.prec = 50
        assert diagnostic.cash_tax_to_provision == Decimal(5364) / Decimal(7199)
    assert diagnostic.historical_evidence_state is KnowledgeState.KNOWN
    assert diagnostic.forward_application_state is KnowledgeState.UNKNOWN
    assert set(diagnostic.modeling_flags) >= {
        "total_da_includes_disclosed_finance_lease_rou_amortization",
        "cash_tax_equals_provision_despite_historical_difference",
        "lease_note_to_income_statement_interest_bridge_unresolved",
    }
    assert diagnostic.output_id == diagnose_historical_lease_and_cash_tax(
        _historical_evidence(),
        HistoricalLeaseCashTaxModelPolicy(True, True),
    ).output_id

    with pytest.raises(ValueError, match="exceeds total D&A"):
        replace(
            _historical_evidence(), finance_lease_rou_amortization=Decimal(14204)
        )


def test_unobserved_bisected_core_cash_flow_withholds_release_consumption() -> None:
    dcf = _dated_dcf(date(2026, 5, 21))
    boundary = assess_dated_dcf_stub_boundary(
        dcf,
        first_core_period_id="fy27_remainder",
        first_core_period_start=date(2026, 5, 1),
        first_core_period_end=date(2027, 1, 31),
        evidence=DatedStubEvidence(
            evidence_id="may_stub_unavailable",
            source_ids=("fy27_q1",),
            available_at=datetime(2026, 5, 21, tzinfo=UTC),
            last_disclosed_period_end=date(2026, 4, 30),
            realized_prevaluation_cash_flow=KnowledgeState.UNKNOWN,
        ),
    )

    assert boundary.prevaluation_days == 20
    assert boundary.postvaluation_days == 256
    assert boundary.realized_prevaluation_cash_flow is None
    assert boundary.realized_prevaluation_cash_flow_state is KnowledgeState.UNKNOWN
    assert boundary.requires_explicit_stub_treatment
    assert not boundary.can_enter_downstream_valuation_eligibility
    assert boundary.status is GateStatus.WITHHELD
    assert boundary.failed_checks == ("prevaluation_realized_cash_flow_unavailable",)
    assert boundary.release_consumable_enterprise_value is None

    with pytest.raises(ValueError, match="does not cover DCF stub"):
        assess_dated_dcf_stub_boundary(
            dcf,
            first_core_period_id="fy27_remainder",
            first_core_period_start=date(2026, 5, 1),
            first_core_period_end=date(2027, 1, 31),
            evidence=DatedStubEvidence(
                evidence_id="partial_observation",
                source_ids=("fy27_q1",),
                available_at=datetime(2026, 5, 21, tzinfo=UTC),
                last_disclosed_period_end=date(2026, 4, 30),
                realized_prevaluation_cash_flow=Decimal(1),
                realized_prevaluation_period_start=date(2026, 5, 2),
                realized_prevaluation_period_end=date(2026, 5, 20),
            ),
        )


def test_future_first_core_period_excludes_preperiod_gap_from_post_days() -> None:
    dcf = _dated_dcf(date(2026, 4, 30))
    boundary = assess_dated_dcf_stub_boundary(
        dcf,
        first_core_period_id="fy27_remainder",
        first_core_period_start=date(2026, 5, 1),
        first_core_period_end=date(2027, 1, 31),
        evidence=DatedStubEvidence(
            evidence_id="opening_balance_date",
            source_ids=("fy26_10k",),
            available_at=datetime(2026, 4, 30, tzinfo=UTC),
            last_disclosed_period_end=date(2026, 4, 30),
            realized_prevaluation_cash_flow=KnowledgeState.UNKNOWN,
        ),
    )

    with localcontext() as decimal_context:
        decimal_context.prec = 50
        assert dcf.period_year_fractions[0] == Decimal(276) / Decimal(365)
    assert boundary.prevaluation_days == 0
    assert boundary.postvaluation_days == 276
    assert not boundary.requires_explicit_stub_treatment
    assert boundary.can_enter_downstream_valuation_eligibility
    assert boundary.status is GateStatus.NOT_EVALUATED
