"""Synthetic known-answer and fail-closed tests for the M3 credit lens."""

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
from versioned_finance_core.modules.m3 import (
    CashStressSensitivity,
    CovenantDirection,
    CovenantTestability,
    CreditPeriodInput,
    ObligorCashPosition,
    assess_covenant,
    evaluate_credit_path,
    evaluate_obligor_cash,
    reverse_stress_cash_floor,
)


def _core(
    end: date, *, liquidity: Decimal | KnowledgeState,
    cfads: Decimal | KnowledgeState = Decimal(20),
    debt_service: Decimal | KnowledgeState = Decimal(-10),
    accounting_scope: AccountingScope = AccountingScope.STANDALONE,
    legal_entity_id: str | None = "obligor",
) -> CashInclusionResult:
    return CashInclusionResult(
        output_id=f"synthetic_core_{end}",
        case_id="synthetic_case",
        scope=ScopeRef("obligor_scope", accounting_scope, "bridge_1",
                       legal_entity_id, None, None),
        version_id="synthetic_v1",
        period=Period(end, end, "INSTANT"),
        currency="KRW",
        unit="KRW",
        views=tuple(
            CashViewTotal(view, value, (view.value,), (f"fact_{view.value}",), ())
            for view, value in (
                (CashView.CFADS, cfads),
                (CashView.DEBT_SERVICE, debt_service),
                (CashView.LIQUIDITY, liquidity),
            )
        ),
    )


def _opening(*, unavailable: Decimal | KnowledgeState = Decimal(20)):
    return evaluate_obligor_cash(ObligorCashPosition(
        legal_entity_id="obligor",
        group_cash=Decimal(1000),
        obligor_cash=Decimal(100),
        unavailable_cash=unavailable,
        group_source_id="group_disclosure",
        obligor_source_id="standalone_disclosure",
        exclusion_source_id="cash_access_review",
    ))


def _period(
    end: date, liquidity: Decimal | KnowledgeState, *,
    floor: Decimal | KnowledgeState = Decimal(50),
    drawable: Decimal | KnowledgeState = Decimal(10),
    cfads: Decimal | KnowledgeState = Decimal(20),
    debt_service: Decimal | KnowledgeState = Decimal(-10),
    accounting_scope: AccountingScope = AccountingScope.STANDALONE,
) -> CreditPeriodInput:
    return CreditPeriodInput(
        core_cash=_core(end, liquidity=liquidity, cfads=cfads,
                        debt_service=debt_service, accounting_scope=accounting_scope),
        operating_cash_floor=floor,
        committed_drawable=drawable,
        floor_basis_id="operating_floor_source",
        facility_basis_id="committed_drawable_source",
        liquidity_access_basis_id="accessibility_review",
    )


def test_group_cash_never_becomes_obligor_accessible_cash() -> None:
    result = _opening()
    assert result.group_cash_reference == Decimal(1000)
    assert result.obligor_cash == Decimal(100)
    assert result.accessible_cash == Decimal(80)


def test_unknown_exclusion_is_not_assumed_zero() -> None:
    assert _opening(unavailable=KnowledgeState.UNKNOWN).accessible_cash is KnowledgeState.UNKNOWN
    with pytest.raises(ValueError, match="exceeds obligor"):
        _opening(unavailable=Decimal(101))
    with pytest.raises(TypeError, match="Decimal"):
        evaluate_obligor_cash(ObligorCashPosition(
            "obligor", Decimal(1000), 100.0, Decimal(0),
            "group", "obligor", "exclusions",
        ))
    with pytest.raises(ValueError, match="source"):
        evaluate_obligor_cash(ObligorCashPosition(
            "obligor", KnowledgeState.UNKNOWN, Decimal(100), Decimal(0),
        ))


def test_credit_path_uses_core_signed_liquidity_once_and_keeps_facility_conditional() -> None:
    first = date(2027, 3, 31)
    second = date(2027, 6, 30)
    path = evaluate_credit_path(_opening(), (
        _period(first, Decimal(-20), cfads=Decimal(40), debt_service=Decimal(-30)),
        _period(second, Decimal(-25), cfads=Decimal(5), debt_service=Decimal(-20)),
    ))
    assert path.periods[0].closing_accessible_cash == Decimal(60)
    assert path.periods[0].model_dscr == Decimal(40) / Decimal(30)
    assert path.periods[1].closing_accessible_cash == Decimal(35)
    assert path.periods[1].pre_action_cash_gap == Decimal(15)
    assert path.periods[1].gap_after_committed_capacity == Decimal(5)
    assert path.cash_trough == Decimal(35)
    assert path.cash_trough_date == second
    assert path.first_cash_floor_failure_date == second


def test_credit_path_output_id_tracks_core_values_and_evidence() -> None:
    period = _period(date(2027, 3, 31), Decimal(-20))
    first = evaluate_credit_path(_opening(), (period,))
    assert first.output_id == evaluate_credit_path(_opening(), (period,)).output_id
    revised_source = evaluate_credit_path(
        _opening(), (replace(period, floor_basis_id="revised_floor_source"),),
    )
    revised_value = evaluate_credit_path(
        _opening(), (_period(date(2027, 3, 31), Decimal(-21)),),
    )
    assert first.output_id != revised_source.output_id
    assert first.output_id != revised_value.output_id


