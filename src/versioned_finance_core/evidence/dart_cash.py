"""Pure parser for DART half-year cash-flow statement viewer sections.

The caller supplies the already-retrieved HTML section. Publication timestamps,
receipt IDs, rights, and raw-fact persistence belong to the evidence ledger.
Cash reconciliation belongs to ``financial_core``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from html.parser import HTMLParser

from versioned_finance_core.contracts.enums import AccountingScope

_LABELS = {
    "기초현금및현금성자산": "opening_cash",
    "영업활동현금흐름": "operating_cash_flow",
    "투자활동현금흐름": "investing_cash_flow",
    "재무활동현금흐름": "financing_cash_flow",
    "현금및현금성자산에대한환율변동효과": "fx_and_other",
    "기말현금및현금성자산": "closing_cash",
}
_ROLES = (
    "opening_cash",
    "operating_cash_flow",
    "investing_cash_flow",
    "financing_cash_flow",
    "fx_and_other",
    "closing_cash",
)
_PERIOD = re.compile(
    r"제\s*\d+\s*기\s*반기\s*"
    r"(\d{4})\.(\d{1,2})\.(\d{1,2})\s*부터\s*"
    r"(\d{4})\.(\d{1,2})\.(\d{1,2})\s*까지"
)
_AMOUNT = re.compile(r"(?:\d+|\d{1,3}(?:,\d{3})+)")


@dataclass(frozen=True)
class DartCashRow:
    role: str
    raw_label: str
    raw_value: str
    value: Decimal


@dataclass(frozen=True)
class DartCashStatement:
    accounting_scope: AccountingScope
    period_start: date
    period_end: date
    currency: str
    unit: str
    rows: tuple[DartCashRow, ...]

    def by_role(self) -> dict[str, DartCashRow]:
        return {row.role: row for row in self.rows}


class _Tables(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._depth = 0
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            if self._depth == 0:
                self._table = []
            self._depth += 1
        elif self._depth == 1 and tag == "tr":
            self._row = []
        elif self._depth == 1 and tag in ("th", "td") and self._row is not None:
            self._cell = []
        elif self._depth == 1 and tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if self._depth == 1 and tag in ("th", "td") and self._cell is not None:
            assert self._row is not None
            self._row.append(_space("".join(self._cell)))
            self._cell = None
        elif self._depth == 1 and tag == "tr" and self._row is not None:
            assert self._table is not None
            self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._depth:
            self._depth -= 1
            if self._depth == 0:
                assert self._table is not None
                self.tables.append(self._table)
                self._table = None

    def handle_data(self, data: str) -> None:
        if self._depth == 1 and self._cell is not None:
            self._cell.append(data)


def _space(value: str) -> str:
    return " ".join(value.split())


def _label_key(value: str) -> str:
    return "".join(value.split())


def _parse_amount(value: str, role: str) -> Decimal:
    raw = _space(value)
    negative = raw.startswith("(") and raw.endswith(")")
    digits = raw[1:-1] if negative else raw
    if digits.startswith(("-", "+")) and negative:
        raise ValueError(f"invalid DART amount for {role}: {raw!r}")
    if digits.startswith(("-", "+")):
        negative = digits[0] == "-"
        digits = digits[1:]
    if not _AMOUNT.fullmatch(digits):
        raise ValueError(f"invalid DART amount for {role}: {raw!r}")
    amount = Decimal(digits.replace(",", ""))
    return -amount if negative else amount


def parse_dart_cash_statement(section_html: str) -> DartCashStatement:
    """Extract the six filed current-period rows from one DART H1 section.

    Only exact cash-flow labels are accepted. The previous-year comparative
    column is deliberately ignored. No financial arithmetic is performed here.
    """

    if not isinstance(section_html, str):
        raise TypeError("section_html must be decoded HTML text")
    parser = _Tables()
    parser.feed(section_html)
    parser.close()
    if parser._depth:
        raise ValueError("incomplete DART cash-flow HTML table")

    titled = [
        table for table in parser.tables
        if table and table[0] and _space(table[0][0]) in ("연결 현금흐름표", "현금흐름표")
    ]
    if len(titled) != 1:
        raise ValueError("expected one DART cash-flow statement header")
    header = titled[0]
    scope = (
        AccountingScope.CONSOLIDATED
        if _space(header[0][0]) == "연결 현금흐름표"
        else AccountingScope.STANDALONE
    )
    if len(header) < 2:
        raise ValueError("DART cash-flow statement header has no current period")
    current_period_text = " ".join(header[1])
    period_match = _PERIOD.search(current_period_text)
    if period_match is None:
        raise ValueError("DART H1 period is missing from the statement header")
    start_year, start_month, start_day, end_year, end_month, end_day = (
        int(part) for part in period_match.groups()
    )
    start = date(start_year, start_month, start_day)
    end = date(end_year, end_month, end_day)
    if start != date(start_year, 1, 1) or end != date(start_year, 6, 30):
        raise ValueError("DART statement is not a January-to-June half-year period")
    header_text = " ".join(cell for row in header for cell in row)
    if not re.search(r"\(\s*단위\s*:\s*원\s*\)", header_text):
        raise ValueError("DART cash-flow unit must be Korean won")

    data_tables = [
        table for table in parser.tables if table is not header
        and any(row and _label_key(row[0]) in _LABELS for row in table)
    ]
    if len(data_tables) != 1:
        raise ValueError("expected one DART cash-flow data table")
    data = data_tables[0]
    current_term = re.match(r"제\s*\d+\s*기\s*반기", current_period_text)
    if (
        not data or len(data[0]) < 2 or current_term is None
        or _space(data[0][1]) != _space(current_term.group())
    ):
        raise ValueError("DART cash-flow current-period column is missing")
    found: dict[str, DartCashRow] = {}
    for cells in data:
        if not cells:
            continue
        role = _LABELS.get(_label_key(cells[0]))
        if role is None:
            continue
        if role in found:
            raise ValueError(f"duplicate DART cash-flow label: {cells[0]}")
        if len(cells) != 3:
            raise ValueError(f"DART cash-flow row has wrong column count: {cells[0]}")
        found[role] = DartCashRow(role, cells[0], cells[1], _parse_amount(cells[1], role))
    missing = [role for role in _ROLES if role not in found]
    if missing:
        raise ValueError(f"missing DART cash-flow labels: {', '.join(missing)}")
    return DartCashStatement(scope, start, end, "KRW", "KRW", tuple(found[r] for r in _ROLES))
