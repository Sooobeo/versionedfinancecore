from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from versioned_finance_core.contracts.enums import GateStatus
from versioned_finance_core.modules.m1.valuation import (
    DCF_REVIEW_CHECKS,
    EQUITY_BRIDGE_REVIEW_CHECKS,
    CashFlowClaim,
    ClaimBridgeEvidence,
    DcfInputs,
    DiscountRateClaim,
    EnterpriseToEquityInputs,
    ForecastCashFlow,
    RateBasis,
    ValuationEligibilityReview,
    assess_dcf_eligibility,
    assess_equity_bridge_eligibility,
    bridge_enterprise_to_equity,
    eligible_valuation_amount,
    enterprise_to_equity,
    value_perpetuity_dcf,
)


def d(value: str | int) -> Decimal:
    return Decimal(value)


def inputs() -> DcfInputs:
    return DcfInputs(
        cash_flow_claim=CashFlowClaim.FCFF,
        discount_rate_claim=DiscountRateClaim.WACC,
        cash_flow_basis=RateBasis.NOMINAL,
        discount_rate_basis=RateBasis.NOMINAL,
        cash_flow_currency="KRW",
        discount_rate_currency="KRW",
        forecast_version_id="synthetic_forecast_v1",
        annual_cash_flows=(
            ForecastCashFlow(1, d(100), "fcff_y1"),
            ForecastCashFlow(2, d(125), "fcff_y2"),
        ),
        annual_discount_rate=d("0.25"),
        discount_rate_assumption_id="synthetic_wacc_assumption",
        terminal_next_cash_flow=d(125),
        terminal_growth_rate=d(0),
        terminal_state_assumption_id="synthetic_terminal_state",
    )


def test_fcff_dcf_and_claim_bridge_known_answer() -> None:
    value = value_perpetuity_dcf(inputs())
    assert value.value_claim == "ENTERPRISE_VALUE"
    assert value.explicit_period_value == d(160)
    assert value.terminal_value_at_horizon == d(500)
    assert value.present_terminal_value == d(320)
    assert value.total_value == d(480)
    assert value.eligibility_status is GateStatus.NOT_EVALUATED
    assert value.output_id.startswith("m1_dcf_")
    assert ("cash_flow_period_1", "fcff_y1") in value.input_lineage
    assert ("terminal_state_assumption", "synthetic_terminal_state") in value.input_lineage
    assert enterprise_to_equity(
        EnterpriseToEquityInputs(d(480), d(50), d(20), d(100), d(10), d(0))
    ) == d(440)


