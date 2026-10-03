"""Offline checks of the SEC-filed SWA DFS case and its claim boundary."""

from __future__ import annotations

import csv
import importlib.util
from decimal import Decimal
from pathlib import Path

import pytest

from versioned_finance_core.evidence import (
    load_provenanced_facts,
    load_source_ledger,
    receipt_id,
)

CASE_DIR = Path(__file__).parents[2] / "cases" / "standard_lithium_swa_2025dfs"


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dfs_arithmetic_is_reproducible_but_not_an_incremental_decision() -> None:
    evidence_dir = CASE_DIR / "01_evidence_core"
    receipts = load_source_ledger(evidence_dir)
    assert {receipt.source_id for receipt in receipts} == {
        "sec_sli_swa_dfs_20251014",
        "sec_sli_40f_20250324",
        "sec_sli_doe_grant_20250116",
    }
    for receipt in receipts:
        assert receipt.snapshot_id == receipt_id(
            receipt.source_id, receipt.metadata.retrieved_at, receipt.content_sha256
        )
        assert not receipt.metadata.retention_right
    assert load_provenanced_facts(evidence_dir) == ()

    check = _module("swa_dfs_check", CASE_DIR / "07_validation_governance" / "reproduce_dfs.py")
    result = check.reproduce()
    assert len(check.load_rounded_cash()) == 23
    assert Decimal(result["sum_of_rounded_annual_fcff_D"]) == Decimal("4701.5")
    assert Decimal(result["published_npv_8pct_F"]) == Decimal("1275.0")
    assert abs(Decimal(result["mid_year_difference_from_published_D"])) < Decimal(
        result["maximum_annual_row_rounding_effect_D"]
    )
    assert Decimal(result["npv_start_year_D"]) > Decimal("1275.0")
    assert Decimal(result["npv_end_year_D"]) < Decimal("1275.0")
    assert Decimal(result["irr_from_rounded_annual_fcff_D"]).quantize(
        Decimal("0.001")
    ) == Decimal("0.182")
    assert result["timing_state"] == "MID_YEAR_IS_AN_INFERENCE_NOT_A_DISCLOSED_CONVENTION"

    with (CASE_DIR / "04_m2_capital_allocation" / "alternatives.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        alternatives = {row["option_id"]: row for row in csv.DictReader(handle)}
    assert alternatives["NO_BUILD_HOLD"]["evidence_state"] == "UNKNOWN"
    with (CASE_DIR / "07_validation_governance" / "gate_results.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        gates = {row["gate_id"]: row["status"] for row in csv.DictReader(handle)}
    assert gates["DFS_PROJECT_MODEL_ARITHMETIC"] == "PASS"
    assert gates["M2_CAPITAL_ALLOCATION"] == "WITHHELD"


def test_dfs_table_extractor_keeps_relative_period_and_dash() -> None:
    extractor = _module("swa_dfs_extract", CASE_DIR / "01_evidence_core" / "extract_dfs.py")

    def tr(values: tuple[str, ...]) -> str:
        return "<tr>" + "".join(f"<td>{value}</td>" for value in values) + "</tr>"

    header = tr(("Dollar Figures in real 2025 $M", "US$M", "Total", *extractor.PERIODS))
    rows = "".join(
        tr((label, "US$M", "0", "-", *("-1.0" for _ in range(23))))
        for label in extractor.ROWS
    )
    # The source has a repeated table header. Only one cash-flow block is complete.
    html = "<table>" + header + rows + header + "</table>"
    parsed = extractor.parse_table_22_2(html)
    assert len(parsed) == 24
    assert parsed[0]["relative_period"] == "-4"
    assert parsed[0]["post_tax_unlevered_fcff"] == "-"
    assert parsed[-1]["relative_period"] == "20"
    assert parsed[-1]["post_tax_unlevered_fcff"] == "-1.0"
    with pytest.raises(ValueError, match="one complete Table 22-2"):
        extractor.parse_table_22_2("<table>" + header + rows.replace("Closure Capital", "Missing") + "</table>")
