"""Offline contract tests for the reusable public-evidence adapters."""

from __future__ import annotations

import json
import shutil
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest

from versioned_finance_core.orchestration.public_reproductions import (
    dfs_legacy_artifact,
    guidance_legacy_artifact,
    reproduce_dfs,
    reproduce_guidance,
    reproduce_m2_evidence,
)

ROOT = Path(__file__).resolve().parents[2]
WALMART_CASE = ROOT / "cases" / "walmart_fy27q1_guidance_outcome"
SWA_CASE = ROOT / "cases" / "standard_lithium_swa_2025dfs"
ORION_CASE = ROOT / "cases" / "orion_jincheon_2026h1"


def test_public_guidance_adapter_reuses_core_and_m1_without_releasing_m1() -> None:
    result = reproduce_guidance(WALMART_CASE)

    assert result == reproduce_guidance(WALMART_CASE)
    assert result["output_id"].startswith("m1_guidance_reproduction_")
    assert result["calculation_state"] == "PASS"
    assert result["module_state"] == "WITHHELD"
    assert result["release_status"] == "WITHHELD"
    assert len(result["canonical_output_ids"]) == 3
    assert all(item.startswith("m1_guidance_range_") for item in result["canonical_output_ids"])
    assert all((WALMART_CASE / item).is_file() for item in result["input_files"])
    assert "driver attribution" in " ".join(result["limitations"])
    assert json.loads(json.dumps(result)) == result

    pinned = json.loads(
        (
            WALMART_CASE
            / "03_m1_operating_forecast_valuation"
            / "guidance_range_comparison.json"
        ).read_text(encoding="utf-8")
    )
    assert guidance_legacy_artifact(result) == pinned


def test_public_dfs_adapter_reconciles_the_public_row_without_creating_an_m2_option_value() -> None:
    result = reproduce_dfs(SWA_CASE)
    reproduction = result["reported_project_cash_audit"]

    assert result == reproduce_dfs(SWA_CASE)
    assert result["output_id"].startswith("m2_dfs_reproduction_")
    assert result["calculation_state"] == "PASS"
    assert result["module_state"] == "WITHHELD"
    assert result["release_status"] == "WITHHELD"
    assert result["m2_option_evaluation_state"] == "NOT_TESTABLE_FROM_PUBLIC_DATA"
    assert result["m2_option_valuation"] is None
    assert result["m2_input_coverage"] == {
        "status_quo_evidence_state": "UNKNOWN",
        "incremental_cash_flow_row_count": 0,
        "sources_uses_row_count": 0,
        "public_evidence_row_count": 8,
        "incremental_cashflow_evidence_state": "NOT_TESTABLE_FROM_PUBLIC_DATA",
        "funding_feasibility_evidence_state": "NOT_TESTABLE_FROM_PUBLIC_DATA",
    }
    evidence = result["m2_public_evidence_assessment"]
    assert evidence["decision_state"] == "NOT_TESTABLE_FROM_PUBLIC_DATA"
    assert evidence["criterion_coverage"][3] == {
        "criterion": "AFTER_TAX_BASIS",
        "coverage": "COMPLETE",
    }
    assert {item["source_id"] for item in result["m2_public_evidence_items"]} == {
        "sec_sli_swa_dfs_20251014",
        "sec_sli_40f_20250324",
        "sec_sli_doe_grant_20250116",
    }
    assert reproduction["annual_discount_rate"] == "0.08"
    assert reproduction["annual_discount_rate_unit"] == "real_annual_fraction"
    assert all((SWA_CASE / item).is_file() for item in result["input_files"])
    assert result["rounding"]["display_quantums"] == ["0.1"]
    assert Decimal(reproduction["sum_of_rounded_annual_fcff_D"]) == Decimal("4701.5")
    assert abs(Decimal(reproduction["mid_year_difference_from_published_D"])) < Decimal(
        reproduction["maximum_annual_row_rounding_effect_D"]
    )
    assert "not expanded into an unconditional no-build cash path" in " ".join(
        result["limitations"]
    )
    assert json.loads(json.dumps(result)) == result

    pinned = json.loads(
        (
            SWA_CASE / "04_m2_capital_allocation" / "dfs_reproduction.json"
        ).read_text(encoding="utf-8")
    )
    assert dfs_legacy_artifact(result) == pinned

    non_eight_percent = deepcopy(result)
    non_eight_percent["assumptions"]["discount_rate"]["value"] = "0.07"
    non_eight_percent["reported_project_cash_audit"]["annual_discount_rate"] = "0.07"
    with pytest.raises(ValueError, match="only labels a published NPV at 8%"):
        dfs_legacy_artifact(non_eight_percent)


