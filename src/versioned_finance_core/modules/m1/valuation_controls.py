"""Pure M1 controls for historical lease/tax evidence and dated DCF stubs.

These controls deliberately separate two things that are often collapsed in a
screening model: a disclosed historical observation, and evidence sufficient to
use a period-level cash flow at a valuation date inside that period.  They do
not create forecast cash flows, allocate a stub pro rata, or approve a release.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, localcontext

from versioned_finance_core.contracts.enums import GateStatus, KnowledgeState
from versioned_finance_core.modules.m1.valuation import DcfResult, DiscountTiming


def _finite(value: Decimal, label: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{label} must be a finite Decimal")
    return value


def _date(value: date, label: str) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TypeError(f"{label} must be a date")
    return value


def _timestamp(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be offset-aware")
    return value


def _source_ids(value: tuple[str, ...], label: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or not value:
        raise ValueError(f"{label} requires source IDs")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{label} source IDs must be nonempty text")
    if len(set(value)) != len(value):
        raise ValueError(f"{label} source IDs must be unique")
    return value


def _output_id(prefix: str, payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()}"


def _decimal_or_state(value: Decimal | KnowledgeState) -> str:
    return str(value) if isinstance(value, Decimal) else value.value


def _ratio(numerator: Decimal, denominator: Decimal) -> Decimal | KnowledgeState:
    if denominator == 0:
        return KnowledgeState.NM
    with localcontext() as decimal_context:
        decimal_context.prec = 50
        return numerator / denominator


@dataclass(frozen=True, slots=True)
class HistoricalLeaseCashTaxEvidence:
    """One fully sourced historical period, in a single reported unit."""

    period_start: date
    period_end: date
    available_at: datetime
    source_ids: tuple[str, ...]
    unit: str
    total_depreciation_and_amortization: Decimal
    finance_lease_rou_amortization: Decimal
    operating_lease_cost: Decimal
    finance_lease_interest: Decimal
    finance_lease_income_statement_interest: Decimal
    operating_lease_cash_paid: Decimal
    finance_lease_operating_cash_paid: Decimal
    finance_lease_financing_cash_paid: Decimal
    income_tax_provision: Decimal
    cash_taxes_paid: Decimal
    pretax_income: Decimal

    def __post_init__(self) -> None:
        start = _date(self.period_start, "period_start")
        end = _date(self.period_end, "period_end")
        if start > end:
            raise ValueError("period_start must not follow period_end")
        _timestamp(self.available_at, "available_at")
        _source_ids(self.source_ids, "historical lease/cash-tax evidence")
        if not isinstance(self.unit, str) or not self.unit.strip():
            raise ValueError("unit is required")
        for name in (
            "total_depreciation_and_amortization",
            "finance_lease_rou_amortization",
            "operating_lease_cost",
            "finance_lease_interest",
            "finance_lease_income_statement_interest",
            "operating_lease_cash_paid",
            "finance_lease_operating_cash_paid",
            "finance_lease_financing_cash_paid",
            "cash_taxes_paid",
        ):
            if _finite(getattr(self, name), name) < 0:
                raise ValueError(f"{name} must be nonnegative")
        _finite(self.income_tax_provision, "income_tax_provision")
        _finite(self.pretax_income, "pretax_income")
        if self.finance_lease_rou_amortization > self.total_depreciation_and_amortization:
            raise ValueError("finance lease ROU amortization exceeds total D&A")


@dataclass(frozen=True, slots=True)
class HistoricalLeaseCashTaxModelPolicy:
    """Declared model choices tested against, but not inferred from, history."""

    total_da_booked_to_ppe_depreciation: bool
    cash_tax_rate_equals_tax_expense_rate: bool

    def __post_init__(self) -> None:
        for name in (
            "total_da_booked_to_ppe_depreciation",
            "cash_tax_rate_equals_tax_expense_rate",
        ):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be bool")


@dataclass(frozen=True, slots=True)
class HistoricalLeaseCashTaxDiagnostic:
    """Auditable history diagnostic; it makes no forward cash-flow forecast."""

    period_start: date
    period_end: date
    unit: str
    source_ids: tuple[str, ...]
    total_depreciation_and_amortization: Decimal
    finance_lease_rou_amortization: Decimal
    da_excluding_disclosed_finance_lease_rou_amortization: Decimal
    operating_lease_cost: Decimal
    finance_lease_interest: Decimal
    finance_lease_income_statement_interest: Decimal
    finance_lease_income_statement_interest_minus_note_interest: Decimal
    operating_lease_cash_paid: Decimal
    finance_lease_cash_paid: Decimal
    income_tax_provision: Decimal
    cash_taxes_paid: Decimal
    cash_tax_minus_provision: Decimal
    cash_tax_to_provision: Decimal | KnowledgeState
    cash_tax_to_pretax_income: Decimal | KnowledgeState
    historical_evidence_state: KnowledgeState
    forward_application_state: KnowledgeState
    modeling_flags: tuple[str, ...]
    output_id: str

    def as_dict(self) -> dict[str, object]:
        """Return JSON-safe detail without converting unknown values to zero."""

        return {
            "output_id": self.output_id,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "unit": self.unit,
            "source_ids": self.source_ids,
            "total_depreciation_and_amortization": str(self.total_depreciation_and_amortization),
            "finance_lease_rou_amortization": str(self.finance_lease_rou_amortization),
            "da_excluding_disclosed_finance_lease_rou_amortization": str(
                self.da_excluding_disclosed_finance_lease_rou_amortization
            ),
            "operating_lease_cost": str(self.operating_lease_cost),
            "finance_lease_interest": str(self.finance_lease_interest),
            "finance_lease_income_statement_interest": str(
                self.finance_lease_income_statement_interest
            ),
            "finance_lease_income_statement_interest_minus_note_interest": str(
                self.finance_lease_income_statement_interest_minus_note_interest
            ),
            "operating_lease_cash_paid": str(self.operating_lease_cash_paid),
            "finance_lease_cash_paid": str(self.finance_lease_cash_paid),
            "income_tax_provision": str(self.income_tax_provision),
            "cash_taxes_paid": str(self.cash_taxes_paid),
            "cash_tax_minus_provision": str(self.cash_tax_minus_provision),
            "cash_tax_to_provision": _decimal_or_state(self.cash_tax_to_provision),
            "cash_tax_to_pretax_income": _decimal_or_state(self.cash_tax_to_pretax_income),
            "historical_evidence_state": self.historical_evidence_state.value,
            "forward_application_state": self.forward_application_state.value,
            "modeling_flags": self.modeling_flags,
        }


def diagnose_historical_lease_and_cash_tax(
    evidence: HistoricalLeaseCashTaxEvidence,
    policy: HistoricalLeaseCashTaxModelPolicy,
) -> HistoricalLeaseCashTaxDiagnostic:
    """Test declared D&A/tax simplifications against sourced historical data.

    The residual D&A is deliberately left unclassified: it is not asserted to
    be PPE depreciation, and no historical rate is promoted to a forward FCFF
    cash-tax assumption.
    """

    if not isinstance(evidence, HistoricalLeaseCashTaxEvidence):
        raise TypeError("evidence must be HistoricalLeaseCashTaxEvidence")
    if not isinstance(policy, HistoricalLeaseCashTaxModelPolicy):
        raise TypeError("policy must be HistoricalLeaseCashTaxModelPolicy")
    with localcontext() as decimal_context:
        decimal_context.prec = 50
        da_residual = (
            evidence.total_depreciation_and_amortization
            - evidence.finance_lease_rou_amortization
        )
        finance_lease_cash_paid = (
            evidence.finance_lease_operating_cash_paid
            + evidence.finance_lease_financing_cash_paid
        )
        cash_tax_minus_provision = evidence.cash_taxes_paid - evidence.income_tax_provision
        income_statement_interest_minus_note_interest = (
            evidence.finance_lease_income_statement_interest
            - evidence.finance_lease_interest
        )
    flags: list[str] = [
        "historical_observation_does_not_establish_forward_lease_cash_flows",
        "historical_cash_taxes_do_not_establish_forward_fcff_cash_tax_rate",
    ]
    if policy.total_da_booked_to_ppe_depreciation and evidence.finance_lease_rou_amortization:
        flags.append("total_da_includes_disclosed_finance_lease_rou_amortization")
    if (
        policy.cash_tax_rate_equals_tax_expense_rate
        and evidence.cash_taxes_paid != evidence.income_tax_provision
    ):
        flags.append("cash_tax_equals_provision_despite_historical_difference")
    if income_statement_interest_minus_note_interest != 0:
        flags.append("lease_note_to_income_statement_interest_bridge_unresolved")
    ratios = (
        _ratio(evidence.cash_taxes_paid, evidence.income_tax_provision),
        _ratio(evidence.cash_taxes_paid, evidence.pretax_income),
    )
    payload = {
        "schema_version": 1,
        "period_start": evidence.period_start.isoformat(),
        "period_end": evidence.period_end.isoformat(),
        "available_at": evidence.available_at.astimezone(UTC).isoformat(),
        "source_ids": evidence.source_ids,
        "unit": evidence.unit,
        "total_depreciation_and_amortization": str(evidence.total_depreciation_and_amortization),
        "finance_lease_rou_amortization": str(evidence.finance_lease_rou_amortization),
        "operating_lease_cost": str(evidence.operating_lease_cost),
        "finance_lease_interest": str(evidence.finance_lease_interest),
        "finance_lease_income_statement_interest": str(
            evidence.finance_lease_income_statement_interest
        ),
        "finance_lease_income_statement_interest_minus_note_interest": str(
            income_statement_interest_minus_note_interest
        ),
        "operating_lease_cash_paid": str(evidence.operating_lease_cash_paid),
        "finance_lease_operating_cash_paid": str(evidence.finance_lease_operating_cash_paid),
        "finance_lease_financing_cash_paid": str(evidence.finance_lease_financing_cash_paid),
        "income_tax_provision": str(evidence.income_tax_provision),
        "cash_taxes_paid": str(evidence.cash_taxes_paid),
        "pretax_income": str(evidence.pretax_income),
        "policy": {
            "total_da_booked_to_ppe_depreciation": policy.total_da_booked_to_ppe_depreciation,
            "cash_tax_rate_equals_tax_expense_rate": policy.cash_tax_rate_equals_tax_expense_rate,
        },
        "ratios": tuple(_decimal_or_state(value) for value in ratios),
        "modeling_flags": tuple(flags),
    }
    return HistoricalLeaseCashTaxDiagnostic(
        period_start=evidence.period_start,
        period_end=evidence.period_end,
        unit=evidence.unit,
        source_ids=evidence.source_ids,
        total_depreciation_and_amortization=evidence.total_depreciation_and_amortization,
        finance_lease_rou_amortization=evidence.finance_lease_rou_amortization,
        da_excluding_disclosed_finance_lease_rou_amortization=da_residual,
        operating_lease_cost=evidence.operating_lease_cost,
        finance_lease_interest=evidence.finance_lease_interest,
        finance_lease_income_statement_interest=evidence.finance_lease_income_statement_interest,
        finance_lease_income_statement_interest_minus_note_interest=(
            income_statement_interest_minus_note_interest
        ),
        operating_lease_cash_paid=evidence.operating_lease_cash_paid,
        finance_lease_cash_paid=finance_lease_cash_paid,
        income_tax_provision=evidence.income_tax_provision,
        cash_taxes_paid=evidence.cash_taxes_paid,
        cash_tax_minus_provision=cash_tax_minus_provision,
        cash_tax_to_provision=ratios[0],
        cash_tax_to_pretax_income=ratios[1],
        historical_evidence_state=KnowledgeState.KNOWN,
        forward_application_state=KnowledgeState.UNKNOWN,
        modeling_flags=tuple(flags),
        output_id=_output_id("m1_historical_lease_cash_tax", payload),
    )


@dataclass(frozen=True, slots=True)
class DatedStubEvidence:
    """Evidence for the part of a Core period that predates a valuation date."""

    evidence_id: str
    source_ids: tuple[str, ...]
    available_at: datetime
    last_disclosed_period_end: date
    realized_prevaluation_cash_flow: Decimal | KnowledgeState
    realized_prevaluation_period_start: date | None = None
    realized_prevaluation_period_end: date | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_id, str) or not self.evidence_id.strip():
            raise ValueError("evidence_id is required")
        _source_ids(self.source_ids, "dated stub evidence")
        _timestamp(self.available_at, "available_at")
        _date(self.last_disclosed_period_end, "last_disclosed_period_end")
        if isinstance(self.realized_prevaluation_cash_flow, Decimal):
            _finite(self.realized_prevaluation_cash_flow, "realized_prevaluation_cash_flow")
            if (
                self.realized_prevaluation_period_start is None
                or self.realized_prevaluation_period_end is None
            ):
                raise ValueError("observed prevaluation cash flow requires covered period")
            start = _date(
                self.realized_prevaluation_period_start,
                "realized_prevaluation_period_start",
            )
            end = _date(
                self.realized_prevaluation_period_end,
                "realized_prevaluation_period_end",
            )
            if start > end:
                raise ValueError("observed prevaluation cash-flow period is invalid")
        elif isinstance(self.realized_prevaluation_cash_flow, KnowledgeState):
            if self.realized_prevaluation_cash_flow not in {
                KnowledgeState.UNKNOWN,
                KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA,
                KnowledgeState.WITHHELD,
            }:
                raise ValueError("prevaluation cash flow state must represent unavailable cash flow")
            if (
                self.realized_prevaluation_period_start is not None
                or self.realized_prevaluation_period_end is not None
            ):
                raise ValueError("unavailable prevaluation cash flow cannot claim a covered period")
        else:
            raise TypeError("realized_prevaluation_cash_flow must be Decimal or KnowledgeState")


@dataclass(frozen=True, slots=True)
class DatedDcfStubBoundary:
    """Technical release boundary for a dated DCF whose first Core flow is partial."""

    parent_dcf_output_id: str
    first_core_period_id: str
    first_core_period_start: date
    first_core_period_end: date
    valuation_date: date
    last_disclosed_period_end: date
    prevaluation_period_start: date | None
    prevaluation_period_end: date | None
    prevaluation_days: int
    postvaluation_days: int
    realized_prevaluation_cash_flow: Decimal | None
    realized_prevaluation_cash_flow_state: KnowledgeState | None
    requires_explicit_stub_treatment: bool
    can_enter_downstream_valuation_eligibility: bool
    status: GateStatus
    failed_checks: tuple[str, ...]
    input_lineage: tuple[tuple[str, str], ...]
    release_consumable_enterprise_value: None
    output_id: str

    def as_dict(self) -> dict[str, object]:
        """Serialize a fail-closed boundary; it never exposes a release value."""

        return {
            "output_id": self.output_id,
            "parent_dcf_output_id": self.parent_dcf_output_id,
            "first_core_period_id": self.first_core_period_id,
            "first_core_period_start": self.first_core_period_start.isoformat(),
            "first_core_period_end": self.first_core_period_end.isoformat(),
            "valuation_date": self.valuation_date.isoformat(),
            "last_disclosed_period_end": self.last_disclosed_period_end.isoformat(),
            "prevaluation_period_start": (
                self.prevaluation_period_start.isoformat()
                if self.prevaluation_period_start is not None
                else None
            ),
            "prevaluation_period_end": (
                self.prevaluation_period_end.isoformat()
                if self.prevaluation_period_end is not None
                else None
            ),
            "prevaluation_days": self.prevaluation_days,
            "postvaluation_days": self.postvaluation_days,
            "realized_prevaluation_cash_flow": (
                str(self.realized_prevaluation_cash_flow)
                if self.realized_prevaluation_cash_flow is not None
                else None
            ),
            "realized_prevaluation_cash_flow_state": (
                self.realized_prevaluation_cash_flow_state.value
                if self.realized_prevaluation_cash_flow_state is not None
                else None
            ),
            "requires_explicit_stub_treatment": self.requires_explicit_stub_treatment,
            "can_enter_downstream_valuation_eligibility": (
                self.can_enter_downstream_valuation_eligibility
            ),
            "status": self.status.value,
            "failed_checks": self.failed_checks,
            "input_lineage": self.input_lineage,
            "release_consumable_enterprise_value": self.release_consumable_enterprise_value,
        }


def assess_dated_dcf_stub_boundary(
    dcf: DcfResult,
    *,
    first_core_period_id: str,
    first_core_period_start: date,
    first_core_period_end: date,
    evidence: DatedStubEvidence,
) -> DatedDcfStubBoundary:
    """Fail closed when a valuation date bisects an unresolved Core cash flow.

    A dated DCF may still retain conditional arithmetic for diagnosis.  This
    result is the separate contract a release adapter must consume: when a
    realized pre-valuation flow is unavailable, it exposes no numeric value for
    release use and blocks entry to downstream valuation eligibility.
    """

    if not isinstance(dcf, DcfResult):
        raise TypeError("dcf must be DcfResult")
    if dcf.discount_timing is not DiscountTiming.ACT_365_FIXED:
        raise ValueError("dated stub boundary requires ACT_365_FIXED DCF")
    if dcf.valuation_date is None or dcf.first_forecast_period_start is None:
        raise ValueError("dated DCF is missing valuation or first-period date")
    if dcf.information_cutoff is None:
        raise ValueError("dated DCF is missing information cutoff")
    _timestamp(dcf.information_cutoff, "DCF information_cutoff")
    if not isinstance(first_core_period_id, str) or not first_core_period_id.strip():
        raise ValueError("first_core_period_id is required")
    start = _date(first_core_period_start, "first_core_period_start")
    end = _date(first_core_period_end, "first_core_period_end")
    if start > end:
        raise ValueError("first Core period is invalid")
    if start != dcf.first_forecast_period_start:
        raise ValueError("first Core period start differs from DCF provenance")
    valuation_date = _date(dcf.valuation_date, "DCF valuation_date")
    if valuation_date > end:
        raise ValueError("valuation_date follows first Core period")
    if evidence.available_at > dcf.information_cutoff:
        raise ValueError("dated stub evidence is unavailable at DCF cutoff")
    if evidence.last_disclosed_period_end >= start:
        raise ValueError("last disclosed period overlaps first Core forecast period")
    if not dcf.period_year_fractions:
        raise ValueError("dated DCF is missing period year fractions")
    with localcontext() as decimal_context:
        decimal_context.prec = 50
        expected_fraction = Decimal((end - valuation_date).days) / Decimal(365)
    if dcf.period_year_fractions[0] != expected_fraction:
        raise ValueError("first Core period end differs from DCF timing")

    has_prevaluation_interval = valuation_date > start
    pre_start = start if has_prevaluation_interval else None
    pre_end = valuation_date - timedelta(days=1) if has_prevaluation_interval else None
    pre_days = (valuation_date - start).days if has_prevaluation_interval else 0
    # This is a calendar-day diagnostic, not the ACT/365 discount fraction.
    # If the Core period starts after the valuation date, do not count the
    # gap before that period as post-valuation Core days.
    post_days = (end - max(start, valuation_date)).days + 1
    if post_days <= 0:
        raise ValueError("dated DCF has no post-valuation first-period days")

    observed_flow: Decimal | None = None
    observed_state: KnowledgeState | None = None
    failed: tuple[str, ...] = ()
    if has_prevaluation_interval:
        if isinstance(evidence.realized_prevaluation_cash_flow, Decimal):
            if (
                evidence.realized_prevaluation_period_start != pre_start
                or evidence.realized_prevaluation_period_end != pre_end
            ):
                raise ValueError("observed prevaluation cash flow does not cover DCF stub")
            observed_flow = evidence.realized_prevaluation_cash_flow
        else:
            observed_state = evidence.realized_prevaluation_cash_flow
            failed = ("prevaluation_realized_cash_flow_unavailable",)
    passed = not failed
    status = GateStatus.NOT_EVALUATED if passed else GateStatus.WITHHELD
    lineage = (
        ("parent_dcf", dcf.output_id),
        ("stub_evidence", evidence.evidence_id),
        *((f"stub_source_{index}", source_id)
          for index, source_id in enumerate(evidence.source_ids, start=1)),
    )
    payload = {
        "schema_version": 1,
        "parent_dcf_output_id": dcf.output_id,
        "first_core_period_id": first_core_period_id,
        "first_core_period_start": start.isoformat(),
        "first_core_period_end": end.isoformat(),
        "valuation_date": valuation_date.isoformat(),
        "last_disclosed_period_end": evidence.last_disclosed_period_end.isoformat(),
        "prevaluation_days": pre_days,
        "postvaluation_days": post_days,
        "realized_prevaluation_cash_flow": (
            str(observed_flow) if observed_flow is not None else observed_state.value
            if observed_state is not None else None
        ),
        "evidence_id": evidence.evidence_id,
        "source_ids": evidence.source_ids,
        "failed_checks": failed,
    }
    return DatedDcfStubBoundary(
        parent_dcf_output_id=dcf.output_id,
        first_core_period_id=first_core_period_id,
        first_core_period_start=start,
        first_core_period_end=end,
        valuation_date=valuation_date,
        last_disclosed_period_end=evidence.last_disclosed_period_end,
        prevaluation_period_start=pre_start,
        prevaluation_period_end=pre_end,
        prevaluation_days=pre_days,
        postvaluation_days=post_days,
        realized_prevaluation_cash_flow=observed_flow,
        realized_prevaluation_cash_flow_state=observed_state,
        requires_explicit_stub_treatment=has_prevaluation_interval,
        can_enter_downstream_valuation_eligibility=passed,
        status=status,
        failed_checks=failed,
        input_lineage=lineage,
        release_consumable_enterprise_value=None,
        output_id=_output_id("m1_dated_dcf_stub_boundary", payload),
    )
