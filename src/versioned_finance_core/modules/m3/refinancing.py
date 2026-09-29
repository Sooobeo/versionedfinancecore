"""M3 maturity gap lens over a pinned credit path and Core facility snapshots.

The credit path already contains the Core LIQUIDITY cash change. A repayment
included in that view is added back *only to recover cash immediately before
that due payment*; it is not subtracted from closing cash again. Facilities
contribute only legally drawable capacity remaining after Core-booked draws.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from enum import StrEnum

from versioned_finance_core.contracts import KnowledgeState
from versioned_finance_core.financial_core.debt_facility import (
    DebtFacilityResult,
    FacilityEventType,
)
from versioned_finance_core.modules.m3.credit import CreditPathResult

Money = Decimal | KnowledgeState


def _money(value: Money, label: str) -> Money:
    if isinstance(value, KnowledgeState):
        if value is KnowledgeState.KNOWN:
            raise ValueError(f"{label}: KNOWN requires a Decimal amount")
        return value
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal or KnowledgeState")
    if not value.is_finite() or value < 0:
        raise ValueError(f"{label} must be finite and nonnegative")
    return value


def _text(value: Money) -> str:
    return value.value if isinstance(value, KnowledgeState) else str(value)


def _precision(values: Iterable[Decimal]) -> int:
    entries = tuple(values)
    return max(
        28,
        max((len(value.as_tuple().digits) + abs(value.as_tuple().exponent)
             for value in entries), default=0) + len(entries).bit_length() + 8,
    )


class MaturityCashTreatment(StrEnum):
    INCLUDED_IN_CORE_LIQUIDITY = "INCLUDED_IN_CORE_LIQUIDITY"
    NOT_YET_BOOKED = "NOT_YET_BOOKED"


@dataclass(frozen=True)
class MaturityObligation:
    obligation_id: str
    due_date: date
    legal_entity_id: str
    currency: str
    principal_due: Money
    evidence_id: str
    cash_treatment: MaturityCashTreatment
    treatment_basis_id: str
    core_facility_event_id: str = ""
    core_liquidity_output_id: str = ""


@dataclass(frozen=True)
class FundingCandidate:
    facility: DebtFacilityResult
    eligible_for_this_maturity: bool | KnowledgeState
    eligibility_basis_id: str


@dataclass(frozen=True)
class RefinancingResult:
    output_id: str
    knowledge_state: KnowledgeState
    credit_path_output_id: str
    due_date: date
    legal_entity_id: str
    currency: str
    unit: str
    gross_principal_due: Money
    cash_available_before_unbooked_funding: Money
    committed_undrawn_available: Money
    gap_before_new_funding: Money
    refinancing_gap: Money
    booked_draw_event_ids: tuple[str, ...]
    uncommitted_facility_ids: tuple[str, ...]
    evidence_or_assumption_ids: tuple[str, ...]
    limitation: str


def evaluate_refinancing_window(
    path: CreditPathResult,
    *,
    due_date: date,
    maturities: Iterable[MaturityObligation],
    facilities: Iterable[FundingCandidate],
    maturity_register_source_id: str,
    funding_register_source_id: str,
    maturity_register_complete: bool,
    funding_register_complete: bool,
) -> RefinancingResult:
    """Return a dated, obligor-specific refinancing gap or an explicit limit.

    A funding candidate must be committed in Core, legally drawable at the
    due-date snapshot, and separately eligible for this maturity. Capacity is
    never cash until a draw event enters the Core path. The result has no
    assumption of automatic extension, refinancing or third-party funding.
    """

    obligations = tuple(maturities)
    candidates = tuple(facilities)
    if type(maturity_register_complete) is not bool or type(funding_register_complete) is not bool:
        raise TypeError("register completeness flags must be boolean")
    matching_periods = tuple(row for row in path.periods if row.period_end == due_date)
    if len(matching_periods) > 1:
        raise ValueError("credit path has duplicate maturity dates")
    row = matching_periods[0] if matching_periods else None
    obligation_ids: set[str] = set()
    facility_ids: set[str] = set()
    evidence_ids = {
        source_id for source_id in (maturity_register_source_id, funding_register_source_id)
        if source_id
    }
    reasons: list[str] = []
    if not maturity_register_source_id:
        reasons.append("Maturity register source is unavailable.")
    if not funding_register_source_id:
        reasons.append("Funding register source is unavailable.")
    if row is None:
        reasons.append("No credit cash/floor timestep at the maturity date.")
    if not maturity_register_complete:
        reasons.append("Maturity register is incomplete.")
    if not funding_register_complete:
        reasons.append("Funding register is incomplete.")
    for obligation in obligations:
        if not obligation.obligation_id or obligation.obligation_id in obligation_ids:
            raise ValueError("maturity obligation IDs must be nonempty and unique")
        obligation_ids.add(obligation.obligation_id)
        if (obligation.due_date != due_date
                or obligation.legal_entity_id != path.legal_entity_id
                or obligation.currency != path.currency):
            raise ValueError("maturity must match date, obligor and currency")
        amount = _money(obligation.principal_due, "principal_due")
        if not obligation.evidence_id or not obligation.treatment_basis_id:
            reasons.append(f"Maturity {obligation.obligation_id} lacks source/basis evidence.")
        else:
            evidence_ids.update((obligation.evidence_id, obligation.treatment_basis_id))
        if isinstance(amount, KnowledgeState):
            reasons.append(f"Maturity {obligation.obligation_id} amount is unavailable.")
        if obligation.cash_treatment is MaturityCashTreatment.INCLUDED_IN_CORE_LIQUIDITY:
            if (row is None or not obligation.core_facility_event_id
                    or obligation.core_liquidity_output_id != row.core_output_id):
                reasons.append(
                    f"Maturity {obligation.obligation_id} lacks a pinned booked-payment link."
                )
        elif obligation.cash_treatment is MaturityCashTreatment.NOT_YET_BOOKED:
            if obligation.core_facility_event_id or obligation.core_liquidity_output_id:
                raise ValueError("unbooked maturity must not reference a booked Core cash event")
        else:
            raise ValueError("unsupported maturity cash treatment")
    booked_events: dict[str, list[tuple[FacilityEventType, Decimal, Decimal]]] = {}
    booked_draw_ids: list[str] = []
    uncommitted_ids: list[str] = []
    for candidate in candidates:
        facility = candidate.facility
        if facility.facility_id in facility_ids:
            raise ValueError("each facility can be a funding candidate only once")
        facility_ids.add(facility.facility_id)
        if (facility.legal_entity_id != path.legal_entity_id
                or facility.currency != path.currency or facility.unit != path.unit
                or facility.version_id != path.version_id):
            raise ValueError("facility must match credit path obligor, currency, unit and version")
        if facility.as_of_date != due_date:
            reasons.append(f"Facility {facility.facility_id} lacks a due-date snapshot.")
        if facility.committed and not candidate.eligibility_basis_id:
            reasons.append(f"Facility {facility.facility_id} lacks maturity-use evidence.")
        elif candidate.eligibility_basis_id:
            evidence_ids.add(candidate.eligibility_basis_id)
        evidence_ids.add(facility.contract_source_id)
        if facility.committed is False:
            uncommitted_ids.append(facility.facility_id)
        for event in facility.events:
            booked_events.setdefault(event.event_id, []).append(
                (event.event_type, event.cash_delta, event.face_delta)
            )
            if event.event_type is FacilityEventType.DRAW:
                booked_draw_ids.append(event.event_id)
        if isinstance(candidate.eligible_for_this_maturity, KnowledgeState):
            if facility.committed:
                reasons.append(f"Facility {facility.facility_id} maturity eligibility is unknown.")
        elif type(candidate.eligible_for_this_maturity) is not bool:
            raise TypeError("facility maturity eligibility must be boolean or KnowledgeState")
        if (facility.committed and candidate.eligible_for_this_maturity is True
                and isinstance(facility.closing.legally_drawable, KnowledgeState)):
            reasons.append(f"Facility {facility.facility_id} drawable amount is unavailable.")
    for obligation in obligations:
        matches = booked_events.get(obligation.core_facility_event_id, ())
        if obligation.cash_treatment is MaturityCashTreatment.INCLUDED_IN_CORE_LIQUIDITY:
            if len(matches) != 1 or matches[0][0] is not FacilityEventType.PRINCIPAL_REPAYMENT:
                reasons.append(
                    f"Maturity {obligation.obligation_id} has no unique Core repayment event."
                )
            elif (isinstance(obligation.principal_due, Decimal)
                  and (matches[0][1] != -obligation.principal_due
                       or matches[0][2] != -obligation.principal_due)):
                raise ValueError("booked Core repayment amount conflicts with maturity amount")
        elif obligation.obligation_id in booked_events:
            raise ValueError("unbooked maturity ID already occurs in Core facility events")
    if row is not None:
        if not isinstance(row.closing_accessible_cash, Decimal):
            reasons.append("Obligor accessible cash at maturity is unavailable.")
        if not isinstance(row.operating_cash_floor, Decimal):
            reasons.append("Evidence-backed operating cash floor is unavailable.")
    if not isinstance(path.cash_trough, Decimal):
        reasons.append("Credit path contains unresolved cash periods.")
    known = not reasons
    gross: Money = KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA
    available_cash: Money = KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA
    committed_available: Money = KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA
    pre_funding_gap: Money = KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA
    final_gap: Money = KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA
    if known:
        values = [row.closing_accessible_cash, row.operating_cash_floor]
        values.extend(obligation.principal_due for obligation in obligations)
        values.extend(
            candidate.facility.closing.legally_drawable
            for candidate in candidates
            if candidate.facility.committed and candidate.eligible_for_this_maturity
        )
        with localcontext() as context:
            context.prec = _precision(values)
            gross = sum((obligation.principal_due for obligation in obligations), Decimal(0))
            already_paid = sum((
                obligation.principal_due for obligation in obligations
                if obligation.cash_treatment is MaturityCashTreatment.INCLUDED_IN_CORE_LIQUIDITY
            ), Decimal(0))
            cash_before_due = row.closing_accessible_cash + already_paid
            available_cash = max(Decimal(0), cash_before_due - row.operating_cash_floor)
            committed_available = sum((
                candidate.facility.closing.legally_drawable
                for candidate in candidates
                if candidate.facility.committed and candidate.eligible_for_this_maturity
            ), Decimal(0))
            pre_funding_gap = max(Decimal(0), gross - available_cash)
            final_gap = max(Decimal(0), pre_funding_gap - committed_available)
    limitation = " ".join(reasons) if reasons else (
        "Model gap for the declared due-date cash path and sourced committed capacity; "
        "funding draw has not been booked or priced."
    )
    identity = {
        "formula": "maturity_refinancing_window_v1",
        "credit_path_output_id": path.output_id,
        "due_date": due_date.isoformat(),
        "legal_entity_id": path.legal_entity_id,
        "currency": path.currency,
        "unit": path.unit,
        "registers": (
            maturity_register_source_id, maturity_register_complete,
            funding_register_source_id, funding_register_complete,
        ),
        "maturities": [
            (
                obligation.obligation_id, _text(obligation.principal_due),
                obligation.evidence_id, obligation.cash_treatment.value,
                obligation.treatment_basis_id, obligation.core_facility_event_id,
                obligation.core_liquidity_output_id,
            )
            for obligation in sorted(obligations, key=lambda item: item.obligation_id)
        ],
        "facilities": [
            (
                candidate.facility.output_id, candidate.facility.facility_id,
                candidate.facility.committed,
                _text(candidate.facility.closing.legally_drawable),
                candidate.eligible_for_this_maturity.value
                if isinstance(candidate.eligible_for_this_maturity, KnowledgeState)
                else candidate.eligible_for_this_maturity,
                candidate.eligibility_basis_id,
            )
            for candidate in sorted(candidates, key=lambda item: item.facility.facility_id)
        ],
        "outputs": tuple(_text(value) for value in (
            gross, available_cash, committed_available, pre_funding_gap, final_gap,
        )),
        "limitation": limitation,
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return RefinancingResult(
        output_id=f"refinancing_{digest}",
        knowledge_state=(KnowledgeState.KNOWN if known
                         else KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA),
        credit_path_output_id=path.output_id,
        due_date=due_date,
        legal_entity_id=path.legal_entity_id,
        currency=path.currency,
        unit=path.unit,
        gross_principal_due=gross,
        cash_available_before_unbooked_funding=available_cash,
        committed_undrawn_available=committed_available,
        gap_before_new_funding=pre_funding_gap,
        refinancing_gap=final_gap,
        booked_draw_event_ids=tuple(sorted(booked_draw_ids)),
        uncommitted_facility_ids=tuple(sorted(uncommitted_ids)),
        evidence_or_assumption_ids=tuple(sorted(evidence_ids)),
        limitation=limitation,
    )
