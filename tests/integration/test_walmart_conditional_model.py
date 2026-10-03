"""Offline case reconstruction from pinned source facts to conditional M1 screen."""

from __future__ import annotations

import csv
import json
import runpy
from decimal import Decimal
from pathlib import Path
from shutil import copytree

import pytest

from versioned_finance_core.orchestration.conditional_model import (
    build_review_artifacts as build_conditional_review_artifacts,
)
from versioned_finance_core.orchestration.conditional_model import (
    review_csvs as conditional_review_csvs,
)
from versioned_finance_core.orchestration.core_build import build_core

ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "cases" / "walmart_20260521_p1_valuation"
SCRIPT = CASE / "02_financial_core" / "build_conditional_model.py"
CONFIG = CASE / "02_financial_core" / "conditional_model_config.json"


def _built_facts(tmp_path: Path) -> Path:
    built = build_core(CASE, tmp_path / "core")
    return built / "normalized_actuals.csv"


def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_walmart_linked_forecast_and_valuation_screen_are_reproducible_and_withheld(
    tmp_path: Path,
) -> None:
    functions = runpy.run_path(str(SCRIPT))
    normalized = _built_facts(tmp_path)
    first = functions["build_review_artifacts"](normalized_actuals=normalized)
    second = functions["build_review_artifacts"](normalized_actuals=normalized)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    generic = build_conditional_review_artifacts(
        case_dir=CASE,
        normalized_actuals=normalized,
        config_path=CONFIG,
    )
    assert json.dumps(generic, sort_keys=True) == json.dumps(first, sort_keys=True)

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
    assert set(valuation["wacc"]["failed_structural_checks"]) == {
        "beta_company_fit",
        "market_debt_value_basis",
        "shares_outstanding_as_of_date",
        "debt_value_as_of_date",
    }
    assert valuation["wacc"]["pre_tax_cost_of_debt"] == "0.04758"
    assert valuation["market_input_review"]["wmt_close_20260521"]["first_public_at"] is None
    assert valuation["dcf_screen"]["value_claim"] == "ENTERPRISE_VALUE"
    assert valuation["dcf_screen"]["discount_timing"] == "ACT_365_FIXED"
    assert valuation["dcf_screen"]["conditional_arithmetic_only"]
    assert valuation["dcf_screen"]["release_consumable_enterprise_value_usd"] is None
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
    historical = valuation["historical_lease_cash_tax_diagnostic"]
    assert historical["da_excluding_disclosed_finance_lease_rou_amortization"] == "13315"
    assert historical["finance_lease_cash_paid"] == "1268"
    assert historical["cash_tax_minus_provision"] == "-1835"
    assert historical["finance_lease_income_statement_interest_minus_note_interest"] == "98"
    assert "lease_note_to_income_statement_interest_bridge_unresolved" in historical[
        "modeling_flags"
    ]
    assert historical["forward_application_state"] == "UNKNOWN"
    stub = valuation["dated_stub_boundary"]
    assert stub["parent_dcf_output_id"] == valuation["dcf_screen"]["output_id"]
    assert stub["prevaluation_period_start"] == "2026-05-01"
    assert stub["prevaluation_period_end"] == "2026-05-20"
    assert stub["prevaluation_days"] == 20
    assert stub["postvaluation_days"] == 256
    assert stub["realized_prevaluation_cash_flow_state"] == "UNKNOWN"
    assert stub["status"] == "WITHHELD"
    assert not stub["can_enter_downstream_valuation_eligibility"]
    assert stub["release_consumable_enterprise_value"] is None
    assert valuation["release_status"] == "WITHHELD"
    assert {field["output_id"] for field in first["memo_fields"]["fields"]} == {
        forecast["baseline_output_id"], valuation["dcf_screen"]["output_id"],
        valuation["partial_equity_bridge"]["output_id"],
    }

    csvs = functions["review_csvs"](first)
    assert conditional_review_csvs(generic, config_path=CONFIG) == csvs
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


def test_generic_adapter_rejects_claim_date_that_does_not_match_selected_source(
    tmp_path: Path,
) -> None:
    normalized = _built_facts(tmp_path)
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    config["adapter_metadata"]["claim_aggregates"]["debt"]["balance_date"] = "2026-01-31"
    altered = tmp_path / "misaligned_claim_date.json"
    altered.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ValueError, match="claim balance date"):
        build_conditional_review_artifacts(
            case_dir=CASE,
            normalized_actuals=normalized,
            config_path=altered,
        )


def test_generic_adapter_reads_historical_fact_selector_from_case_config(tmp_path: Path) -> None:
    normalized = _built_facts(tmp_path)
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    config["adapter_metadata"]["historical_fact_selectors"]["current_quarter_capex"][
        "period_end"
    ] = "2026-04-29"
    altered = tmp_path / "misaligned_selector.json"
    altered.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ValueError, match="expected one pinned fact"):
        build_conditional_review_artifacts(
            case_dir=CASE,
            normalized_actuals=normalized,
            config_path=altered,
        )


