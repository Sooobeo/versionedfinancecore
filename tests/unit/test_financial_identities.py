import json
from decimal import Decimal
from pathlib import Path

from versioned_finance_core.financial_core import (
    cash_rollforward_residual,
    debt_face_rollforward_residual,
    sources_uses_residual,
)

FIXTURE = (
    Path(__file__).parents[1] / "fixtures" / "synthetic_known_answers" / "core_identities.json"
)


def test_known_answer_identities() -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert debt_face_rollforward_residual(**data["debt_face"]) == Decimal(0)
    assert cash_rollforward_residual(**data["cash"]) == Decimal(0)
    assert sources_uses_residual(**data["sources_uses"]) == Decimal(0)


def test_identity_exposes_residual_instead_of_hiding_it() -> None:
    assert debt_face_rollforward_residual(100, 30, 5, 20, 114) == Decimal(1)


def test_large_cash_balance_keeps_small_unit_in_reconciliation() -> None:
    opening = Decimal(10000000000000000000000000000000000000000)
    closing = Decimal("10000000000000000000000000000000000000000.01")
    assert cash_rollforward_residual(opening, Decimal("0.01"), 0, 0, 0, closing) == 0
    assert sources_uses_residual((opening, Decimal("0.01")), (closing,)) == 0