def test_fcfe_requires_cost_of_equity_and_returns_equity_claim() -> None:
    value = value_perpetuity_dcf(
        replace(
            inputs(),
            cash_flow_claim=CashFlowClaim.FCFE,
            discount_rate_claim=DiscountRateClaim.COST_OF_EQUITY,
        )
    )
    assert value.value_claim == "EQUITY_VALUE"
    assert value.total_value == d(480)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"discount_rate_claim": DiscountRateClaim.COST_OF_EQUITY}, "do not match"),
        ({"discount_rate_basis": RateBasis.REAL}, "basis differ"),
        ({"discount_rate_currency": "USD"}, "currency differ"),
        ({"annual_discount_rate": d(0)}, "must exceed"),
        ({"terminal_next_cash_flow": d(0)}, "must be positive"),
        ({"terminal_state_assumption_id": ""}, "terminal_state_assumption_id"),
        ({"annual_discount_rate": 0.25}, "finite Decimal"),
        ({"annual_cash_flows": ()}, "at least one"),
    ],
)
def test_structural_valuation_gate_fails_closed(changes: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        value_perpetuity_dcf(replace(inputs(), **changes))  # type: ignore[arg-type]


def test_rejects_gap_in_forecast_periods_and_negative_debt_claim() -> None:
    with pytest.raises(ValueError, match="contiguous"):
        value_perpetuity_dcf(
            replace(
                inputs(),
                annual_cash_flows=(
                    ForecastCashFlow(1, d(100), "fcff_y1"),
                    ForecastCashFlow(3, d(125), "fcff_y3"),
                ),
            )
        )
    with pytest.raises(ValueError, match="debt_like_claims"):
        enterprise_to_equity(
            EnterpriseToEquityInputs(d(480), d(50), d(20), d(-100), d(10), d(0))
        )


def review(checks: set[str], review_id: str = "synthetic_review") -> ValuationEligibilityReview:
    return ValuationEligibilityReview(
        review_id=review_id,
        reviewer_id="synthetic_reviewer",
        reviewed_at=datetime(2026, 8, 18, tzinfo=UTC),
        checks={name: True for name in checks},
    )


def claim_evidence(dcf_output_id: str) -> ClaimBridgeEvidence:
    return ClaimBridgeEvidence(
        enterprise_value_output_id=dcf_output_id,
        excess_cash_source_id="synthetic_cash_source",
        nonoperating_assets_source_id="synthetic_nonoperating_source",
        debt_like_claims_source_id="synthetic_debt_source",
        minority_interest_source_id="synthetic_minority_source",
        other_senior_claims_source_id="synthetic_other_claim_source",
    )


def test_dcf_output_id_is_deterministic_and_tracks_input_lineage() -> None:
    original = value_perpetuity_dcf(inputs())
    assert value_perpetuity_dcf(inputs()).output_id == original.output_id
    changed_source = value_perpetuity_dcf(
        replace(inputs(), terminal_state_assumption_id="other_terminal_assumption")
    )
    changed_amount = value_perpetuity_dcf(
        replace(inputs(), terminal_next_cash_flow=d(150))
    )
    assert changed_source.output_id != original.output_id
    assert changed_amount.output_id != original.output_id


def test_dcf_release_value_requires_explicit_complete_eligibility_review() -> None:
    dcf = value_perpetuity_dcf(inputs())
    missing_terminal = review(DCF_REVIEW_CHECKS - {"terminal_state_supported"})
    withheld = assess_dcf_eligibility(dcf, missing_terminal)
    assert withheld.status is GateStatus.WITHHELD
    assert withheld.failed_checks == ("terminal_state_supported",)
    with pytest.raises(ValueError, match="not eligible"):
        eligible_valuation_amount(dcf, withheld)

    passing = assess_dcf_eligibility(dcf, review(DCF_REVIEW_CHECKS))
    assert passing.status is GateStatus.PASS
    assert passing.calculation_output_id == dcf.output_id
    assert passing.output_id.startswith("m1_valuation_review_")
    assert eligible_valuation_amount(dcf, passing) == d(480)
    with pytest.raises(ValueError, match="does not match"):
        eligible_valuation_amount(
            value_perpetuity_dcf(replace(inputs(), terminal_next_cash_flow=d(150))),
            passing,
        )


def test_claim_bridge_requires_pinned_dcf_and_separate_claim_review() -> None:
    dcf = value_perpetuity_dcf(inputs())
    bridge_inputs = EnterpriseToEquityInputs(d(480), d(50), d(20), d(100), d(10), d(0))
    bridge = bridge_enterprise_to_equity(dcf, bridge_inputs, claim_evidence(dcf.output_id))
    assert bridge.equity_value == d(440)
    assert bridge.eligibility_status is GateStatus.NOT_EVALUATED
    assert bridge.parent_dcf_output_id == dcf.output_id
    assert ("debt_like_claims", "synthetic_debt_source") in bridge.input_lineage
    assert bridge_enterprise_to_equity(
        dcf, bridge_inputs, claim_evidence(dcf.output_id)
    ).output_id == bridge.output_id

    dcf_withheld = assess_dcf_eligibility(
        dcf, review(DCF_REVIEW_CHECKS - {"terminal_state_supported"})
    )
    blocked = assess_equity_bridge_eligibility(
        bridge, dcf_withheld, review(EQUITY_BRIDGE_REVIEW_CHECKS)
    )
    assert blocked.status is GateStatus.WITHHELD
    assert blocked.failed_checks == ("parent_dcf_eligibility",)

    dcf_passed = assess_dcf_eligibility(dcf, review(DCF_REVIEW_CHECKS))
    incomplete = assess_equity_bridge_eligibility(
        bridge,
        dcf_passed,
        review(EQUITY_BRIDGE_REVIEW_CHECKS - {"claim_balances_complete"}),
    )
    assert incomplete.status is GateStatus.WITHHELD
    assert incomplete.failed_checks == ("claim_balances_complete",)
    bridge_passed = assess_equity_bridge_eligibility(
        bridge, dcf_passed, review(EQUITY_BRIDGE_REVIEW_CHECKS)
    )
    assert bridge_passed.dependency_output_ids == (dcf_passed.output_id,)
    assert eligible_valuation_amount(bridge, bridge_passed) == d(440)
    another_dcf_review = assess_dcf_eligibility(
        dcf, review(DCF_REVIEW_CHECKS, "second_review")
    )
    assert assess_equity_bridge_eligibility(
        bridge, another_dcf_review, review(EQUITY_BRIDGE_REVIEW_CHECKS)
    ).output_id != bridge_passed.output_id

    with pytest.raises(ValueError, match="pinned DCF"):
        bridge_enterprise_to_equity(
            dcf, replace(bridge_inputs, enterprise_value=d(481)), claim_evidence(dcf.output_id)
        )
    with pytest.raises(ValueError, match="output_id"):
        bridge_enterprise_to_equity(dcf, bridge_inputs, claim_evidence("different_dcf"))
    with pytest.raises(ValueError, match="FCFF"):
        bridge_enterprise_to_equity(
            value_perpetuity_dcf(
                replace(
                    inputs(),
                    cash_flow_claim=CashFlowClaim.FCFE,
                    discount_rate_claim=DiscountRateClaim.COST_OF_EQUITY,
                )
            ),
            bridge_inputs,
            claim_evidence(dcf.output_id),
        )