def test_generic_adapter_rejects_malformed_inputs_and_mismatched_normalized_scope(
    tmp_path: Path,
) -> None:
    malformed_config = tmp_path / "malformed_config.json"
    malformed_config.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="malformed JSON"):
        build_conditional_review_artifacts(
            case_dir=CASE,
            normalized_actuals=tmp_path / "not_read.csv",
            config_path=malformed_config,
        )

    duplicate_key_config = tmp_path / "duplicate_key_config.json"
    duplicate_key_config.write_text('{"schema_version": 1, "schema_version": 1}', encoding="utf-8")
    with pytest.raises(ValueError, match="malformed JSON"):
        build_conditional_review_artifacts(
            case_dir=CASE,
            normalized_actuals=tmp_path / "not_read.csv",
            config_path=duplicate_key_config,
        )

    normalized = _built_facts(tmp_path)
    malformed_csv = tmp_path / "malformed.csv"
    header = normalized.read_text(encoding="utf-8").splitlines()[0]
    malformed_csv.write_text(f'{header}\n"unterminated', encoding="utf-8")
    with pytest.raises(ValueError, match="malformed CSV"):
        build_conditional_review_artifacts(
            case_dir=CASE,
            normalized_actuals=malformed_csv,
            config_path=CONFIG,
        )

    rows = list(csv.DictReader(normalized.read_text(encoding="utf-8").splitlines()))
    for column, replacement, message in (
        ("case_id", "another_case", "case_id mismatch"),
        ("legal_entity_id", "another_legal_entity", "legal entity mismatch"),
    ):
        altered_rows = [dict(row) for row in rows]
        altered_rows[0][column] = replacement
        altered = tmp_path / f"wrong_{column}.csv"
        _write_rows(altered, altered_rows)
        with pytest.raises(ValueError, match=message):
            build_conditional_review_artifacts(
                case_dir=CASE,
                normalized_actuals=altered,
                config_path=CONFIG,
            )


def test_generic_adapter_rejects_case_source_scope_mismatch(tmp_path: Path) -> None:
    normalized = _built_facts(tmp_path)
    copied_case = tmp_path / "cases" / CASE.name
    copytree(CASE, copied_case)
    ledger = copied_case / "01_evidence_core" / "source_ledger.csv"
    rows = list(csv.DictReader(ledger.read_text(encoding="utf-8").splitlines()))
    for row in rows:
        if row["source_id"] == "wmt_fy27q1_8k_ex991_20260521":
            row["entity_scope"] = "wrong_source_scope"
    _write_rows(ledger, rows)

    with pytest.raises(ValueError, match="case source scope mismatch"):
        build_conditional_review_artifacts(
            case_dir=copied_case,
            normalized_actuals=normalized,
            config_path=copied_case / "02_financial_core" / "conditional_model_config.json",
        )


def test_generic_adapter_rejects_historical_diagnostic_value_different_from_locator(
    tmp_path: Path,
) -> None:
    normalized = _built_facts(tmp_path)
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    config["adapter_metadata"]["valuation_controls"]["historical_lease_cash_tax"][
        "finance_lease_rou_amortization"
    ] = "0"
    altered = tmp_path / "historical_value_mismatch.json"
    altered.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ValueError, match="historical control value does not match locator"):
        build_conditional_review_artifacts(
            case_dir=CASE,
            normalized_actuals=normalized,
            config_path=altered,
        )


def test_generic_adapter_rejects_historical_receipt_or_transformation_right(
    tmp_path: Path,
) -> None:
    normalized = _built_facts(tmp_path)
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    config["adapter_metadata"]["valuation_controls"]["historical_lease_cash_tax"][
        "source_receipt"
    ]["content_sha256"] = "0" * 64
    altered = tmp_path / "historical_receipt_mismatch.json"
    altered.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError, match="historical source receipt mismatch"):
        build_conditional_review_artifacts(
            case_dir=CASE,
            normalized_actuals=normalized,
            config_path=altered,
        )

    copied_case = tmp_path / "receipt_right_case" / CASE.name
    copytree(CASE, copied_case)
    ledger = copied_case / "01_evidence_core" / "source_ledger.csv"
    rows = list(csv.DictReader(ledger.read_text(encoding="utf-8").splitlines()))
    receipt = next(row for row in rows if row["source_id"] == "wmt_fy26_10k_html_20260313")
    receipt["transformation_right"] = "NO"
    _write_rows(ledger, rows)
    with pytest.raises(ValueError, match="lacks transformation right"):
        build_conditional_review_artifacts(
            case_dir=copied_case,
            normalized_actuals=normalized,
            config_path=copied_case / "02_financial_core" / "conditional_model_config.json",
        )


@pytest.mark.parametrize(
    ("target", "bad_schema_version"),
    (("configuration", True), ("configuration", 1.0), ("adapter", True), ("adapter", 1.0)),
)
def test_generic_adapter_requires_integer_schema_versions(
    tmp_path: Path, target: str, bad_schema_version: object
) -> None:
    normalized = _built_facts(tmp_path)
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    if target == "configuration":
        config["schema_version"] = bad_schema_version
    else:
        config["adapter_metadata"]["schema_version"] = bad_schema_version
    altered = tmp_path / f"invalid_{target}_{bad_schema_version!s}.json"
    altered.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ValueError, match="schema|review-only"):
        build_conditional_review_artifacts(
            case_dir=CASE,
            normalized_actuals=normalized,
            config_path=altered,
        )


def test_archived_v1_configuration_is_provenance_only_not_current_adapter_input(
    tmp_path: Path,
) -> None:
    normalized = _built_facts(tmp_path)
    with pytest.raises(ValueError, match="version 1 is a provenance snapshot only"):
        build_conditional_review_artifacts(
            case_dir=CASE,
            normalized_actuals=normalized,
            config_path=CASE / "02_financial_core" / "conditional_model_config_v1.json",
        )
