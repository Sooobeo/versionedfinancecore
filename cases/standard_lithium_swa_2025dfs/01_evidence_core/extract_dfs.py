"""Read the published SWA DFS model table without treating it as actual cash.

The SEC filing is a locator-only source in this case. Download it separately
under the SEC fair-access policy, then run this parser on the local HTML file.
The source HTML must not be committed to this repository.
"""

from __future__ import annotations

import argparse
import csv
from html.parser import HTMLParser
from pathlib import Path

PERIODS = ("-4", "-3", "-2", "-1", *(str(year) for year in range(1, 21)))
ROWS = {
    "Initial Capital": "initial_capital",
    "Sustaining Capital": "sustaining_capital",
    "Closure Capital": "closure_capital",
    "Change in Working Capital": "change_in_working_capital",
    "Pre-Tax Unlevered Free Cash Flow": "pre_tax_unlevered_fcff",
    "Unlevered Cash Taxes": "unlevered_cash_taxes",
    "Post-Tax Unlevered Free Cash Flow": "post_tax_unlevered_fcff",
}


class _Rows(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[tuple[str, ...]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._row is not None and self._cell is not None:
            value = " ".join("".join(self._cell).split())
            self._row.append(value)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(tuple(self._row))
            self._row = None


def parse_table_22_2(html: str) -> tuple[dict[str, str], ...]:
    """Return only the model row cells, retaining dashes as unavailable values."""

    parser = _Rows()
    parser.feed(html)
    headers = [
        index for index, row in enumerate(parser.rows)
        if row and row[0].startswith("Dollar Figures in real 2025 $M")
        and tuple(row[-24:]) == PERIODS
    ]
    selected_groups: list[dict[str, tuple[str, ...]]] = []
    for index, start in enumerate(headers):
        stop = headers[index + 1] if index + 1 < len(headers) else start + 40
        selected: dict[str, tuple[str, ...]] = {}
        for row in parser.rows[start + 1:stop]:
            if row and row[0] in ROWS:
                if row[0] in selected:
                    raise ValueError(f"Duplicate model row: {row[0]}")
                if len(row) != 27 or row[1] != "US$M":
                    raise ValueError(f"Unexpected 2025 USD million row structure: {row[0]}")
                selected[row[0]] = row
        if set(selected) == set(ROWS):
            selected_groups.append(selected)
    if len(selected_groups) != 1:
        raise ValueError("Expected one complete Table 22-2 cash-flow block")
    selected = selected_groups[0]
    output = []
    for position, period in enumerate(PERIODS, start=3):
        values = {
            normalized: selected[label][position]
            for label, normalized in ROWS.items()
        }
        output.append({"relative_period": period, **values})
    return tuple(output)


def _write_csv(rows: tuple[dict[str, str], ...], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("relative_period", *ROWS.values()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html_file", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    html = args.html_file.read_text(encoding="utf-8")
    rows = parse_table_22_2(html)
    if args.output:
        _write_csv(rows, args.output)
    else:
        for row in rows:
            print(row)


if __name__ == "__main__":
    main()
