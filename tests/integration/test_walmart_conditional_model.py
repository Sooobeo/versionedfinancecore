"""Offline case reconstruction from pinned source facts to conditional M1 screen."""

from __future__ import annotations

import csv
import json
import runpy
from decimal import Decimal
from pathlib import Path

import pytest

from versioned_finance_core.orchestration.core_build import build_core

ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "cases" / "walmart_20260521_p1_valuation"
SCRIPT = CASE / "02_financial_core" / "build_conditional_model.py"
CONFIG = CASE / "02_financial_core" / "conditional_model_config.json"


def _built_facts(tmp_path: Path) -> Path:
    built = build_core(CASE, tmp_path / "core")
    return built / "normalized_actuals.csv"


def test_walmart_linked_forecast_and_valuation_screen_are_reproducible_and_withheld(
    tmp_path: Path,
) -> None:
    functions = runpy.run_path(str(SCRIPT))
    normalized = _built_facts(tmp_path)
    first = functions["build_review_artifacts"](normalized_actuals=normalized)
    second = functions["build_review_artifacts"](normalized_actuals=normalized)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)

    forecast, valuation = first["forecast"], first["valuation"]
    assert forecast["opening_balance_sheet"]["cash"] == "10729000000"
    assert len(forecast["periods"]) == 5
    assert forecast["periods"][0]["income_statement"]["net_sales"] == "558976176000.0000"
    assert all(
        all(Decimal(value) == 0 for value in period["identity_residuals"].values())
        for period in forecast["periods"]
    )
    assert all(period["fcff_output_id"].startswith("core_fcff_") for period in forecast["periods"])
    assert all(period["cash_component_audit_id"].startswith("core_cash_inclusion_") for period in forecast["periods"])
    assert len(forecast["cash_component_audits"]) == 5
    assert valuation["wacc"]["eligibility_status"] == "WITHHELD"
    assert "lease_valuation_treatment" in valuation["wacc"]["failed_structural_checks"]
    assert valuation["market_input_review"]["wmt_close_20260521"]["first_public_at"] is None
    assert valuation["dcf_screen"]["value_claim"] == "ENTERPRISE_VALUE"
    assert valuation["dcf_screen"]["discount_timing"] == "ACT_365_FIXED"
    assert valuation["terminal"]["final_core_fcff_output_id"] == forecast["periods"][-1]["fcff_output_id"]
    assert Decimal(valuation["terminal"]["transition_difference"]) > 0
    assert Decimal(valuation["terminal"]["transition_ratio"]) > Decimal("1.7")
    assert valuation["partial_equity_bridge"]["known_claims"]["debt_and_finance_leases_usd"] == "58129000000"
    assert valuation["partial_equity_bridge"]["known_claims"]["redeemable_and_nonredeemable_nci_usd"] == "6645000000"
    assert len(valuation["partial_equity_bridge"]["known_claims"]["debt_component_source_ids"]) == 5
    assert len(valuation["partial_equity_bridge"]["known_claims"]["minority_component_source_ids"]) == 2
    assert set(valuation["partial_equity_bridge"]["unknown_components"]) == {
        "excess_cash", "nonoperating_assets", "other_senior_claims",
    }
    assert valuation["partial_equity_bridge"]["equity_value"] is None
    assert valuation["release_status"] == "WITHHELD"
    assert {field["output_id"] for field in first["memo_fields"]["fields"]} == {
        forecast["baseline_output_id"], valuation["dcf_screen"]["output_id"],
        valuation["partial_equity_bridge"]["output_id"],
    }

    csvs = functions["review_csvs"](first)
    assert len(list(csv.DictReader(csvs["conditional_scenario_drivers.csv"].splitlines()))) == 165
    assumption_rows = list(csv.DictReader(csvs["assumptions.csv"].splitlines()))
    assert len(assumption_rows) == len({row["assumption_id"] for row in assumption_rows})
    valuation_row = next(csv.DictReader(csvs["valuation_runs.csv"].splitlines()))
    assert valuation_row["eligibility_state"] == "WITHHELD"
    assert valuation_row["enterprise_value"] == valuation_row["equity_value"] == ""


def test_walmart_model_rejects_late_fact_and_unreconciled_claim_proxy(tmp_path: Path) -> None:
    functions = runpy.run_path(str(SCRIPT))
    normalized = _built_facts(tmp_path)
    rows = list(csv.DictReader(normalized.read_text(encoding="utf-8").splitlines()))
    target = next(row for row in rows if row["metric_id"] == "finance_lease_current"
                  and row["period_end"] == "2026-04-30")
    target["first_public_at"] = "2026-05-22T12:00:00-04:00"
    late = tmp_path / "late.csv"
    with late.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="cutoff"):
        functions["build_review_artifacts"](normalized_actuals=late)

    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    config["wacc_screen"]["debt_value_usd"] = "0"
    altered = tmp_path / "altered_config.json"
    altered.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError, match="WACC debt proxy"):
        functions["build_review_artifacts"](
            normalized_actuals=normalized, config_path=altered
        )
