"""Offline registered-fact integration; raw company HTML is not a fixture."""

import csv
import shutil
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from versioned_finance_core.evidence import load_source_ledger, register_source_locator
from versioned_finance_core.orchestration.core_build import build_core
from versioned_finance_core.orchestration.credit_evidence import review_credit_evidence

CASE = Path(__file__).parents[2] / "cases/ford_credit_2025ye_m3"


def test_ford_public_disclosures_reconcile_without_legal_cash_inference(tmp_path):
    core = build_core(CASE, tmp_path / "core")
    result = review_credit_evidence(CASE, core)
    assert [row["state"] for row in result["disclosure_audits"]] == ["PASS"] * 4
    assert [row["calculated_value"] for row in result["disclosure_audits"]] == [
        "24.4", "24.6", "141417", "141904",
    ]
    assert len(result["disclosed_maturity_buckets"]) == 17
    assert all(row["payment_date"] == "UNKNOWN" for row in result["disclosed_maturity_buckets"])
    assert len(result["public_terms"]) == 10
    assert len(result["entities"]) == 6
    assert result["accessible_cash"] == "UNKNOWN"
    assert result["refinancing_gap"] == "NOT_TESTABLE_FROM_PUBLIC_DATA"
    assert result["first_failure_date"] is None
    assert result["recovery_state"] == "STRUCTURE_ONLY"
    assert result["release_status"] == "WITHHELD"
    assert all(row["drawable_amount"] == "UNKNOWN" for row in result["debt_and_facilities"])
    assert result == review_credit_evidence(CASE, core)


@pytest.mark.parametrize("column,value,match", [
    ("content_sha256", "0" * 64, "provenance"),
    ("as_of_date", "2026-12-31", "after cutoff"),
    ("legal_entity_id", "unknown", "scope"),
    ("term_type", "INVENTED", "Unknown public"),
    ("value", "NaN", "finite"),
    ("value", "invalid_amount", "Decimal"),
    ("legal_entity_id", "ford_bank_gmbh", "instrument scope"),
    ("verified_at", "2026-10-03T10:23:45", "timestamp"),
])
def test_public_terms_reject_bad_provenance_and_invalid_fields(tmp_path, column, value, match):
    case_dir = tmp_path / CASE.name
    shutil.copytree(CASE, case_dir)
    path = case_dir / "05_m3_credit_liquidity_claims/public_terms.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields, rows = reader.fieldnames, list(reader)
    rows[0][column] = value
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    core = build_core(case_dir, tmp_path / "core")
    with pytest.raises(ValueError, match=match):
        review_credit_evidence(case_dir, core)


def test_unlabelled_facility_amounts_fail_closed(tmp_path):
    case_dir = tmp_path / CASE.name
    shutil.copytree(CASE, case_dir)
    path = case_dir / "05_m3_credit_liquidity_claims/debt_facilities.csv"
    text = path.read_text(encoding="utf-8").replace(",USD_MILLION", ",UNKNOWN")
    path.write_text(text, encoding="utf-8")
    core = build_core(case_dir, tmp_path / "core")
    with pytest.raises(ValueError, match="explicit currency-compatible unit"):
        review_credit_evidence(case_dir, core)


@pytest.mark.parametrize("restriction", ["late", "rights", "ineligible"])
def test_term_snapshot_itself_must_be_eligible_not_merely_source_id(tmp_path, restriction):
    case_dir = tmp_path / CASE.name
    shutil.copytree(CASE, case_dir)
    evidence_dir = case_dir / "01_evidence_core"
    original = load_source_ledger(evidence_dir)[-1]
    changes = {"retrieved_at": original.metadata.retrieved_at + timedelta(seconds=1)}
    if restriction == "late":
        changes["first_public_at"] = original.first_public_at + timedelta(days=1)
    elif restriction == "rights":
        changes["transformation_right"] = False
    else:
        changes["cutoff_eligible"] = False
    late = register_source_locator(evidence_dir, replace(original.metadata, **changes), "0" * 64)
    path = case_dir / "05_m3_credit_liquidity_claims/public_terms.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields, rows = reader.fieldnames, list(reader)
    rows[0].update(snapshot_id=late.snapshot_id, content_sha256=late.content_sha256,
                   first_public_at=late.first_public_at.isoformat(),
                   retrieved_at=late.metadata.retrieved_at.isoformat(),
                   verified_at=late.metadata.retrieved_at.isoformat())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    core = build_core(case_dir, tmp_path / "core")
    with pytest.raises(ValueError, match="receipt is not eligible"):
        review_credit_evidence(case_dir, core)


def test_malformed_quoted_term_row_fails_closed(tmp_path):
    case_dir = tmp_path / CASE.name
    shutil.copytree(CASE, case_dir)
    path = case_dir / "05_m3_credit_liquidity_claims/public_terms.csv"
    header = path.read_text(encoding="utf-8").splitlines()[0]
    path.write_text(header + '\n"unterminated', encoding="utf-8")
    core = build_core(case_dir, tmp_path / "core")
    with pytest.raises(ValueError, match="Malformed credit CSV"):
        review_credit_evidence(case_dir, core)
