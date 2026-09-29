"""Obligor-specific credit lens over pinned, canonical Core cash outputs.

The LIQUIDITY Core view is a *signed* cash change that already includes any
cash debt service flagged by the case. M3 never subtracts DEBT_SERVICE again.
An undrawn facility is shown as conditional capacity, never booked as cash or
debt by this module; a draw must first enter the shared Core cash/debt path.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from versioned_finance_core.contracts import AccountingScope, KnowledgeState
from versioned_finance_core.financial_core.cash_components import CashInclusionResult, CashView
from versioned_finance_core.financial_core.identities import _exact_sum

Money = Decimal | KnowledgeState


def _text(value: Money) -> str:
    return value.value if isinstance(value, KnowledgeState) else str(value)


def _money(value: Money, label: str) -> Money:
    if isinstance(value, KnowledgeState):
        if value is KnowledgeState.KNOWN:
            raise ValueError(f"{label}: KNOWN requires a Decimal amount")
        return value
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal or KnowledgeState")
    if not value.is_finite():
        raise ValueError(f"{label} must be finite")
    return value


def _unresolved(*values: Money) -> KnowledgeState:
    states = [value for value in values if isinstance(value, KnowledgeState)]
    if KnowledgeState.WITHHELD in states:
        return KnowledgeState.WITHHELD
    if KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA in states:
        return KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA
    return KnowledgeState.UNKNOWN


def _nonnegative(value: Money, label: str) -> Money:
    amount = _money(value, label)
    if isinstance(amount, Decimal) and amount < 0:
        raise ValueError(f"{label} cannot be negative")
    return amount


@dataclass(frozen=True)
class ObligorCashPosition:
    """Separate group disclosure from legally scoped obligor cash.

    ``unavailable_cash`` is the reviewed, non-overlapping total of restricted,
    pledged, trapped, customer or otherwise inaccessible cash in the obligor
    balance. Unknown exclusions are not silently set to zero.
    """

    legal_entity_id: str
    group_cash: Money
    obligor_cash: Money
    unavailable_cash: Money
    group_source_id: str = ""
    obligor_source_id: str = ""
    exclusion_source_id: str = ""


@dataclass(frozen=True)
class ObligorCashResult:
    legal_entity_id: str
    group_cash_reference: Money
    obligor_cash: Money
    unavailable_cash: Money
    accessible_cash: Money
    evidence_ids: tuple[str, ...]


def evaluate_obligor_cash(position: ObligorCashPosition) -> ObligorCashResult:
    """Subtract reviewed inaccessible obligor cash; never import group cash."""

    if not position.legal_entity_id:
        raise ValueError("legal_entity_id is required")
    group = _nonnegative(position.group_cash, "group_cash")
    obligor = _nonnegative(position.obligor_cash, "obligor_cash")
    unavailable = _nonnegative(position.unavailable_cash, "unavailable_cash")
    for amount, source_id, label in (
        (group, position.group_source_id, "group_cash"),
        (obligor, position.obligor_source_id, "obligor_cash"),
        (unavailable, position.exclusion_source_id, "unavailable_cash"),
    ):
        if isinstance(amount, Decimal) and not source_id:
            raise ValueError(f"{label} requires a source or reviewed assumption ID")
    if isinstance(obligor, Decimal) and isinstance(unavailable, Decimal):
        if unavailable > obligor:
            raise ValueError("unavailable cash exceeds obligor cash")
        accessible: Money = _exact_sum((obligor, unavailable.copy_negate()))
    else:
        accessible = _unresolved(obligor, unavailable)
    return ObligorCashResult(
        legal_entity_id=position.legal_entity_id,
        group_cash_reference=group,
        obligor_cash=obligor,
        unavailable_cash=unavailable,
        accessible_cash=accessible,
        evidence_ids=tuple(
            source_id for source_id in (
                position.group_source_id,
                position.obligor_source_id,
                position.exclusion_source_id,
            ) if source_id
        ),
    )


@dataclass(frozen=True)
class CreditPeriodInput:
    """A Core cash result plus case-evidenced M3 liquidity constraints.

    ``committed_drawable`` is remaining, conditional availability after drawn
    amounts, letters of credit, borrowing-base and draw conditions. It is not
    a booked inflow and must exclude amounts already in Core LIQUIDITY.
    """

    core_cash: CashInclusionResult
    operating_cash_floor: Money
    committed_drawable: Money
    floor_basis_id: str
    facility_basis_id: str
    liquidity_access_basis_id: str


@dataclass(frozen=True)
class CreditPeriodResult:
    period_end: date
    core_output_id: str
    opening_accessible_cash: Money
    closing_accessible_cash: Money
    cfads: Money
    mandatory_debt_service: Money
    model_dscr: Money
    operating_cash_floor: Money
    pre_action_cash_gap: Money
    committed_drawable: Money
    gap_after_committed_capacity: Money


@dataclass(frozen=True)
class CreditPathResult:
    """Credit lens over supplied timesteps; trough is among their period ends."""

    output_id: str
    case_id: str
    version_id: str
    legal_entity_id: str
    currency: str
    unit: str
    periods: tuple[CreditPeriodResult, ...]
    cash_trough: Money
    cash_trough_date: date | KnowledgeState
    first_cash_floor_failure_date: date | KnowledgeState | None


def _cash_gap(closing: Money, floor: Money) -> Money:
    if isinstance(closing, Decimal) and isinstance(floor, Decimal):
        return max(Decimal(0), _exact_sum((floor, closing.copy_negate())))
    return _unresolved(closing, floor)


def _model_dscr(cfads: Money, debt_service: Money) -> Money:
    if not isinstance(cfads, Decimal) or not isinstance(debt_service, Decimal):
        return _unresolved(cfads, debt_service)
    if debt_service > 0:
        raise ValueError("DEBT_SERVICE view must be zero or a signed cash outflow")
    if debt_service == 0 or cfads <= 0:
        return KnowledgeState.NM
    return cfads / -debt_service


def evaluate_credit_path(
    opening: ObligorCashResult, periods: Iterable[CreditPeriodInput]
) -> CreditPathResult:
    """Track pre-action obligor cash and separately show committed capacity.

    Core's LIQUIDITY total must already classify cash accessibility. Each
    period therefore needs an explicit review/basis ID. Unknown Core values,
    cash floors, or facility availability remain nonnumeric.
    """

    entries = tuple(periods)
    if not entries:
        raise ValueError("at least one credit period is required")
    first = entries[0].core_cash
    previous_end: date | None = None
    opening_cash = _money(opening.accessible_cash, "opening accessible cash")
    results: list[CreditPeriodResult] = []
    for entry in entries:
        core = entry.core_cash
        if core.case_id != first.case_id or core.version_id != first.version_id:
            raise ValueError("credit periods must share one pinned case and version")
        if core.currency != first.currency or core.unit != first.unit:
            raise ValueError("credit periods must share currency and unit")
        if core.scope != first.scope or core.scope.legal_entity_id != opening.legal_entity_id:
            raise ValueError("Core output must match the obligor legal entity and scope")
        if core.scope.accounting_scope is not AccountingScope.STANDALONE:
            raise ValueError("consolidated cash is not obligor accessible cash")
        if previous_end is not None and core.period.end <= previous_end:
            raise ValueError("credit periods must be strictly ordered and unique")
        previous_end = core.period.end
        if not all((entry.floor_basis_id, entry.facility_basis_id,
                    entry.liquidity_access_basis_id)):
            raise ValueError("cash floor, facility and accessibility basis IDs are required")
        floor = _nonnegative(entry.operating_cash_floor, "operating_cash_floor")
        drawable = _nonnegative(entry.committed_drawable, "committed_drawable")
        liquidity = _money(core.total_for(CashView.LIQUIDITY).value, "Core LIQUIDITY")
        cfads = _money(core.total_for(CashView.CFADS).value, "Core CFADS")
        debt_service = _money(
            core.total_for(CashView.DEBT_SERVICE).value, "Core DEBT_SERVICE"
        )
        if isinstance(opening_cash, Decimal) and isinstance(liquidity, Decimal):
            closing: Money = _exact_sum((opening_cash, liquidity))
        else:
            closing = _unresolved(opening_cash, liquidity)
        gap = _cash_gap(closing, floor)
        if isinstance(gap, Decimal) and isinstance(drawable, Decimal):
            after_capacity: Money = max(
                Decimal(0), _exact_sum((gap, drawable.copy_negate()))
            )
        else:
            after_capacity = _unresolved(gap, drawable)
        results.append(CreditPeriodResult(
            period_end=core.period.end,
            core_output_id=core.output_id,
            opening_accessible_cash=opening_cash,
            closing_accessible_cash=closing,
            cfads=cfads,
            mandatory_debt_service=debt_service,
            model_dscr=_model_dscr(cfads, debt_service),
            operating_cash_floor=floor,
            pre_action_cash_gap=gap,
            committed_drawable=drawable,
            gap_after_committed_capacity=after_capacity,
        ))
        opening_cash = closing
    if any(isinstance(row.closing_accessible_cash, KnowledgeState) for row in results):
        trough: Money = KnowledgeState.UNKNOWN
        trough_date: date | KnowledgeState = KnowledgeState.UNKNOWN
    else:
        low = min(results, key=lambda row: row.closing_accessible_cash)
        trough = low.closing_accessible_cash
        trough_date = low.period_end
    first_failure: date | KnowledgeState | None = None
    unknown_before_failure = False
    for row in results:
        if isinstance(row.pre_action_cash_gap, KnowledgeState):
            unknown_before_failure = True
        elif row.pre_action_cash_gap > 0:
            first_failure = (
                KnowledgeState.UNKNOWN if unknown_before_failure else row.period_end
            )
            break
    if first_failure is None and unknown_before_failure:
        first_failure = KnowledgeState.UNKNOWN
    identity = {
        "formula": "obligor_credit_path_v1",
        "case_id": first.case_id,
        "version_id": first.version_id,
        "legal_entity_id": opening.legal_entity_id,
        "currency": first.currency,
        "unit": first.unit,
        "opening": {
            "group_cash_reference": _text(opening.group_cash_reference),
            "obligor_cash": _text(opening.obligor_cash),
            "unavailable_cash": _text(opening.unavailable_cash),
            "accessible_cash": _text(opening.accessible_cash),
            "evidence_ids": opening.evidence_ids,
        },
        "periods": [
            {
                "core_output_id": entry.core_cash.output_id,
                "core_scope": entry.core_cash.scope.key(),
                "core_period": entry.core_cash.period.key(),
                "period_end": row.period_end.isoformat(),
                "core_views": {
                    view.value: _text(entry.core_cash.total_for(view).value)
                    for view in (CashView.CFADS, CashView.DEBT_SERVICE, CashView.LIQUIDITY)
                },
                "operating_cash_floor": _text(entry.operating_cash_floor),
                "committed_drawable": _text(entry.committed_drawable),
                "basis_ids": (
                    entry.floor_basis_id, entry.facility_basis_id,
                    entry.liquidity_access_basis_id,
                ),
                "closing_accessible_cash": _text(row.closing_accessible_cash),
                "model_dscr": _text(row.model_dscr),
                "pre_action_cash_gap": _text(row.pre_action_cash_gap),
                "gap_after_committed_capacity": _text(row.gap_after_committed_capacity),
            }
            for entry, row in zip(entries, results, strict=True)
        ],
        "cash_trough": _text(trough),
        "cash_trough_date": (
            trough_date.value if isinstance(trough_date, KnowledgeState)
            else trough_date.isoformat()
        ),
        "first_cash_floor_failure_date": (
            first_failure.value if isinstance(first_failure, KnowledgeState)
            else first_failure.isoformat() if first_failure is not None else None
        ),
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return CreditPathResult(
        output_id=f"credit_path_{digest}",
        case_id=first.case_id,
        version_id=first.version_id,
        legal_entity_id=opening.legal_entity_id,
        currency=first.currency,
        unit=first.unit,
        periods=tuple(results),
        cash_trough=trough,
        cash_trough_date=trough_date,
        first_cash_floor_failure_date=first_failure,
    )


@dataclass(frozen=True)
class CashStressSensitivity:
    period_end: date
    incremental_cash_outflow_per_unit: Decimal


@dataclass(frozen=True)
class ReverseStressResult:
    switching_value: Money
    first_boundary_date: date | KnowledgeState | None
    constraint: str
    assumption_id: str
    monotonicity: str
    tested_bracket: tuple[Decimal, Decimal] | None


def reverse_stress_cash_floor(
    path: CreditPathResult,
    sensitivities: Iterable[CashStressSensitivity],
    *, assumption_id: str,
) -> ReverseStressResult:
    """Solve one linear monotone shock against the evidenced cash floor.

    Sensitivities are *additional* cash outflows per unit shock, by period.
    Nonnegative sensitivities prove monotonic cash deterioration. The result
    is the equality boundary; an epsilon above it breaches the floor. Joint
    or nonlinear shocks require a separate path calculation and solver.
    """

    if not assumption_id:
        raise ValueError("a sourced stress assumption ID is required")
    shocks = tuple(sensitivities)
    if tuple(row.period_end for row in shocks) != tuple(row.period_end for row in path.periods):
        raise ValueError("stress sensitivities must match the credit path periods")
    for shock in shocks:
        _nonnegative(shock.incremental_cash_outflow_per_unit, "stress sensitivity")
    if any(
        not isinstance(row.closing_accessible_cash, Decimal)
        or not isinstance(row.operating_cash_floor, Decimal)
        for row in path.periods
    ):
        return ReverseStressResult(
            KnowledgeState.WITHHELD, KnowledgeState.UNKNOWN,
            "OPERATING_CASH_FLOOR", assumption_id, "NOT_TESTABLE", None,
        )
    cumulative = Decimal(0)
    candidates: list[tuple[Decimal, date]] = []
    for row, shock in zip(path.periods, shocks, strict=True):
        cumulative = _exact_sum((cumulative, shock.incremental_cash_outflow_per_unit))
        headroom = _exact_sum((
            row.closing_accessible_cash, row.operating_cash_floor.copy_negate()
        ))
        if headroom < 0:
            candidates.append((Decimal(0), row.period_end))
        elif cumulative > 0:
            candidates.append((headroom / cumulative, row.period_end))
    if not candidates:
        return ReverseStressResult(
            KnowledgeState.NOT_APPLICABLE, None,
            "OPERATING_CASH_FLOOR", assumption_id, "MONOTONE_NONINCREASING", None,
        )
    value, boundary_date = min(candidates, key=lambda item: (item[0], item[1]))
    return ReverseStressResult(
        value, boundary_date, "OPERATING_CASH_FLOOR", assumption_id,
        "MONOTONE_NONINCREASING", (Decimal(0), value),
    )


class CovenantTestability(StrEnum):
    PUBLIC_RECALCULATION = "PUBLIC_RECALCULATION"
    ANALYST_PROXY_ONLY = "ANALYST_PROXY_ONLY"
    ISSUER_REPORTED_COMPLIANT = "ISSUER_REPORTED_COMPLIANT"
    NOT_TESTABLE_FROM_PUBLIC_DATA = "NOT_TESTABLE_FROM_PUBLIC_DATA"
    PUBLICLY_NOT_OBSERVABLE = "PUBLICLY_NOT_OBSERVABLE"


class CovenantDirection(StrEnum):
    MAXIMUM = "MAXIMUM"
    MINIMUM = "MINIMUM"


@dataclass(frozen=True)
class CovenantAssessment:
    testability: CovenantTestability
    headroom: Money
    mathematical_threshold_crossed: bool | KnowledgeState
    definition_source_id: str
    component_source_ids: tuple[str, ...]


def assess_covenant(
    *, testability: CovenantTestability, actual: Money,
    threshold: Money, direction: CovenantDirection,
    definition_source_id: str = "", component_source_ids: Iterable[str] = (),
) -> CovenantAssessment:
    """Calculate mathematical headroom only for fully public exact definitions."""

    if not isinstance(testability, CovenantTestability):
        raise TypeError("testability must be a CovenantTestability enum")
    if not isinstance(direction, CovenantDirection):
        raise TypeError("direction must be a CovenantDirection enum")
    components = tuple(component_source_ids)
    actual = _money(actual, "covenant actual")
    threshold = _money(threshold, "covenant threshold")
    if testability is not CovenantTestability.PUBLIC_RECALCULATION:
        return CovenantAssessment(testability, KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA,
                                  KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA,
                                  definition_source_id, components)
    if not definition_source_id or not components:
        raise ValueError("public recalculation requires definition and component evidence")
    if not isinstance(actual, Decimal) or not isinstance(threshold, Decimal):
        return CovenantAssessment(testability, _unresolved(actual, threshold),
                                  KnowledgeState.UNKNOWN, definition_source_id, components)
    headroom = (
        _exact_sum((threshold, actual.copy_negate()))
        if direction is CovenantDirection.MAXIMUM
        else _exact_sum((actual, threshold.copy_negate()))
    )
    return CovenantAssessment(testability, headroom, headroom < 0,
                              definition_source_id, components)
