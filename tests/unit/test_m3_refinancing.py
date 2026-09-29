"""Synthetic due-date gap tests; no real obligor or facility evidence is used."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from versioned_finance_core.contracts import AccountingScope, KnowledgeState, Period, ScopeRef
from versioned_finance_core.financial_core.cash_components import (
    CashInclusionResult,
    CashView,
    CashViewTotal,
)
from versioned_finance_core.financial_core.debt_facility import (
    FacilityContract,
    FacilityEvent,
    FacilityEventType,
    FacilityOpening,
    evaluate_debt_facility,
)
from versioned_finance_core.modules.m3 import (
    CreditPeriodInput,
    FundingCandidate,
    MaturityCashTreatment,
    MaturityObligation,
    ObligorCashPosition,
    evaluate_credit_path,
    evaluate_obligor_cash,
    evaluate_refinancing_window,
)

DUE = date(2027, 6, 30)
OPEN = date(2026, 12, 31)


def _credit_path(
    liquidity_change: Decimal | KnowledgeState = Decimal(-60),
    floor: Decimal | KnowledgeState = Decimal(50),
    *, end: date = DUE,
):
    core = CashInclusionResult(
        output_id="synthetic_liquidity_output",
        case_id="synthetic_case",
        scope=ScopeRef("obligor_scope", AccountingScope.STANDALONE,
                       "synthetic_bridge", "synthetic_obligor", None, None),
        version_id="synthetic_v1",
        period=Period(end, end, "INSTANT"),
        currency="KRW", unit="KRW",
        views=tuple(
            CashViewTotal(view, amount, (view.value,), (f"fact_{view.value}",), ())
            for view, amount in (
                (CashView.CFADS, Decimal(20)),
                (CashView.DEBT_SERVICE, Decimal(-80)),
                (CashView.LIQUIDITY, liquidity_change),
            )
        ),
    )
    opening = evaluate_obligor_cash(ObligorCashPosition(
        "synthetic_obligor", Decimal(120), Decimal(90), Decimal(0),
        "group", "obligor", "access_review",
    ))
    return evaluate_credit_path(opening, (CreditPeriodInput(
        core, floor, Decimal(0),
        "floor_basis", "not_drawn_in_credit_path", "access_review",
    ),))


def _facility(
    facility_id: str, *, committed: bool, commitment: int,
    opening_face: int, event_id: str, kind: FacilityEventType,
    event_amount: int,
):
    contract = FacilityContract(
        facility_id, "synthetic_obligor", "KRW", "KRW",
        Decimal(commitment), committed, date(2027, 12, 31),
        KnowledgeState.NOT_APPLICABLE, True,
        f"contract_{facility_id}", f"base_{facility_id}", f"conditions_{facility_id}",
    )
    opening = FacilityOpening(
        OPEN, Decimal(100), Decimal(opening_face), Decimal(opening_face),
        Decimal(0), f"opening_{facility_id}",
    )
    signed = Decimal(event_amount if kind is FacilityEventType.DRAW else -event_amount)
    event = FacilityEvent(
        event_id, DUE, 1, kind, "synthetic_obligor", "KRW",
        signed, signed, signed, Decimal(0), f"source_{event_id}",
        kind is FacilityEventType.PRINCIPAL_REPAYMENT,
    )
    return evaluate_debt_facility(
        contract, opening, (event,), as_of_date=DUE,
        version_id="synthetic_v1", event_register_source_id=f"register_{facility_id}",
        event_register_complete=True, other_cash_change=Decimal(0),
        other_cash_source_id=f"other_cash_{facility_id}",
        reported_closing_cash=Decimal(100) + signed,
        reported_closing_face=Decimal(opening_face) + signed,
        reported_closing_carrying=Decimal(opening_face) + signed,
        reported_closing_source_id=f"closing_{facility_id}",
    )


def _maturity(*, included: bool = True, amount: Decimal | KnowledgeState = Decimal(80)):
    return MaturityObligation(
        obligation_id="synthetic_principal_due",
        due_date=DUE,
        legal_entity_id="synthetic_obligor",
        currency="KRW",
        principal_due=amount,
        evidence_id="maturity_source",
        cash_treatment=(MaturityCashTreatment.INCLUDED_IN_CORE_LIQUIDITY
                        if included else MaturityCashTreatment.NOT_YET_BOOKED),
        treatment_basis_id="cash_inclusion_review",
        core_facility_event_id="repay_80" if included else "",
        core_liquidity_output_id="synthetic_liquidity_output" if included else "",
    )


def _evaluate(
    *, path=None, maturities=None, candidates=None,
    maturity_register_complete: bool = True,
    funding_register_complete: bool = True,
    maturity_register_source_id: str = "complete_maturity_register",
    funding_register_source_id: str = "complete_funding_register",
):
    obligation = _facility(
        "obligation_line", committed=False, commitment=100, opening_face=80,
        event_id="repay_80", kind=FacilityEventType.PRINCIPAL_REPAYMENT,
        event_amount=80,
    )
    funding = _facility(
        "funding_line", committed=True, commitment=50, opening_face=20,
        event_id="draw_20", kind=FacilityEventType.DRAW, event_amount=20,
    )
    return evaluate_refinancing_window(
        _credit_path() if path is None else path,
        due_date=DUE,
        maturities=(_maturity(),) if maturities is None else maturities,
        facilities=(FundingCandidate(obligation, False, "uncommitted_exclusion"),
                    FundingCandidate(funding, True, "eligible_committed_source"))
        if candidates is None else candidates,
        maturity_register_source_id=maturity_register_source_id,
        funding_register_source_id=funding_register_source_id,
        maturity_register_complete=maturity_register_complete,
        funding_register_complete=funding_register_complete,
    )


def test_booked_repayment_is_not_subtracted_twice_and_booked_draw_is_not_readded() -> None:
    result = _evaluate()
    assert result.knowledge_state is KnowledgeState.KNOWN
    assert result.gross_principal_due == Decimal(80)
    assert result.cash_available_before_unbooked_funding == Decimal(60)
    assert result.gap_before_new_funding == Decimal(20)
    assert result.committed_undrawn_available == Decimal(10)
    assert result.refinancing_gap == Decimal(10)
    assert result.booked_draw_event_ids == ("draw_20",)
    assert result.uncommitted_facility_ids == ("obligation_line",)
    assert result.output_id == _evaluate().output_id


def test_unbooked_maturity_uses_pre_payment_cash_and_remaining_committed_capacity() -> None:
    path = _credit_path(Decimal(0))  # 90 cash before the future principal payment
    result = _evaluate(
        path=path,
        maturities=(_maturity(included=False),),
        candidates=(_evaluate_candidates()[1],),
    )
    assert result.cash_available_before_unbooked_funding == Decimal(40)
    assert result.gap_before_new_funding == Decimal(40)
    assert result.committed_undrawn_available == Decimal(10)
    assert result.refinancing_gap == Decimal(30)


def _evaluate_candidates():
    obligation = _facility(
        "obligation_line", committed=False, commitment=100, opening_face=80,
        event_id="repay_80", kind=FacilityEventType.PRINCIPAL_REPAYMENT,
        event_amount=80,
    )
    funding = _facility(
        "funding_line", committed=True, commitment=50, opening_face=20,
        event_id="draw_20", kind=FacilityEventType.DRAW, event_amount=20,
    )
    return (
        FundingCandidate(obligation, False, "uncommitted_exclusion"),
        FundingCandidate(funding, True, "eligible_committed_source"),
    )


def test_uncommitted_or_restricted_facility_is_excluded_from_funding() -> None:
    obligation, funding = _evaluate_candidates()
    only_uncommitted = _evaluate(candidates=(obligation,))
    assert only_uncommitted.committed_undrawn_available == Decimal(0)
    assert only_uncommitted.refinancing_gap == Decimal(20)
    restricted = _evaluate(candidates=(obligation, replace(
        funding, eligible_for_this_maturity=False,
        eligibility_basis_id="restricted_use_contract",
    )))
    assert restricted.committed_undrawn_available == Decimal(0)
    assert restricted.refinancing_gap == Decimal(20)


def test_missing_maturity_cash_floor_source_or_register_withholds_numeric_gap() -> None:
    for result in (
        _evaluate(maturities=(_maturity(amount=KnowledgeState.UNKNOWN),)),
        _evaluate(path=_credit_path(liquidity_change=KnowledgeState.UNKNOWN)),
        _evaluate(path=_credit_path(floor=KnowledgeState.UNKNOWN)),
        _evaluate(maturities=(replace(_maturity(), evidence_id=""),)),
        _evaluate(maturity_register_complete=False),
        _evaluate(funding_register_complete=False),
        _evaluate(maturity_register_source_id=""),
        _evaluate(funding_register_source_id=""),
        _evaluate(path=_credit_path(end=date(2027, 3, 31))),
    ):
        assert result.knowledge_state is KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA
        assert result.refinancing_gap is KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA


def test_maturity_amount_must_match_pinned_core_repayment() -> None:
    with pytest.raises(ValueError, match="conflicts with maturity amount"):
        _evaluate(maturities=(_maturity(amount=Decimal(79)),))
    with pytest.raises(ValueError, match="unbooked maturity ID already occurs"):
        _evaluate(maturities=(replace(
            _maturity(included=False), obligation_id="repay_80",
        ),))


def test_funding_evidence_change_changes_output_identity() -> None:
    obligation, funding = _evaluate_candidates()
    first = _evaluate(candidates=(obligation, funding))
    revised = _evaluate(candidates=(obligation, replace(
        funding, eligibility_basis_id="new_facility_review",
    )))
    assert first.output_id != revised.output_id
