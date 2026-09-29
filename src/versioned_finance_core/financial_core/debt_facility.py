"""Pure, source-pinned facility event ledger for the canonical financial Core.

Commitment is not cash. Only a dated draw changes cash and debt face; its
carrying-value change is explicit. Interest and fees are separate cash events.
Reported closing balances are optional knowledge states, never inferred from
the modeled closing amounts for a spurious zero residual.
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
from versioned_finance_core.financial_core.identities import debt_face_rollforward_residual

Money = Decimal | KnowledgeState


def _money(value: Money, label: str, *, nonnegative: bool = False) -> Money:
    if isinstance(value, KnowledgeState):
        if value is KnowledgeState.KNOWN:
            raise ValueError(f"{label}: KNOWN requires a Decimal amount")
        return value
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal or KnowledgeState")
    if not value.is_finite():
        raise ValueError(f"{label} must be finite")
    if nonnegative and value < 0:
        raise ValueError(f"{label} cannot be negative")
    return value


def _decimal(value: Decimal, label: str) -> Decimal:
    amount = _money(value, label)
    if not isinstance(amount, Decimal):
        raise TypeError(f"{label} must have a known Decimal amount")
    return amount


def _missing(*values: Money) -> KnowledgeState:
    states = tuple(value for value in values if isinstance(value, KnowledgeState))
    if KnowledgeState.WITHHELD in states:
        return KnowledgeState.WITHHELD
    if KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA in states:
        return KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA
    return KnowledgeState.UNKNOWN


def _precision(values: Iterable[Money]) -> int:
    decimals = tuple(value for value in values if isinstance(value, Decimal))
    return max(
        28,
        max((len(value.as_tuple().digits) + abs(value.as_tuple().exponent)
             for value in decimals), default=0) + len(decimals).bit_length() + 8,
    )


def _text(value: Money) -> str:
    return value.value if isinstance(value, KnowledgeState) else str(value)


class FacilityEventType(StrEnum):
    DRAW = "DRAW"
    PRINCIPAL_REPAYMENT = "PRINCIPAL_REPAYMENT"
    CASH_INTEREST = "CASH_INTEREST"
    FACILITY_FEE = "FACILITY_FEE"
    LC_USAGE_CHANGE = "LC_USAGE_CHANGE"
    CARRYING_ADJUSTMENT = "CARRYING_ADJUSTMENT"


@dataclass(frozen=True)
class FacilityContract:
    facility_id: str
    legal_entity_id: str
    currency: str
    unit: str
    commitment: Money
    committed: bool
    expiry_date: date
    borrowing_base_limit: Money
    draw_conditions_met: bool | KnowledgeState
    source_id: str
    borrowing_base_source_id: str
    conditions_source_id: str


@dataclass(frozen=True)
class FacilityOpening:
    as_of_date: date
    cash: Money
    debt_face: Money
    debt_carrying: Money
    lc_usage: Money
    source_id: str


@dataclass(frozen=True)
class FacilityEvent:
    event_id: str
    event_at: date
    sequence: int
    event_type: FacilityEventType
    legal_entity_id: str
    currency: str
    cash_delta: Decimal
    face_delta: Decimal
    carrying_delta: Decimal
    lc_delta: Decimal
    source_or_assumption_id: str
    settled: bool


@dataclass(frozen=True)
class FacilityState:
    as_of_date: date
    cash: Money
    debt_face: Money
    debt_carrying: Money
    lc_usage: Money
    nominal_undrawn: Money
    legally_drawable: Money


@dataclass(frozen=True)
class FacilityEventState:
    event_id: str
    event_type: FacilityEventType
    cash_delta: Decimal
    face_delta: Decimal
    settled: bool
    state: FacilityState


@dataclass(frozen=True)
class DebtFacilityResult:
    output_id: str
    version_id: str
    facility_id: str
    committed: bool
    expiry_date: date
    contract_source_id: str
    legal_entity_id: str
    currency: str
    unit: str
    as_of_date: date
    opening: FacilityState
    events: tuple[FacilityEventState, ...]
    closing: FacilityState
    facility_cash_change: Decimal
    other_cash_change: Money
    cash_rollforward_residual: Money
    debt_face_rollforward_residual: Money
    debt_carrying_residual: Money
    evidence_or_assumption_ids: tuple[str, ...]


def _availability(
    contract: FacilityContract, face: Money, lc: Money, on_date: date,
) -> tuple[Money, Money]:
    commitment = contract.commitment
    if isinstance(commitment, Decimal) and isinstance(face, Decimal) and isinstance(lc, Decimal):
        nominal: Money = commitment - face - lc
        if nominal < 0:
            raise ValueError("drawn face plus LC usage exceeds facility commitment")
    else:
        nominal = _missing(commitment, face, lc)
    if not contract.committed or on_date > contract.expiry_date:
        return nominal, Decimal(0)
    if contract.draw_conditions_met is False:
        return nominal, Decimal(0)
    if contract.draw_conditions_met is not True:
        return nominal, KnowledgeState.UNKNOWN
    if not isinstance(nominal, Decimal):
        return nominal, nominal
    if nominal == 0:
        return nominal, Decimal(0)
    base = contract.borrowing_base_limit
    if base is KnowledgeState.NOT_APPLICABLE:
        return nominal, nominal
    if isinstance(base, KnowledgeState):
        return nominal, _missing(base)
    if not isinstance(face, Decimal) or not isinstance(lc, Decimal):
        return nominal, KnowledgeState.UNKNOWN
    return nominal, min(nominal, max(Decimal(0), base - face - lc))


def _state(
    contract: FacilityContract, at: date,
    cash: Money, face: Money, carrying: Money, lc: Money,
) -> FacilityState:
    nominal, drawable = _availability(contract, face, lc, at)
    return FacilityState(at, cash, face, carrying, lc, nominal, drawable)


def _validate_event(event: FacilityEvent, contract: FacilityContract) -> None:
    if not event.event_id or not event.source_or_assumption_id:
        raise ValueError("event ID and source or assumption ID are required")
    if event.legal_entity_id != contract.legal_entity_id or event.currency != contract.currency:
        raise ValueError("event legal entity and currency must match the facility")
    if isinstance(event.sequence, bool) or not isinstance(event.sequence, int) or event.sequence < 0:
        raise ValueError("event sequence must be a nonnegative integer")
    if type(event.settled) is not bool:
        raise TypeError("event settled flag must be boolean")
    cash = _decimal(event.cash_delta, "cash_delta")
    face = _decimal(event.face_delta, "face_delta")
    carrying = _decimal(event.carrying_delta, "carrying_delta")
    lc = _decimal(event.lc_delta, "lc_delta")
    kind = event.event_type
    if kind is FacilityEventType.DRAW:
        if not (face > 0 and 0 < cash <= face and carrying >= 0 and lc == 0):
            raise ValueError("draw needs positive face and net cash, with no LC change")
    elif kind is FacilityEventType.PRINCIPAL_REPAYMENT:
        if not (face < 0 and cash == face and carrying <= 0 and lc == 0):
            raise ValueError("principal repayment cash must equal the face reduction")
    elif kind is FacilityEventType.CASH_INTEREST:
        if not (cash < 0 and face == carrying == lc == 0):
            raise ValueError("cash interest changes cash only")
    elif kind is FacilityEventType.FACILITY_FEE:
        if not (cash < 0 and face == lc == 0 and carrying <= 0):
            raise ValueError("facility fee changes cash and optionally carrying value")
    elif kind is FacilityEventType.LC_USAGE_CHANGE:
        if not (lc != 0 and cash == face == carrying == 0):
            raise ValueError("LC usage changes only reserved commitment")
    elif kind is FacilityEventType.CARRYING_ADJUSTMENT:
        if not (carrying != 0 and cash == face == lc == 0):
            raise ValueError("carrying adjustment is noncash and does not change face")
    else:
        raise ValueError("unsupported facility event type")


def evaluate_debt_facility(
    contract: FacilityContract,
    opening: FacilityOpening,
    events: Iterable[FacilityEvent],
    *,
    as_of_date: date,
    version_id: str,
    event_register_source_id: str,
    event_register_complete: bool,
    other_cash_change: Money,
    other_cash_source_id: str,
    reported_closing_cash: Money,
    reported_closing_face: Money,
    reported_closing_carrying: Money,
    reported_closing_source_id: str,
) -> DebtFacilityResult:
    """Replay signed facility events and compare against reported balances.

    ``other_cash_change`` must exclude every facility event in this call. It
    represents all other cash movements, pinned to a Core output/source ID.
    Without a complete event register, numeric facility roll-forward is
    refused. Unknown reported balances yield unknown reconciliation residuals.
    """

    if not all((contract.facility_id, contract.legal_entity_id, contract.currency,
                contract.unit, contract.source_id, contract.borrowing_base_source_id,
                contract.conditions_source_id, opening.source_id, version_id,
                event_register_source_id, other_cash_source_id,
                reported_closing_source_id)):
        raise ValueError("facility, version and all source IDs are required")
    if type(contract.committed) is not bool:
        raise TypeError("committed flag must be boolean")
    if not isinstance(contract.draw_conditions_met, (bool, KnowledgeState)):
        raise TypeError("draw_conditions_met must be boolean or KnowledgeState")
    if contract.draw_conditions_met is KnowledgeState.KNOWN:
        raise ValueError("KNOWN draw conditions require a boolean")
    if not event_register_complete:
        raise ValueError("incomplete event register cannot produce numeric roll-forward")
    if opening.as_of_date > as_of_date:
        raise ValueError("opening date exceeds analysis date")
    commitment = _money(contract.commitment, "commitment", nonnegative=True)
    base = _money(contract.borrowing_base_limit, "borrowing_base_limit", nonnegative=True)
    if base is KnowledgeState.NM:
        raise ValueError("borrowing_base_limit cannot be NM")
    opening_cash = _money(opening.cash, "opening cash", nonnegative=True)
    opening_face = _money(opening.debt_face, "opening face", nonnegative=True)
    opening_carrying = _money(opening.debt_carrying, "opening carrying", nonnegative=True)
    opening_lc = _money(opening.lc_usage, "opening LC", nonnegative=True)
    other = _money(other_cash_change, "other_cash_change")
    reported_cash = _money(reported_closing_cash, "reported closing cash")
    reported_face = _money(reported_closing_face, "reported closing face", nonnegative=True)
    reported_carrying = _money(
        reported_closing_carrying, "reported closing carrying", nonnegative=True,
    )
    entries = tuple(events)
    ids: set[str] = set()
    keys: set[tuple[date, int]] = set()
    for event in entries:
        _validate_event(event, contract)
        if event.event_id in ids or (event.event_at, event.sequence) in keys:
            raise ValueError("event IDs and dated sequence keys must be unique")
        ids.add(event.event_id)
        keys.add((event.event_at, event.sequence))
        if not opening.as_of_date < event.event_at <= as_of_date:
            raise ValueError("event date must follow opening and meet analysis cutoff")
    ordered = tuple(sorted(entries, key=lambda item: (item.event_at, item.sequence)))
    inputs = (
        commitment, base, opening_cash, opening_face, opening_carrying, opening_lc,
        other, reported_cash, reported_face, reported_carrying,
        *(value for event in ordered for value in (
            event.cash_delta, event.face_delta, event.carrying_delta, event.lc_delta,
        )),
    )
    with localcontext() as context:
        context.prec = _precision(inputs)
        opening_state = _state(
            contract, opening.as_of_date,
            opening_cash, opening_face, opening_carrying, opening_lc,
        )
        cash, face, carrying, lc = (
            opening_cash, opening_face, opening_carrying, opening_lc,
        )
        event_states: list[FacilityEventState] = []
        total_cash = Decimal(0)
        total_draw = Decimal(0)
        total_repay = Decimal(0)
        for event in ordered:
            if event.event_type is FacilityEventType.DRAW and not event.settled:
                _, drawable = _availability(contract, face, lc, event.event_at)
                if not isinstance(drawable, Decimal):
                    raise ValueError("projected draw requires known legal availability")
                if event.face_delta > drawable:
                    raise ValueError("projected draw exceeds legally drawable capacity")
            total_cash += event.cash_delta
            if event.event_type is FacilityEventType.DRAW:
                total_draw += event.face_delta
            elif event.event_type is FacilityEventType.PRINCIPAL_REPAYMENT:
                total_repay -= event.face_delta
            cash = cash + event.cash_delta if isinstance(cash, Decimal) else cash
            face = face + event.face_delta if isinstance(face, Decimal) else face
            carrying = (
                carrying + event.carrying_delta
                if isinstance(carrying, Decimal) else carrying
            )
            lc = lc + event.lc_delta if isinstance(lc, Decimal) else lc
            for label, value in (("debt face", face), ("debt carrying", carrying),
                                 ("LC usage", lc)):
                if isinstance(value, Decimal) and value < 0:
                    raise ValueError(f"{label} cannot become negative")
            event_states.append(FacilityEventState(
                event.event_id, event.event_type, event.cash_delta,
                event.face_delta, event.settled,
                _state(contract, event.event_at, cash, face, carrying, lc),
            ))
        if isinstance(cash, Decimal) and isinstance(other, Decimal):
            cash += other
        else:
            cash = _missing(cash, other)
        closing = _state(contract, as_of_date, cash, face, carrying, lc)
        cash_residual: Money = (
            cash - reported_cash
            if isinstance(cash, Decimal) and isinstance(reported_cash, Decimal)
            else _missing(cash, reported_cash)
        )
        face_residual: Money = (
            debt_face_rollforward_residual(
                opening_face, total_draw, Decimal(0), total_repay, reported_face,
            )
            if isinstance(opening_face, Decimal) and isinstance(reported_face, Decimal)
            else _missing(opening_face, reported_face)
        )
        carrying_residual: Money = (
            carrying - reported_carrying
            if isinstance(carrying, Decimal) and isinstance(reported_carrying, Decimal)
            else _missing(carrying, reported_carrying)
        )
    identity = {
        "formula": "debt_facility_events_v1",
        "version_id": version_id,
        "facility": {
            "id": contract.facility_id,
            "legal_entity_id": contract.legal_entity_id,
            "currency": contract.currency,
            "unit": contract.unit,
            "commitment": _text(commitment),
            "committed": contract.committed,
            "expiry_date": contract.expiry_date.isoformat(),
            "borrowing_base_limit": _text(base),
            "draw_conditions_met": (
                contract.draw_conditions_met.value
                if isinstance(contract.draw_conditions_met, KnowledgeState)
                else contract.draw_conditions_met
            ),
            "source_ids": (contract.source_id, contract.borrowing_base_source_id,
                           contract.conditions_source_id),
        },
        "opening": {
            "at": opening.as_of_date.isoformat(),
            "cash": _text(opening_cash),
            "face": _text(opening_face),
            "carrying": _text(opening_carrying),
            "lc": _text(opening_lc),
            "source_id": opening.source_id,
        },
        "as_of_date": as_of_date.isoformat(),
        "event_register_source_id": event_register_source_id,
        "events": [
            {
                "id": event.event_id,
                "at": event.event_at.isoformat(),
                "sequence": event.sequence,
                "type": event.event_type.value,
                "cash_delta": str(event.cash_delta),
                "face_delta": str(event.face_delta),
                "carrying_delta": str(event.carrying_delta),
                "lc_delta": str(event.lc_delta),
                "source_or_assumption_id": event.source_or_assumption_id,
                "settled": event.settled,
            }
            for event in ordered
        ],
        "other_cash_change": _text(other),
        "other_cash_source_id": other_cash_source_id,
        "reported_closing": (
            _text(reported_cash), _text(reported_face), _text(reported_carrying),
            reported_closing_source_id,
        ),
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return DebtFacilityResult(
        output_id=f"debt_facility_{digest}",
        version_id=version_id,
        facility_id=contract.facility_id,
        committed=contract.committed,
        expiry_date=contract.expiry_date,
        contract_source_id=contract.source_id,
        legal_entity_id=contract.legal_entity_id,
        currency=contract.currency,
        unit=contract.unit,
        as_of_date=as_of_date,
        opening=opening_state,
        events=tuple(event_states),
        closing=closing,
        facility_cash_change=total_cash,
        other_cash_change=other,
        cash_rollforward_residual=cash_residual,
        debt_face_rollforward_residual=face_residual,
        debt_carrying_residual=carrying_residual,
        evidence_or_assumption_ids=tuple(sorted({
            contract.source_id, contract.borrowing_base_source_id,
            contract.conditions_source_id, opening.source_id,
            event_register_source_id, other_cash_source_id,
            reported_closing_source_id,
            *(event.source_or_assumption_id for event in ordered),
        })),
    )
