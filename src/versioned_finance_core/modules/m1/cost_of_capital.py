"""Evidence-pinned CAPM and WACC arithmetic for M1 valuation.

Calculation creates a reviewable discount-rate output, not a release-approved
rate. Stale shares, carrying debt proxies, sector beta, and lease mismatches
remain visible limitations rather than being hidden in a single WACC number.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, localcontext
from enum import StrEnum

from versioned_finance_core.contracts.enums import AccountingScope, GateStatus
from versioned_finance_core.modules.m1.valuation import (
    LeasePolicyEvidence,
    LeaseValuationTreatment,
    RateBasis,
)


class BetaBasis(StrEnum):
    COMPANY_OBSERVED = "COMPANY_OBSERVED"
    SECTOR_PROXY = "SECTOR_PROXY"


class DebtValueBasis(StrEnum):
    MARKET_VALUE = "MARKET_VALUE"
    CARRYING_PROXY = "CARRYING_PROXY"


@dataclass(frozen=True, slots=True)
class SourcedValuationParameter:
    value: Decimal
    assumption_id: str
    basis_source_ids: tuple[str, ...]
    observation_date: date
    available_at: datetime
    rationale: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal) or not self.value.is_finite():
            raise ValueError("valuation parameter must be a finite Decimal")
        if not isinstance(self.assumption_id, str) or not self.assumption_id.strip():
            raise ValueError("assumption_id is required")
        if not isinstance(self.basis_source_ids, tuple) or not self.basis_source_ids:
            raise ValueError("valuation parameter requires basis source IDs")
        if any(not isinstance(item, str) or not item.strip() for item in self.basis_source_ids):
            raise ValueError("basis source IDs must be nonempty")
        if len(set(self.basis_source_ids)) != len(self.basis_source_ids):
            raise ValueError("duplicate basis source ID")
        if not isinstance(self.observation_date, date) or isinstance(
            self.observation_date, datetime
        ):
            raise TypeError("observation_date must be a date")
        if not isinstance(self.available_at, datetime) or (
            self.available_at.tzinfo is None or self.available_at.utcoffset() is None
        ):
            raise ValueError("available_at must be offset-aware")
        if not isinstance(self.rationale, str) or not self.rationale.strip():
            raise ValueError("rationale is required")


@dataclass(frozen=True, slots=True)
class WaccInputs:
    case_id: str
    assumption_id: str
    valuation_date: date
    information_cutoff: datetime
    accounting_scope: AccountingScope
    economic_scope_id: str
    currency: str
    rate_basis: RateBasis
    risk_free_rate: SourcedValuationParameter
    levered_beta: SourcedValuationParameter
    equity_risk_premium: SourcedValuationParameter
    marginal_tax_rate: SourcedValuationParameter
    share_price: SourcedValuationParameter
    shares_outstanding: SourcedValuationParameter
    debt_value: SourcedValuationParameter
    beta_basis: BetaBasis
    debt_value_basis: DebtValueBasis
    lease_policy: LeasePolicyEvidence
    marginal_pre_tax_debt_rate: SourcedValuationParameter | None = None
    marginal_debt_spread: SourcedValuationParameter | None = None


@dataclass(frozen=True, slots=True)
class WaccResult:
    case_id: str
    assumption_id: str
    valuation_date: date
    currency: str
    risk_free_rate: Decimal
    cost_of_equity: Decimal
    pre_tax_cost_of_debt: Decimal
    after_tax_cost_of_debt: Decimal
    market_equity_value: Decimal
    debt_value: Decimal
    equity_weight: Decimal
    debt_weight: Decimal
    wacc: Decimal
    lease_policy_id: str
    failed_structural_checks: tuple[str, ...]
    eligibility_status: GateStatus
    input_lineage: tuple[tuple[str, str], ...]
    output_id: str


def calculate_wacc(inputs: WaccInputs) -> WaccResult:
    """Calculate nominal WACC from CAPM and market capital weights.

    Marginal debt cost is either an evidenced current yield or a spread added
    to the matched risk-free input. Reported coupon is not substituted.
    """

    if not isinstance(inputs, WaccInputs):
        raise TypeError("inputs must be WaccInputs")
    for name in ("case_id", "assumption_id", "economic_scope_id", "currency"):
        value = getattr(inputs, name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} is required")
    if not isinstance(inputs.accounting_scope, AccountingScope):
        raise TypeError("accounting_scope must be AccountingScope")
    if not isinstance(inputs.valuation_date, date) or isinstance(inputs.valuation_date, datetime):
        raise TypeError("valuation_date must be a date")
    if not isinstance(inputs.information_cutoff, datetime) or (
        inputs.information_cutoff.tzinfo is None
        or inputs.information_cutoff.utcoffset() is None
    ):
        raise ValueError("information_cutoff must be offset-aware")
    if inputs.valuation_date > inputs.information_cutoff.date():
        raise ValueError("valuation_date is after information_cutoff")
    if inputs.rate_basis is not RateBasis.NOMINAL:
        raise ValueError("financial-statement WACC requires nominal rate basis")
    if not isinstance(inputs.beta_basis, BetaBasis):
        raise TypeError("beta_basis must be BetaBasis")
    if not isinstance(inputs.debt_value_basis, DebtValueBasis):
        raise TypeError("debt_value_basis must be DebtValueBasis")
    if not isinstance(inputs.lease_policy, LeasePolicyEvidence):
        raise TypeError("lease_policy must be LeasePolicyEvidence")
    if inputs.lease_policy.available_at > inputs.information_cutoff:
        raise ValueError("lease policy is unavailable at information cutoff")
    if inputs.lease_policy.available_at.astimezone(
        inputs.information_cutoff.tzinfo
    ).date() > inputs.valuation_date:
        raise ValueError("lease policy is unavailable at valuation_date")
    if (inputs.marginal_pre_tax_debt_rate is None) == (inputs.marginal_debt_spread is None):
        raise ValueError("provide exactly one marginal debt rate or debt spread")

    parameter_names = (
        "risk_free_rate", "levered_beta", "equity_risk_premium", "marginal_tax_rate",
        "share_price", "shares_outstanding", "debt_value",
    )
    selected_debt_name = (
        "marginal_pre_tax_debt_rate" if inputs.marginal_pre_tax_debt_rate is not None
        else "marginal_debt_spread"
    )
    parameter_names = (*parameter_names, selected_debt_name)
    for name in parameter_names:
        parameter = getattr(inputs, name)
        if not isinstance(parameter, SourcedValuationParameter):
            raise TypeError(f"{name} must be SourcedValuationParameter")
        if parameter.available_at > inputs.information_cutoff:
            raise ValueError(f"{name} is unavailable at information cutoff")
        if parameter.available_at.astimezone(
            inputs.information_cutoff.tzinfo
        ).date() > inputs.valuation_date:
            raise ValueError(f"{name} is unavailable at valuation_date")
        if parameter.observation_date > inputs.valuation_date:
            raise ValueError(f"{name} observation is after valuation_date")
    if inputs.risk_free_rate.value <= -1:
        raise ValueError("risk_free_rate must exceed -1")
    if not Decimal(0) <= inputs.marginal_tax_rate.value < Decimal(1):
        raise ValueError("marginal_tax_rate must be in [0, 1)")
    if inputs.share_price.value <= 0 or inputs.shares_outstanding.value <= 0:
        raise ValueError("share price and outstanding shares must be positive")
    if inputs.debt_value.value < 0:
        raise ValueError("debt_value must be nonnegative")
    with localcontext() as decimal_context:
        decimal_context.prec = 50
        debt_rate = (
            inputs.marginal_pre_tax_debt_rate.value
            if inputs.marginal_pre_tax_debt_rate is not None
            else inputs.risk_free_rate.value + inputs.marginal_debt_spread.value
        )
        if debt_rate <= -1:
            raise ValueError("marginal pre-tax debt rate must exceed -1")
        equity_value = inputs.share_price.value * inputs.shares_outstanding.value
        capital_value = equity_value + inputs.debt_value.value
        equity_weight = equity_value / capital_value
        debt_weight = Decimal(1) - equity_weight
        cost_of_equity = (
            inputs.risk_free_rate.value
            + inputs.levered_beta.value * inputs.equity_risk_premium.value
        )
        after_tax_debt = debt_rate * (Decimal(1) - inputs.marginal_tax_rate.value)
        wacc = equity_weight * cost_of_equity + debt_weight * after_tax_debt

    failed: list[str] = []
    if inputs.beta_basis is BetaBasis.SECTOR_PROXY:
        failed.append("beta_company_fit")
    if inputs.debt_value_basis is DebtValueBasis.CARRYING_PROXY:
        failed.append("market_debt_value_basis")
    for name in ("share_price", "shares_outstanding", "debt_value"):
        if getattr(inputs, name).observation_date != inputs.valuation_date:
            failed.append(f"{name}_as_of_date")
    expected_lease_flags = {
        LeaseValuationTreatment.OPERATING_COST_INCLUDED: (True, False, False),
        LeaseValuationTreatment.CAPITALIZED_FINANCING: (False, True, True),
        LeaseValuationTreatment.MIXED_OPERATING_AND_FINANCE: (True, True, True),
        LeaseValuationTreatment.NOT_APPLICABLE: (False, False, False),
    }
    observed_lease_flags = (
        inputs.lease_policy.lease_cost_in_fcff,
        inputs.lease_policy.lease_liability_in_debt_like_claims,
        inputs.lease_policy.lease_financing_in_wacc,
    )
    if expected_lease_flags.get(inputs.lease_policy.treatment) != observed_lease_flags:
        failed.append("lease_valuation_treatment")

    lineage = tuple(
        (f"{name}_assumption", getattr(inputs, name).assumption_id)
        for name in parameter_names
    ) + tuple(
        (f"{name}_source_{index}", source_id)
        for name in parameter_names
        for index, source_id in enumerate(getattr(inputs, name).basis_source_ids, start=1)
    ) + (("lease_policy", inputs.lease_policy.policy_id),)
    status = GateStatus.WITHHELD if failed else GateStatus.NOT_EVALUATED
    payload = {
        "schema_version": 1,
        "case_id": inputs.case_id,
        "assumption_id": inputs.assumption_id,
        "valuation_date": inputs.valuation_date.isoformat(),
        "information_cutoff": inputs.information_cutoff.astimezone(UTC).isoformat(),
        "accounting_scope": inputs.accounting_scope.value,
        "economic_scope_id": inputs.economic_scope_id,
        "currency": inputs.currency,
        "rate_basis": inputs.rate_basis.value,
        "beta_basis": inputs.beta_basis.value,
        "debt_value_basis": inputs.debt_value_basis.value,
        "parameters": [
            (name, str(getattr(inputs, name).value), getattr(inputs, name).assumption_id,
             getattr(inputs, name).basis_source_ids,
             getattr(inputs, name).observation_date.isoformat(),
             getattr(inputs, name).available_at.astimezone(UTC).isoformat(),
             getattr(inputs, name).rationale)
            for name in parameter_names
        ],
        "lease_policy": (inputs.lease_policy.treatment.value, inputs.lease_policy.policy_id,
                         inputs.lease_policy.source_ids, observed_lease_flags),
        "cost_of_equity": str(cost_of_equity),
        "pre_tax_cost_of_debt": str(debt_rate),
        "after_tax_cost_of_debt": str(after_tax_debt),
        "equity_value": str(equity_value),
        "equity_weight": str(equity_weight),
        "debt_weight": str(debt_weight),
        "wacc": str(wacc),
        "failed_structural_checks": failed,
    }
    output_id = "m1_wacc_" + hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    return WaccResult(
        case_id=inputs.case_id, assumption_id=inputs.assumption_id,
        valuation_date=inputs.valuation_date, currency=inputs.currency,
        risk_free_rate=inputs.risk_free_rate.value,
        cost_of_equity=cost_of_equity, pre_tax_cost_of_debt=debt_rate,
        after_tax_cost_of_debt=after_tax_debt, market_equity_value=equity_value,
        debt_value=inputs.debt_value.value, equity_weight=equity_weight,
        debt_weight=debt_weight, wacc=wacc,
        lease_policy_id=inputs.lease_policy.policy_id,
        failed_structural_checks=tuple(failed), eligibility_status=status,
        input_lineage=lineage, output_id=output_id,
    )