def test_public_dfs_adapter_rejects_unknown_rows_that_would_compress_timing(tmp_path: Path) -> None:
    case_dir = tmp_path / SWA_CASE.name
    shutil.copytree(SWA_CASE, case_dir)
    model_path = case_dir / "04_m2_capital_allocation" / "dfs_project_model.csv"
    model_path.write_text(
        model_path.read_text(encoding="utf-8").replace(
            ",-2,PRE_EXECUTION,-688.9,KNOWN,",
            ",-2,PRE_EXECUTION,,UNKNOWN,",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="only leading unknown"):
        reproduce_dfs(case_dir)


def test_public_dfs_adapter_rejects_reordered_relative_periods(tmp_path: Path) -> None:
    case_dir = tmp_path / SWA_CASE.name
    shutil.copytree(SWA_CASE, case_dir)
    model_path = case_dir / "04_m2_capital_allocation" / "dfs_project_model.csv"
    lines = model_path.read_text(encoding="utf-8").splitlines()
    lines[3], lines[4] = lines[4], lines[3]
    model_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="supported ordered sequence"):
        reproduce_dfs(case_dir)


def test_public_guidance_adapter_rejects_malformed_local_csv(tmp_path: Path) -> None:
    case_dir = tmp_path / WALMART_CASE.name
    shutil.copytree(WALMART_CASE, case_dir)
    guidance_path = case_dir / "03_m1_operating_forecast_valuation" / "forecast_versions.csv"
    guidance_path.write_text(
        guidance_path.read_text(encoding="utf-8").splitlines()[0] + "\n\"unterminated,range,metric\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="malformed CSV"):
        reproduce_guidance(case_dir)


def test_orion_public_m2_evidence_is_source_linked_and_does_not_make_a_defer_case() -> None:
    result = reproduce_m2_evidence(ORION_CASE)

    assert result == reproduce_m2_evidence(ORION_CASE)
    assert result["output_id"].startswith("m2_public_evidence_reproduction_")
    assert result["release_status"] == "WITHHELD"
    assert result["calculation_state"] == "NOT_TESTABLE_FROM_PUBLIC_DATA"
    assert result["declared_status_quo_option_id"] == "STATUS_QUO"
    assessment = result["m2_public_evidence_assessment"]
    assert assessment["incremental_cashflow_state"] == "NOT_TESTABLE_FROM_PUBLIC_DATA"
    assert assessment["funding_feasibility_state"] == "NOT_TESTABLE_FROM_PUBLIC_DATA"
    assert "EXECUTABLE_OPTION_RIGHTS" in assessment["blocking_criteria"]
    progress = next(
        item for item in result["evidence_items"] if item["evidence_id"] == "ORION_PHYSICAL_PROGRESS_ONLY"
    )
    assert progress["disclosed_value"] == "36"
    assert progress["unit"] == "percent_physical_progress"
    assert len(progress["source_content_sha256"]) == 64
    assert progress["source_retrieved_at"].endswith("+00:00")
    assert "cash-disbursement percentage" in progress["limitation"]
    assert all((ORION_CASE / item).is_file() for item in result["input_files"])
    assert json.loads(json.dumps(result)) == result


def test_public_m2_evidence_rejects_an_unlinked_factual_missing_row(tmp_path: Path) -> None:
    case_dir = tmp_path / ORION_CASE.name
    shutil.copytree(ORION_CASE, case_dir)
    evidence_path = case_dir / "04_m2_capital_allocation" / "public_m2_evidence.csv"
    evidence_path.write_text(
        evidence_path.read_text(encoding="utf-8").replace(
            "ORION_STATUS_QUO_REMAINING_SPEND,STATUS_QUO_CASH_PATH,MISSING,,,,I,",
            "ORION_STATUS_QUO_REMAINING_SPEND,STATUS_QUO_CASH_PATH,MISSING,,,,F,",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unlinked factual value"):
        reproduce_m2_evidence(case_dir)
