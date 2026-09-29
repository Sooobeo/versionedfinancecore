"""Offline known-answer and vintage checks for Walmart's limited M1 case."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from versioned_finance_core.evidence import (
    load_provenanced_facts,
    load_source_ledger,
    select_known_facts,
)
from versioned_finance_core.orchestration.scaffold import validate_case

ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "cases" / "walmart_fy27q1_guidance_outcome"


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_walmart_guidance_outcome_reproduces_offline_at_the_correct_vintage() -> None:
    errors, _ = validate_case(CASE)
    assert errors == []
    evidence = CASE / "01_evidence_core"
    receipts = load_source_ledger(evidence)
    actuals = load_provenanced_facts(evidence)
    assert len(receipts) == 3
    assert len(actuals) == 3
    before_actual = datetime.fromisoformat("2026-02-19T23:59:59-05:00")
    assert select_known_facts(actuals, before_actual) == ()
    assert len(select_known_facts(actuals, datetime.fromisoformat("2026-05-21T23:59:59-04:00"))) == 3

    script = CASE / "reproduce_comparison.py"
    generated = json.loads(subprocess.check_output([sys.executable, str(script)], cwd=ROOT))
    pinned = json.loads(
        (CASE / "03_m1_operating_forecast_valuation" / "guidance_range_comparison.json")
        .read_text(encoding="utf-8")
    )
    assert generated == pinned
    by_metric = {row["metric_id"]: row for row in generated["comparisons"]}
    assert set(by_metric) == {
        "consolidated_net_sales_yoy_cc_pct",
        "consolidated_operating_income_yoy_cc_pct",
        "consolidated_adjusted_diluted_eps_usd_per_share",
    }
    assert (
        by_metric["consolidated_net_sales_yoy_cc_pct"]["guidance_lower"],
        by_metric["consolidated_net_sales_yoy_cc_pct"]["guidance_upper"],
        by_metric["consolidated_net_sales_yoy_cc_pct"]["actual"],
        by_metric["consolidated_net_sales_yoy_cc_pct"]["signed_deviation_from_range"],
    ) == ("3.5", "4.5", "5.7", "1.2")
    assert (
        by_metric["consolidated_operating_income_yoy_cc_pct"]["guidance_lower"],
        by_metric["consolidated_operating_income_yoy_cc_pct"]["guidance_upper"],
        by_metric["consolidated_operating_income_yoy_cc_pct"]["actual"],
        by_metric["consolidated_operating_income_yoy_cc_pct"]["signed_deviation_from_range"],
    ) == ("4.0", "6.0", "2.5", "-1.5")
    assert (
        by_metric["consolidated_adjusted_diluted_eps_usd_per_share"]["guidance_lower"],
        by_metric["consolidated_adjusted_diluted_eps_usd_per_share"]["guidance_upper"],
        by_metric["consolidated_adjusted_diluted_eps_usd_per_share"]["actual"],
        by_metric["consolidated_adjusted_diluted_eps_usd_per_share"]["signed_deviation_from_range"],
    ) == ("0.63", "0.65", "0.66", "0.01")
    for comparison in generated["comparisons"]:
        assert comparison["signed_deviation_from_range"] == comparison["unexplained_residual"]
        assert comparison["guidance_version_id"] != comparison["actual_version_id"]


def test_walmart_guidance_is_not_an_analyst_plan_or_release() -> None:
    versions = _csv(CASE / "02_financial_core" / "versions.csv")
    assert {row["version_type"] for row in versions} == {
        "PUBLIC_TARGET_OR_GUIDANCE", "PUBLIC_ACTUAL",
    }
    assert all(row["immutable"] == "true" for row in versions)
    guidance_rows = _csv(CASE / "03_m1_operating_forecast_valuation" / "forecast_versions.csv")
    guidance_source = next(
        row for row in _csv(CASE / "01_evidence_core" / "source_ledger.csv")
        if row["source_id"] == "wmt_guidance_fy27q1_20260219"
    )
    assert len(guidance_rows) == 6
    for row in guidance_rows:
        assert row["version_id"] == "wmt_fy27q1_guidance_20260219"
        assert row["driver_or_assumption_id"] == guidance_source["source_id"]
        assert row["source_snapshot_id"] == guidance_source["snapshot_id"]
        assert row["source_content_sha256"] == guidance_source["content_sha256"]
        assert row["source_first_public_at"] == guidance_source["first_public_at"]
        assert row["created_at"] == ""
    bridge = _csv(CASE / "03_m1_operating_forecast_valuation" / "variance_bridge.csv")
    assert len(bridge) == 3
    assert all(row["driver_effect"] == "" and row["residual"] == row["total_variance"] for row in bridge)
    gates = _csv(CASE / "07_validation_governance" / "gate_results.csv")
    assert next(row for row in gates if row["gate_id"] == "M1_PERFORMANCE")["status"] == "WITHHELD"
    manifest = json.loads((CASE / "release" / "release_manifest.json").read_text(encoding="utf-8"))
    assert manifest["publication_state"] == "WITHHELD"
    assert manifest["release_id"] is None
