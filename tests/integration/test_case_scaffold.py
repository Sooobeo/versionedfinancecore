import csv
import json
import shutil
from pathlib import Path

import pytest

from versioned_finance_core.orchestration.release import build_manifest
from versioned_finance_core.orchestration.scaffold import initialize_case, validate_case

PROJECT_ROOT = Path(__file__).parents[2]
TEMPLATE = PROJECT_ROOT / "cases" / "_template"
ORION = PROJECT_ROOT / "cases" / "orion_jincheon_2026h1"


def test_case_template_has_required_structure() -> None:
    errors, warnings = validate_case(TEMPLATE)
    assert errors == []
    assert warnings


def test_initialize_case_is_non_destructive(tmp_path: Path) -> None:
    cases_dir = tmp_path / "cases"
    created = initialize_case("sample_case", cases_dir, TEMPLATE)
    case = json.loads((created / "00_charter" / "case.json").read_text(encoding="utf-8"))
    draft_manifest = json.loads(
        (created / "release" / "release_manifest.json").read_text(encoding="utf-8")
    )
    assert case["case_id"] == "sample_case"
    assert case["status"] == "DRAFT"
    assert draft_manifest["case_id"] == "sample_case"
    assert draft_manifest["publication_state"] == "WITHHELD"

    with pytest.raises(FileExistsError):
        initialize_case("sample_case", cases_dir, TEMPLATE)


def test_manifest_excludes_itself_and_starts_withheld(tmp_path: Path) -> None:
    created = initialize_case("manifest_case", tmp_path / "cases", TEMPLATE)
    manifest = build_manifest(created)
    assert manifest["case_id"] == "manifest_case"
    assert manifest["publication_state"] == "WITHHELD"
    assert "release/release_manifest.json" not in manifest["file_hashes"]


def test_case_validation_rejects_stale_csv_contract(tmp_path: Path) -> None:
    created = initialize_case("schema_case", tmp_path / "cases", TEMPLATE)
    facts = created / "01_evidence_core" / "raw_facts.csv"
    facts.write_text("fact_id,source_id,raw_value\n", encoding="utf-8")
    errors, _ = validate_case(created)
    assert any("Missing CSV columns in 01_evidence_core/raw_facts.csv" in item for item in errors)


def test_case_validation_rejects_mismatched_case_id(tmp_path: Path) -> None:
    created = initialize_case("named_case", tmp_path / "cases", TEMPLATE)
    case_path = created / "00_charter" / "case.json"
    data = json.loads(case_path.read_text(encoding="utf-8"))
    data["case_id"] = "other_case"
    case_path.write_text(json.dumps(data), encoding="utf-8")
    errors, _ = validate_case(created)
    assert "case.json case_id does not match the case directory" in errors


def test_case_validation_rejects_stale_case_manifest(tmp_path: Path) -> None:
    created = tmp_path / ORION.name
    shutil.copytree(ORION, created)
    manifest_path = created / "release" / "release_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["case_id"] = "replace_me"
    manifest["cutoff_timestamp"] = None
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    errors, _ = validate_case(created)
    assert "release_manifest.json case_id does not match the case directory" in errors
    assert "release_manifest.json cutoff differs from case.json" in errors


def test_case_validation_rejects_corrupt_receipt_identity(tmp_path: Path) -> None:
    created = tmp_path / ORION.name
    shutil.copytree(ORION, created)
    ledger = created / "01_evidence_core" / "source_ledger.csv"
    with ledger.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        rows = list(reader)
    assert rows and fieldnames
    rows[0]["snapshot_id"] = "wrong_" + rows[0]["snapshot_id"]
    with ledger.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    errors, _ = validate_case(created)
    assert any("Invalid source_ledger.csv" in item for item in errors)


def test_case_validation_rejects_raw_fact_lineage_mismatch(tmp_path: Path) -> None:
    created = tmp_path / ORION.name
    shutil.copytree(ORION, created)
    facts = created / "01_evidence_core" / "raw_facts.csv"
    with facts.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        rows = list(reader)
    assert rows and fieldnames
    rows[0]["snapshot_id"] = "wrong_" + rows[0]["snapshot_id"]
    with facts.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    errors, _ = validate_case(created)
    assert any("Invalid raw_facts.csv lineage" in item for item in errors)

