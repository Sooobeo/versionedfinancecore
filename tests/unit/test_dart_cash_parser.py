from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from versioned_finance_core.contracts.enums import AccountingScope
from versioned_finance_core.evidence.dart_cash import parse_dart_cash_statement

FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures"
    / "synthetic_known_answers"
    / "dart_cash_h1.html"
)


def _html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_parses_synthetic_h1_rows_without_changing_source_sign() -> None:
    statement = parse_dart_cash_statement(_html())
    assert statement.accounting_scope == AccountingScope.CONSOLIDATED
    assert (statement.period_start, statement.period_end) == (date(2030, 1, 1), date(2030, 6, 30))
    assert (statement.currency, statement.unit) == ("KRW", "KRW")
    assert [(row.role, row.value) for row in statement.rows] == [
        ("opening_cash", Decimal(10)),
        ("operating_cash_flow", Decimal(12)),
        ("investing_cash_flow", Decimal(-3)),
        ("financing_cash_flow", Decimal(-2)),
        ("fx_and_other", Decimal(1)),
        ("closing_cash", Decimal(18)),
    ]
    assert statement.by_role()["investing_cash_flow"].raw_value == "(3)"
    assert statement.by_role()["fx_and_other"].raw_label == (
        "현금및현금성자산에 대한 환율변동효과"
    )


def test_standalone_title_is_a_distinct_scope() -> None:
    statement = parse_dart_cash_statement(_html().replace("연결 현금흐름표", "현금흐름표"))
    assert statement.accounting_scope == AccountingScope.STANDALONE


def test_missing_and_duplicate_cash_labels_fail() -> None:
    original = _html()
    row = "<tr><td>재무활동현금흐름</td><td>(2)</td><td>(1)</td></tr>"
    assert row in original
    with pytest.raises(ValueError, match="missing DART cash-flow labels: financing_cash_flow"):
        parse_dart_cash_statement(original.replace(row, ""))
    with pytest.raises(ValueError, match="duplicate DART cash-flow label"):
        parse_dart_cash_statement(original.replace(row, row + row))


@pytest.mark.parametrize(
    ("changed", "error"),
    [
        (lambda text: text.replace("(단위 : 원)", "(단위 : 천원)"), "unit must be Korean won"),
        (lambda text: text.replace("2030.06.30", "2030.09.30"), "not a January-to-June"),
        (lambda text: text.replace("제 13 기 반기</th>", "제 11 기 반기</th>"),
         "current-period column is missing"),
        (lambda text: text.replace("<td>(3)</td>", "<td>3.5</td>"), "invalid DART amount"),
        (lambda text: text.replace("<td>(3)</td>", "<td>(+3)</td>"), "invalid DART amount"),
        (lambda text: text.replace("<td>10</td>", "<td></td>"), "invalid DART amount"),
    ],
)
def test_invalid_unit_period_and_amount_fail(changed, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        parse_dart_cash_statement(changed(_html()))
