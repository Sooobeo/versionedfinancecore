from decimal import Decimal

from versioned_finance_core.contracts import GateStatus
from versioned_finance_core.modules.m1 import variance_residual
from versioned_finance_core.modules.m2 import incremental_cash_flow
from versioned_finance_core.modules.m3 import ending_accessible_cash, refinancing_gap
from versioned_finance_core.validation import GateResult, release_allowed


def test_m1_variance_keeps_unexplained_residual() -> None:
    assert variance_residual(30, [10, 15]) == Decimal(5)


def test_m2_uses_option_less_status_quo() -> None:
    assert incremental_cash_flow(125, 100) == Decimal(25)


def test_m3_liquidity_and_refinancing_gap() -> None:
    assert ending_accessible_cash(40, [25, 20], [8, 12]) == Decimal(65)
    assert refinancing_gap(100, [40, 35]) == Decimal(25)
    assert refinancing_gap(100, [110]) == Decimal(0)


def test_release_gates_are_non_compensatory() -> None:
    passing = [
        GateResult("A", GateStatus.PASS),
        GateResult("B", GateStatus.NOT_APPLICABLE),
    ]
    failing = passing + [GateResult("C", GateStatus.FAIL)]
    assert release_allowed(passing)
    assert not release_allowed(failing)
    assert not release_allowed([])

