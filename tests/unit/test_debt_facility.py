"""Synthetic facility event identities and fail-closed availability checks."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from versioned_finance_core.contracts import KnowledgeState
from versioned_finance_core.financial_core.debt_facility import (
    FacilityContract,
    FacilityEvent,
    FacilityEventType,
    FacilityOpening,
    evaluate_debt_facility,
)

OPEN = date(2026, 12, 31)
CUTOFF = date(2027, 9, 30)


def _contract(**changes: object) -> FacilityContract:
    default = FacilityContract(
        "synthetic_rcf", "synthetic_obligor", "KRW", "KRW",
        Decimal(200), True, date(2027, 12, 31), Decimal(180), True,
        "contract_source", "borrowing_base_source", "draw_conditions_source",
    )
    return replace(default, **changes)


def _opening(**changes: object) -> FacilityOpening:
    default = FacilityOpening(
        OPEN, Decimal(50), Decimal(20), Decimal(19), Decimal(10),
        "opening_balance_source",
    )
    return replace(default, **changes)


def _event(
    event_id: str, at: date, sequence: int, kind: FacilityEventType,
    cash: str, face: str = "0", carrying: str = "0", lc: str = "0",
    **changes: object,
) -> FacilityEvent:
    default = FacilityEvent(
        event_id, at, sequence, kind, "synthetic_obligor", "KRW",
        Decimal(cash), Decimal(face), Decimal(carrying), Decimal(lc),
        f"source_{event_id}", False,
    )
    return replace(default, **changes)


def _events() -> tuple[FacilityEvent, ...]:
    return (
        _event("draw", date(2027, 3, 1), 1, FacilityEventType.DRAW,
               "98", "100", "98"),
        _event("lc", date(2027, 4, 1), 1, FacilityEventType.LC_USAGE_CHANGE,
               "0", lc="20"),
        _event("interest", date(2027, 6, 1), 1, FacilityEventType.CASH_INTEREST,
               "-5"),
        _event("repay", date(2027, 7, 1), 1, FacilityEventType.PRINCIPAL_REPAYMENT,
               "-40", "-40", "-39"),
        _event("fee", date(2027, 8, 1), 1, FacilityEventType.FACILITY_FEE,
               "-2", carrying="-2"),
        _event("amortization", date(2027, 9, 1), 1,
               FacilityEventType.CARRYING_ADJUSTMENT, "0", carrying="1"),
    )


def _evaluate(
    events: tuple[FacilityEvent, ...] | None = None,
    *, contract: FacilityContract | None = None,
    opening: FacilityOpening | None = None,
    reported_cash: Decimal | KnowledgeState = Decimal(116),
    reported_face: Decimal | KnowledgeState = Decimal(80),
    reported_carrying: Decimal | KnowledgeState = Decimal(77),
):
    return evaluate_debt_facility(
        contract or _contract(), opening or _opening(),
        _events() if events is None else events,
        as_of_date=CUTOFF, version_id="synthetic_v1",
        event_register_source_id="complete_synthetic_register",
        event_register_complete=True,
        other_cash_change=Decimal(15),
        other_cash_source_id="core_other_cash_excluding_facility_events",
        reported_closing_cash=reported_cash,
        reported_closing_face=reported_face,
        reported_closing_carrying=reported_carrying,
        reported_closing_source_id="reported_closing_source",
    )


def test_known_answer_draw_repayment_interest_fee_and_lc_change() -> None:
    result = _evaluate()
    assert result.opening.nominal_undrawn == Decimal(170)
    assert result.opening.legally_drawable == Decimal(150)
    assert result.events[0].state.debt_face == Decimal(120)
    assert result.events[0].state.cash == Decimal(148)
    assert result.events[0].state.legally_drawable == Decimal(50)
    assert result.events[1].state.legally_drawable == Decimal(30)
    assert result.closing.cash == Decimal(116)
    assert result.closing.debt_face == Decimal(80)
    assert result.closing.debt_carrying == Decimal(77)
    assert result.closing.lc_usage == Decimal(30)
    assert result.closing.nominal_undrawn == Decimal(90)
    assert result.closing.legally_drawable == Decimal(70)
    assert result.facility_cash_change == Decimal(51)
    assert result.cash_rollforward_residual == Decimal(0)
    assert result.debt_face_rollforward_residual == Decimal(0)
    assert result.debt_carrying_residual == Decimal(0)


def test_input_order_does_not_change_content_id_but_source_does() -> None:
    first = _evaluate()
    reordered = _evaluate(tuple(reversed(_events())))
    assert first.output_id == reordered.output_id
    changed = list(_events())
    changed[0] = replace(changed[0], source_or_assumption_id="revised_draw_source")
    assert first.output_id != _evaluate(tuple(changed)).output_id


def test_uncommitted_line_is_not_eligible_funding_but_settled_draw_can_be_recorded() -> None:
    contract = _contract(committed=False)
    with pytest.raises(ValueError, match="exceeds legally drawable"):
        _evaluate((_events()[0],), contract=contract)
    settled = replace(_events()[0], settled=True)
    result = _evaluate((settled,), contract=contract,
                       reported_cash=Decimal(163), reported_face=Decimal(120),
                       reported_carrying=Decimal(117))
    assert result.closing.nominal_undrawn == Decimal(70)
    assert result.closing.legally_drawable == Decimal(0)


def test_unknown_conditions_or_borrowing_base_refuse_projected_draw() -> None:
    unknown_conditions = _contract(draw_conditions_met=KnowledgeState.UNKNOWN)
    with pytest.raises(ValueError, match="known legal availability"):
        _evaluate((_events()[0],), contract=unknown_conditions)
    unknown_base = _contract(borrowing_base_limit=KnowledgeState.UNKNOWN)
    with pytest.raises(ValueError, match="known legal availability"):
        _evaluate((_events()[0],), contract=unknown_base)
    no_base = _contract(borrowing_base_limit=KnowledgeState.NOT_APPLICABLE)
    result = _evaluate((), contract=no_base,
                       reported_cash=Decimal(65), reported_face=Decimal(20),
                       reported_carrying=Decimal(19))
    assert result.closing.legally_drawable == Decimal(170)


def test_unknown_reported_balances_do_not_create_false_zero_residual() -> None:
    result = _evaluate(reported_cash=KnowledgeState.UNKNOWN,
                       reported_face=KnowledgeState.UNKNOWN,
                       reported_carrying=KnowledgeState.UNKNOWN)
    assert result.closing.cash == Decimal(116)
    assert result.cash_rollforward_residual is KnowledgeState.UNKNOWN
    assert result.debt_face_rollforward_residual is KnowledgeState.UNKNOWN
    assert result.debt_carrying_residual is KnowledgeState.UNKNOWN


def test_rejects_invalid_scope_dates_duplicates_and_incomplete_register() -> None:
    event = _events()[0]
    with pytest.raises(ValueError, match="legal entity and currency"):
        _evaluate((replace(event, currency="USD"),))
    with pytest.raises(ValueError, match="cutoff"):
        _evaluate((replace(event, event_at=date(2028, 1, 1)),))
    with pytest.raises(ValueError, match="unique"):
        _evaluate((event, replace(event, event_id="other")))
    with pytest.raises(ValueError, match="incomplete event register"):
        evaluate_debt_facility(
            _contract(), _opening(), (), as_of_date=CUTOFF,
            version_id="synthetic_v1", event_register_source_id="register",
            event_register_complete=False, other_cash_change=Decimal(0),
            other_cash_source_id="core_other", reported_closing_cash=Decimal(50),
            reported_closing_face=Decimal(20),
            reported_closing_carrying=Decimal(19),
            reported_closing_source_id="reported",
        )


def test_rejects_overdraw_and_invalid_event_cash_debt_symmetry() -> None:
    with pytest.raises(ValueError, match="exceeds legally drawable"):
        _evaluate((_event("huge_draw", date(2027, 3, 1), 1,
                          FacilityEventType.DRAW, "151", "151", "151"),))
    with pytest.raises(ValueError, match="principal repayment cash"):
        _evaluate((_event("bad_repay", date(2027, 3, 1), 1,
                          FacilityEventType.PRINCIPAL_REPAYMENT,
                          "-9", "-10", "-10"),))
    with pytest.raises(ValueError, match="cannot become negative"):
        _evaluate((_event("too_much_repay", date(2027, 3, 1), 1,
                          FacilityEventType.PRINCIPAL_REPAYMENT,
                          "-21", "-21", "-19"),))


def test_large_decimal_roll_forward_is_not_rounded_internally() -> None:
    large = Decimal(10) ** 39
    result = _evaluate(
        (_event("tiny_interest", date(2027, 3, 1), 1,
                FacilityEventType.CASH_INTEREST, "-0.0000000001"),),
        opening=_opening(cash=large),
        reported_cash=Decimal("1000000000000000000000000000000000000014.9999999999"),
        reported_face=Decimal(20), reported_carrying=Decimal(19),
    )
    assert result.cash_rollforward_residual == Decimal(0)
    assert result.closing.cash == Decimal("1000000000000000000000000000000000000014.9999999999")
