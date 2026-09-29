"""Structural DCF and enterprise-to-equity math with explicit claim matching.

These functions do not establish that a company's forecast, terminal state,
peer set, discount rate or claims are evidentially adequate. The caller must
complete those case-specific review gates before releasing a valuation.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType

from versioned_finance_core.contracts.enums import GateStatus

DCF_REVIEW_CHECKS = frozenset(
    {
        "source_rights_and_vintage",
        "linked_forecast_reconciled",
        "discount_rate_supported",
        "terminal_state_supported",
        "claim_scope_reconciled",
    }
)
EQUITY_BRIDGE_REVIEW_CHECKS = frozenset(
    {
        "source_rights_and_vintage",
        "claim_balances_complete",
        "claim_scope_reconciled",
    }
)


class CashFlowClaim(StrEnum):
    FCFF = "FCFF"
    FCFE = "FCFE"


class DiscountRateClaim(StrEnum):
    WACC = "WACC"
    COST_OF_EQUITY = "COST_OF_EQUITY"


class RateBasis(StrEnum):
    NOMINAL = "NOMINAL"
    REAL = "REAL"


@dataclass(frozen=True, slots=True)
class ForecastCashFlow:
    period_index: int
    amount: Decimal
    output_id: str

    def __post_init__(self) -> None:
        if isinstance(self.period_index, bool) or not isinstance(self.period_index, int):
            raise TypeError("period_index must be an integer")
        if self.period_index < 1:
            raise ValueError("period_index must be positive")
        _finite(self.amount, "amount")
        _nonempty(self.output_id, "output_id")


@dataclass(frozen=True, slots=True)
class DcfInputs:
    cash_flow_claim: CashFlowClaim
    discount_rate_claim: DiscountRateClaim
    cash_flow_basis: RateBasis
    discount_rate_basis: RateBasis
    cash_flow_currency: str
    discount_rate_currency: str
    forecast_version_id: str
    annual_cash_flows: tuple[ForecastCashFlow, ...]
    annual_discount_rate: Decimal
    discount_rate_assumption_id: str
    terminal_next_cash_flow: Decimal
    terminal_growth_rate: Decimal
    terminal_state_assumption_id: str


@dataclass(frozen=True, slots=True)
class DcfResult:
    value_claim: str
    forecast_version_id: str
    explicit_period_value: Decimal
    terminal_value_at_horizon: Decimal
    present_terminal_value: Decimal
    total_value: Decimal
    output_id: str
    input_lineage: tuple[tuple[str, str], ...]
    eligibility_status: GateStatus = GateStatus.NOT_EVALUATED


def value_perpetuity_dcf(inputs: DcfInputs) -> DcfResult:
    """Discount annual FCF and a separately supported terminal-year cash flow."""

    if not isinstance(inputs.cash_flow_claim, CashFlowClaim):
        raise TypeError("cash_flow_claim must be a CashFlowClaim")
    if not isinstance(inputs.discount_rate_claim, DiscountRateClaim):
        raise TypeError("discount_rate_claim must be a DiscountRateClaim")
    if not isinstance(inputs.cash_flow_basis, RateBasis) or not isinstance(
        inputs.discount_rate_basis, RateBasis
    ):
        raise TypeError("cash-flow and discount-rate basis must be RateBasis")
    expected_rate = {
        CashFlowClaim.FCFF: DiscountRateClaim.WACC,
        CashFlowClaim.FCFE: DiscountRateClaim.COST_OF_EQUITY,
    }
    if inputs.discount_rate_claim != expected_rate.get(inputs.cash_flow_claim):
        raise ValueError("cash-flow claim and discount-rate claim do not match")
    if inputs.cash_flow_basis != inputs.discount_rate_basis:
        raise ValueError("cash-flow and discount-rate nominal/real basis differ")
    if inputs.cash_flow_currency != inputs.discount_rate_currency:
        raise ValueError("cash-flow and discount-rate currency differ")
    _nonempty(inputs.cash_flow_currency, "cash_flow_currency")
    _nonempty(inputs.forecast_version_id, "forecast_version_id")
    _nonempty(inputs.discount_rate_assumption_id, "discount_rate_assumption_id")
    _nonempty(inputs.terminal_state_assumption_id, "terminal_state_assumption_id")
    rate = _finite(inputs.annual_discount_rate, "annual_discount_rate")
    growth = _finite(inputs.terminal_growth_rate, "terminal_growth_rate")
    terminal_cash_flow = _finite(inputs.terminal_next_cash_flow, "terminal_next_cash_flow")
    if rate <= growth:
        raise ValueError("annual_discount_rate must exceed terminal_growth_rate")
    if rate <= -1 or growth <= -1:
        raise ValueError("discount and growth rates must exceed -1")
    if terminal_cash_flow <= 0:
        raise ValueError("terminal_next_cash_flow must be positive for perpetuity DCF")
    flows = inputs.annual_cash_flows
    if not isinstance(flows, tuple) or any(
        not isinstance(flow, ForecastCashFlow) for flow in flows
    ):
        raise ValueError("annual_cash_flows must be a tuple of ForecastCashFlow")
    if not flows:
        raise ValueError("at least one forecast cash flow is required")
    if tuple(flow.period_index for flow in flows) != tuple(range(1, len(flows) + 1)):
        raise ValueError("forecast period_index must be contiguous from one")
    if len({flow.output_id for flow in flows}) != len(flows):
        raise ValueError("forecast output_id must be unique")

    explicit = sum(
        (flow.amount / (Decimal(1) + rate) ** flow.period_index for flow in flows),
        Decimal(0),
    )
    terminal = terminal_cash_flow / (rate - growth)
    present_terminal = terminal / (Decimal(1) + rate) ** len(flows)
    value_claim = (
        "ENTERPRISE_VALUE" if inputs.cash_flow_claim is CashFlowClaim.FCFF else "EQUITY_VALUE"
    )
    lineage = (
        ("forecast_version", inputs.forecast_version_id),
        *((f"cash_flow_period_{flow.period_index}", flow.output_id) for flow in flows),
        ("discount_rate_assumption", inputs.discount_rate_assumption_id),
        ("terminal_state_assumption", inputs.terminal_state_assumption_id),
    )
    total_value = explicit + present_terminal
    output_id = _output_id(
        "m1_dcf",
        {
            "schema_version": 1,
            "value_claim": value_claim,
            "cash_flow_claim": inputs.cash_flow_claim.value,
            "discount_rate_claim": inputs.discount_rate_claim.value,
            "rate_basis": inputs.discount_rate_basis.value,
            "currency": inputs.cash_flow_currency,
            "lineage": lineage,
            "cash_flows": [(flow.period_index, str(flow.amount)) for flow in flows],
            "annual_discount_rate": str(rate),
            "terminal_next_cash_flow": str(terminal_cash_flow),
            "terminal_growth_rate": str(growth),
            "explicit_period_value": str(explicit),
            "terminal_value_at_horizon": str(terminal),
            "present_terminal_value": str(present_terminal),
            "total_value": str(total_value),
        },
    )
    return DcfResult(
        value_claim=value_claim,
        forecast_version_id=inputs.forecast_version_id,
        explicit_period_value=explicit,
        terminal_value_at_horizon=terminal,
        present_terminal_value=present_terminal,
        total_value=total_value,
        output_id=output_id,
        input_lineage=lineage,
    )


@dataclass(frozen=True, slots=True)
class EnterpriseToEquityInputs:
    enterprise_value: Decimal
    excess_cash: Decimal
    nonoperating_assets: Decimal
    debt_like_claims: Decimal
    minority_interest: Decimal
    other_senior_claims: Decimal


def enterprise_to_equity(inputs: EnterpriseToEquityInputs) -> Decimal:
    """Return arithmetic only; this value has no release eligibility on its own."""

    _finite(inputs.enterprise_value, "enterprise_value")
    for name in (
        "excess_cash", "nonoperating_assets", "debt_like_claims",
        "minority_interest", "other_senior_claims",
    ):
        value = _finite(getattr(inputs, name), name)
        if value < 0:
            raise ValueError(f"{name} must be nonnegative")
    return (
        inputs.enterprise_value + inputs.excess_cash + inputs.nonoperating_assets
        - inputs.debt_like_claims - inputs.minority_interest - inputs.other_senior_claims
    )


@dataclass(frozen=True, slots=True)
class ClaimBridgeEvidence:
    enterprise_value_output_id: str
    excess_cash_source_id: str
    nonoperating_assets_source_id: str
    debt_like_claims_source_id: str
    minority_interest_source_id: str
    other_senior_claims_source_id: str

    def __post_init__(self) -> None:
        for name in (
            "enterprise_value_output_id", "excess_cash_source_id",
            "nonoperating_assets_source_id", "debt_like_claims_source_id",
            "minority_interest_source_id", "other_senior_claims_source_id",
        ):
            _nonempty(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class EquityClaimBridgeResult:
    parent_dcf_output_id: str
    equity_value: Decimal
    output_id: str
    input_lineage: tuple[tuple[str, str], ...]
    eligibility_status: GateStatus = GateStatus.NOT_EVALUATED


def bridge_enterprise_to_equity(
    dcf: DcfResult,
    inputs: EnterpriseToEquityInputs,
    evidence: ClaimBridgeEvidence,
) -> EquityClaimBridgeResult:
    """Pin claim arithmetic to one FCFF DCF output and identified claim inputs."""

    if dcf.value_claim != "ENTERPRISE_VALUE":
        raise ValueError("claim bridge requires an FCFF enterprise-value DCF")
    if inputs.enterprise_value != dcf.total_value:
        raise ValueError("enterprise_value must equal the pinned DCF result")
    if evidence.enterprise_value_output_id != dcf.output_id:
        raise ValueError("enterprise_value_output_id does not match DCF result")
    equity_value = enterprise_to_equity(inputs)
    lineage = (
        ("enterprise_value", dcf.output_id),
        ("excess_cash", evidence.excess_cash_source_id),
        ("nonoperating_assets", evidence.nonoperating_assets_source_id),
        ("debt_like_claims", evidence.debt_like_claims_source_id),
        ("minority_interest", evidence.minority_interest_source_id),
        ("other_senior_claims", evidence.other_senior_claims_source_id),
    )
    output_id = _output_id(
        "m1_equity_bridge",
        {
            "schema_version": 1,
            "lineage": lineage,
            "enterprise_value": str(inputs.enterprise_value),
            "excess_cash": str(inputs.excess_cash),
            "nonoperating_assets": str(inputs.nonoperating_assets),
            "debt_like_claims": str(inputs.debt_like_claims),
            "minority_interest": str(inputs.minority_interest),
            "other_senior_claims": str(inputs.other_senior_claims),
            "equity_value": str(equity_value),
        },
    )
    return EquityClaimBridgeResult(
        parent_dcf_output_id=dcf.output_id,
        equity_value=equity_value,
        output_id=output_id,
        input_lineage=lineage,
    )


@dataclass(frozen=True, slots=True)
class ValuationEligibilityReview:
    """Explicit human review assertions; their factual truth is external to code."""

    review_id: str
    reviewer_id: str
    reviewed_at: datetime
    checks: Mapping[str, bool]

    def __post_init__(self) -> None:
        _nonempty(self.review_id, "review_id")
        _nonempty(self.reviewer_id, "reviewer_id")
        if (
            not isinstance(self.reviewed_at, datetime)
            or self.reviewed_at.tzinfo is None
            or self.reviewed_at.utcoffset() is None
        ):
            raise ValueError("reviewed_at must be offset-aware")
        if not isinstance(self.checks, Mapping):
            raise TypeError("checks must be a mapping")
        checked = dict(self.checks)
        if any(not isinstance(name, str) or not isinstance(value, bool) for name, value in checked.items()):
            raise ValueError("review checks must map names to booleans")
        object.__setattr__(self, "checks", MappingProxyType(checked))


@dataclass(frozen=True, slots=True)
class ValuationEligibilityResult:
    calculation_output_id: str
    review_id: str
    reviewer_id: str
    reviewed_at: datetime
    status: GateStatus
    failed_checks: tuple[str, ...]
    dependency_output_ids: tuple[str, ...]
    output_id: str


def assess_dcf_eligibility(
    result: DcfResult, review: ValuationEligibilityReview
) -> ValuationEligibilityResult:
    """Only an explicit review can mark a numeric DCF eligible for release."""

    return _assess(result.output_id, review, DCF_REVIEW_CHECKS)


def assess_equity_bridge_eligibility(
    bridge: EquityClaimBridgeResult,
    dcf_eligibility: ValuationEligibilityResult,
    review: ValuationEligibilityReview,
) -> ValuationEligibilityResult:
    """Require a passed parent DCF gate as well as reviewed equity claims."""

    if dcf_eligibility.calculation_output_id != bridge.parent_dcf_output_id:
        raise ValueError("parent DCF eligibility does not match claim bridge")
    additional_failed = (
        ("parent_dcf_eligibility",)
        if dcf_eligibility.status is not GateStatus.PASS else ()
    )
    return _assess(
        bridge.output_id, review, EQUITY_BRIDGE_REVIEW_CHECKS,
        additional_failed=additional_failed,
        dependency_output_ids=(dcf_eligibility.output_id,),
    )


def eligible_valuation_amount(
    result: DcfResult | EquityClaimBridgeResult,
    eligibility: ValuationEligibilityResult,
) -> Decimal:
    """Memo/release adapter must use a matching passed review to emit a value."""

    if eligibility.calculation_output_id != result.output_id:
        raise ValueError("eligibility does not match valuation output_id")
    if eligibility.status is not GateStatus.PASS:
        raise ValueError("valuation is not eligible for release")
    return result.total_value if isinstance(result, DcfResult) else result.equity_value


def _assess(
    calculation_output_id: str,
    review: ValuationEligibilityReview,
    required_checks: frozenset[str],
    *,
    additional_failed: tuple[str, ...] = (),
    dependency_output_ids: tuple[str, ...] = (),
) -> ValuationEligibilityResult:
    failed = tuple(
        sorted({*additional_failed, *(name for name in required_checks if review.checks.get(name) is not True)})
    )
    status = GateStatus.WITHHELD if failed else GateStatus.PASS
    output_id = _output_id(
        "m1_valuation_review",
        {
            "schema_version": 1,
            "calculation_output_id": calculation_output_id,
            "review_id": review.review_id,
            "reviewer_id": review.reviewer_id,
            "reviewed_at": review.reviewed_at.astimezone(UTC).isoformat(),
            "checks": sorted(review.checks.items()),
            "status": status.value,
            "failed_checks": failed,
            "dependency_output_ids": dependency_output_ids,
        },
    )
    return ValuationEligibilityResult(
        calculation_output_id=calculation_output_id,
        review_id=review.review_id,
        reviewer_id=review.reviewer_id,
        reviewed_at=review.reviewed_at,
        status=status,
        failed_checks=failed,
        dependency_output_ids=dependency_output_ids,
        output_id=output_id,
    )


def _output_id(prefix: str, payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()}"


def _finite(value: Decimal, name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal")
    return value


def _nonempty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