def test_large_obligor_cash_path_preserves_minor_unit() -> None:
    large = Decimal(10000000000000000000000000000000000000000)
    opening = evaluate_obligor_cash(ObligorCashPosition(
        legal_entity_id="obligor",
        group_cash=large,
        obligor_cash=large,
        unavailable_cash=Decimal(0),
        group_source_id="group_disclosure",
        obligor_source_id="standalone_disclosure",
        exclusion_source_id="cash_access_review",
    ))
    path = evaluate_credit_path(opening, (
        _period(date(2027, 3, 31), Decimal("0.01"), floor=large, drawable=Decimal(0)),
    ))
    assert path.periods[0].closing_accessible_cash == Decimal(
        "10000000000000000000000000000000000000000.01"
    )
    assert path.periods[0].pre_action_cash_gap == 0


def test_missing_core_cash_or_facility_preserves_unknown() -> None:
    first = date(2027, 3, 31)
    second = date(2027, 6, 30)
    path = evaluate_credit_path(_opening(), (
        _period(first, KnowledgeState.UNKNOWN),
        _period(second, Decimal(20)),
    ))
    assert path.periods[1].closing_accessible_cash is KnowledgeState.UNKNOWN
    assert path.cash_trough is KnowledgeState.UNKNOWN
    assert path.first_cash_floor_failure_date is KnowledgeState.UNKNOWN
    result = reverse_stress_cash_floor(path, (
        CashStressSensitivity(first, Decimal(1)),
        CashStressSensitivity(second, Decimal(1)),
    ), assumption_id="synthetic_shock")
    assert result.switching_value is KnowledgeState.WITHHELD

    facility_unknown = evaluate_credit_path(_opening(), (
        _period(first, Decimal(-50), drawable=KnowledgeState.UNKNOWN),
    ))
    assert facility_unknown.periods[0].pre_action_cash_gap == Decimal(20)
    assert facility_unknown.periods[0].gap_after_committed_capacity is KnowledgeState.UNKNOWN


def test_scope_order_and_debt_service_boundary_checks() -> None:
    first = date(2027, 3, 31)
    with pytest.raises(ValueError, match="consolidated"):
        evaluate_credit_path(_opening(), (_period(
            first, Decimal(0), accounting_scope=AccountingScope.CONSOLIDATED,
        ),))
    with pytest.raises(ValueError, match="ordered"):
        evaluate_credit_path(_opening(), (
            _period(first, Decimal(0)), _period(first, Decimal(0)),
        ))
    with pytest.raises(ValueError, match="signed cash outflow"):
        evaluate_credit_path(_opening(), (_period(
            first, Decimal(0), debt_service=Decimal(1),
        ),))
    assert evaluate_credit_path(_opening(), (_period(
        first, Decimal(0), debt_service=Decimal(0),
    ),)).periods[0].model_dscr is KnowledgeState.NM
    assert evaluate_credit_path(_opening(), (_period(
        first, Decimal(0), cfads=Decimal(-1),
    ),)).periods[0].model_dscr is KnowledgeState.NM


def test_reverse_stress_returns_exact_linear_switching_boundary() -> None:
    first = date(2027, 3, 31)
    second = date(2027, 6, 30)
    path = evaluate_credit_path(_opening(), (
        _period(first, Decimal(-10), floor=Decimal(40)),
        _period(second, Decimal(-10), floor=Decimal(40)),
    ))
    result = reverse_stress_cash_floor(path, (
        CashStressSensitivity(first, Decimal(10)),
        CashStressSensitivity(second, Decimal(20)),
    ), assumption_id="synthetic_shock")
    assert result.switching_value == Decimal(20) / Decimal(30)
    assert result.first_boundary_date == second
    assert result.tested_bracket == (Decimal(0), result.switching_value)
    assert result.monotonicity == "MONOTONE_NONINCREASING"

    no_exposure = reverse_stress_cash_floor(path, (
        CashStressSensitivity(first, Decimal(0)),
        CashStressSensitivity(second, Decimal(0)),
    ), assumption_id="synthetic_shock")
    assert no_exposure.switching_value is KnowledgeState.NOT_APPLICABLE
    with pytest.raises(ValueError, match="negative"):
        reverse_stress_cash_floor(path, (
            CashStressSensitivity(first, Decimal(-1)),
            CashStressSensitivity(second, Decimal(0)),
        ), assumption_id="synthetic_shock")


def test_covenant_headroom_requires_exact_public_definition() -> None:
    maximum = assess_covenant(
        testability=CovenantTestability.PUBLIC_RECALCULATION,
        actual=Decimal(4), threshold=Decimal(3),
        direction=CovenantDirection.MAXIMUM,
        definition_source_id="contract", component_source_ids=("debt", "ebitda"),
    )
    assert maximum.headroom == Decimal(-1)
    assert maximum.mathematical_threshold_crossed is True
    minimum = assess_covenant(
        testability=CovenantTestability.PUBLIC_RECALCULATION,
        actual=Decimal(4), threshold=Decimal(3),
        direction=CovenantDirection.MINIMUM,
        definition_source_id="contract", component_source_ids=("liquidity",),
    )
    assert minimum.headroom == Decimal(1)
    assert minimum.mathematical_threshold_crossed is False
    unsupported = assess_covenant(
        testability=CovenantTestability.ISSUER_REPORTED_COMPLIANT,
        actual=Decimal(4), threshold=Decimal(3),
        direction=CovenantDirection.MAXIMUM,
    )
    assert unsupported.headroom is KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA
    with pytest.raises(ValueError, match="definition and component evidence"):
        assess_covenant(
            testability=CovenantTestability.PUBLIC_RECALCULATION,
            actual=Decimal(4), threshold=Decimal(3),
            direction=CovenantDirection.MAXIMUM,
        )
