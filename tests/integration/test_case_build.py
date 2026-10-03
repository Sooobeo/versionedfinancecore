"""End-to-end checks for immutable, offline case-review bundles."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from versioned_finance_core.cli import main
from versioned_finance_core.contracts.enums import AccessClass, PublicationStatus
from versioned_finance_core.evidence import SourceMetadata, content_path, ingest_snapshot
from versioned_finance_core.orchestration import case_build
from versioned_finance_core.orchestration.case_build import build_case, verify_case_build

REPOSITORY_ROOT = Path(__file__).parents[2]
ORION = REPOSITORY_ROOT / "cases" / "orion_jincheon_2026h1"
FORD = REPOSITORY_ROOT / "cases" / "ford_credit_2025ye_m3"
WALMART_CONDITIONAL = REPOSITORY_ROOT / "cases" / "walmart_20260521_p1_valuation"
WALMART_GUIDANCE = REPOSITORY_ROOT / "cases" / "walmart_fy27q1_guidance_outcome"
SWA = REPOSITORY_ROOT / "cases" / "standard_lithium_swa_2025dfs"


def _copy_case(source: Path, destination: Path) -> Path:
    case_dir = destination / source.name
    shutil.copytree(source, case_dir)
    return case_dir


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


@pytest.mark.parametrize("remove_snapshot", [False, True], ids=["corrupted", "removed"])
def test_retained_snapshot_change_during_build_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, remove_snapshot: bool,
) -> None:
    case_dir = _copy_case(ORION, tmp_path / "source")
    evidence_dir = case_dir / "01_evidence_core"
    source = tmp_path / "synthetic.txt"
    source.write_text("synthetic dependency control, not company evidence", encoding="utf-8")
    receipt = ingest_snapshot(evidence_dir, source, SourceMetadata(
        source_id="synthetic_dependency_control", access_class=AccessClass.SYNTHETIC_TEST,
        authority="Synthetic test", title="Dependency control", url="https://example.invalid",
        document_id="", retrieved_at=datetime(2025, 1, 1, tzinfo=UTC),
        publication_status=PublicationStatus.FILED,
        first_public_at=datetime(2025, 1, 1, tzinfo=UTC),
        retention_right=True, transformation_right=True, redistribution_right=True,
        cutoff_eligible=True,
    ))
    raw_path = content_path(evidence_dir, receipt)
    original = case_build.build_core

    def mutate_after_core(case: Path, build: Path) -> Path:
        result = original(case, build)
        if remove_snapshot:
            raw_path.unlink()
        else:
            raw_path.write_text("corrupted synthetic bytes", encoding="utf-8")
        return result

    monkeypatch.setattr(case_build, "build_core", mutate_after_core)
    with pytest.raises(ValueError, match="changed during|content hash mismatch"):
        build_case(case_dir, tmp_path / "build")
    assert not (tmp_path / "build").exists()


@pytest.mark.parametrize(
    "case_source",
    [ORION, WALMART_CONDITIONAL, WALMART_GUIDANCE, SWA, FORD],
    ids=["orion", "walmart-conditional", "walmart-guidance", "swa", "ford"],
)
def test_real_case_recipe_builds_fresh_withheld_bundle_and_verifies(
    tmp_path: Path, case_source: Path
) -> None:
    case_dir = _copy_case(case_source, tmp_path / "source")
    stage = build_case(case_dir, tmp_path / "build")

    manifest = _read_json(stage / "release_manifest.json")
    report = _read_json(stage / "outputs" / "review_report.json")
    assert manifest["case_id"] == case_source.name
    assert manifest["publication_state"] == "WITHHELD"
    assert manifest["release_ready"] is False
    assert report["case_id"] == case_source.name
    assert report["publication_state"] == "WITHHELD"
    assert report["expected_modules"] == _read_json(case_dir / "00_charter" / "case.json")[
        "active_modules"
    ]
    assert report["release_blockers"]
    assert "outputs/review_report.json" in manifest["output_paths"]
    assert "outputs/review_memo.md" in manifest["memo_paths"]
    assert set(report["artifact_hashes"]) == set(manifest["output_paths"]) - {
        "outputs/review_report.json",
        "outputs/review_memo.md",
    }
    assert any("Pipeline review report blocks release:" in item for item in manifest["known_limitations"])
    assert f"output_id: {report['output_id']}" in (
        stage / "outputs" / "review_memo.md"
    ).read_text(encoding="utf-8")

    verified = verify_case_build(stage)
    assert verified["case_id"] == case_source.name
    assert verified["integrity_state"] == "VERIFIED"
    assert verified["publication_state"] == "WITHHELD"
    assert verified["release_ready"] is False


def test_case_build_ignores_stale_checked_in_walmart_forecast_json(tmp_path: Path) -> None:
    case_dir = _copy_case(WALMART_CONDITIONAL, tmp_path / "source")
    stale_path = case_dir / "02_financial_core" / "conditional_linked_forecast.json"
    stale = _read_json(stale_path)
    stale["periods"][0]["income_statement"]["net_sales"] = "0.0000"
    stale_path.write_text(json.dumps(stale, indent=2) + "\n", encoding="utf-8")

    stage = build_case(case_dir, tmp_path / "build")
    fresh = _read_json(stage / "outputs" / "m1" / "conditional_linked_forecast.json")
    assert fresh["periods"][0]["income_statement"]["net_sales"] == "558976176000.0000"
    assert _read_json(stale_path)["periods"][0]["income_statement"]["net_sales"] == "0.0000"


def test_same_input_has_deterministic_hashes_across_fresh_build_roots(tmp_path: Path) -> None:
    case_dir = _copy_case(ORION, tmp_path / "source")
    first = build_case(case_dir, tmp_path / "build_one")
    second = build_case(case_dir, tmp_path / "build_two")

    first_manifest = _read_json(first / "release_manifest.json")
    second_manifest = _read_json(second / "release_manifest.json")
    assert first.name == second.name
    assert (first / "outputs" / "review_report.json").read_bytes() == (
        second / "outputs" / "review_report.json"
    ).read_bytes()
    assert (first / "outputs" / "review_memo.md").read_bytes() == (
        second / "outputs" / "review_memo.md"
    ).read_bytes()
    for field in (
        "source_snapshot_hash",
        "input_hash",
        "config_hash",
        "formula_or_code_hash",
        "output_hash",
        "memo_hash",
        "content_hash",
        "file_hashes",
        "output_paths",
        "memo_paths",
        "known_limitations",
    ):
        assert first_manifest[field] == second_manifest[field]


def test_case_build_never_overwrites_and_leaves_source_snapshot_unchanged(tmp_path: Path) -> None:
    case_dir = _copy_case(ORION, tmp_path / "source")
    before = _tree_hashes(case_dir)
    stage = build_case(case_dir, tmp_path / "build")
    manifest_bytes = (stage / "release_manifest.json").read_bytes()

    assert _tree_hashes(case_dir) == before
    with pytest.raises(FileExistsError, match="Release stage already exists"):
        build_case(case_dir, tmp_path / "build")
    assert (stage / "release_manifest.json").read_bytes() == manifest_bytes
    assert verify_case_build(stage)["integrity_state"] == "VERIFIED"


def test_verify_case_build_refuses_tampered_artifact_and_cli_returns_controlled_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    case_dir = _copy_case(ORION, tmp_path / "source")
    stage = build_case(case_dir, tmp_path / "build")
    report_path = stage / "outputs" / "review_report.json"
    report_path.write_text(report_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Stage file hashes differ"):
        verify_case_build(stage)
    assert main(["verify-build", str(stage)]) == 2
    assert "ERROR: Stage file hashes differ" in capsys.readouterr().out


def test_build_case_refuses_a_build_root_inside_the_source_case(tmp_path: Path) -> None:
    case_dir = _copy_case(ORION, tmp_path / "source")

    with pytest.raises(ValueError, match="Build root must be outside the source case"):
        build_case(case_dir, case_dir / "build")


@pytest.mark.parametrize(("field", "value"), [
    ("schema_version", 999), ("contract_version", 2.0), ("program_id", "another_program"),
    ("coverage_state", "CASE_EVALUATED"), ("release_id", "r-invented"),
    ("review_state", "HUMAN_APPROVED"),
    ("release_ready", 0), ("reproduction_command", "unrelated command"),
    ("supersedes_release_id", "r-invented"), ("declared_limitations", []),
])
def test_verify_case_build_rejects_manifest_contract_or_review_tampering(
    tmp_path: Path, field: str, value: object,
) -> None:
    case_dir = _copy_case(ORION, tmp_path / "source")
    stage = build_case(case_dir, tmp_path / "build")
    path = stage / "release_manifest.json"
    manifest = _read_json(path)
    manifest[field] = value
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="Build manifest|no longer matches"):
        verify_case_build(stage)


@pytest.mark.parametrize(
    ("case_source", "steps", "message"),
    [
        (ORION, ["not_a_build_step"], "Unknown build steps"),
        (ORION, ["conditional_valuation", "core_cash"], "conditional_valuation requires core_cash first"),
        (FORD, ["dfs_reproduction"], "Build step dfs_reproduction requires active module M2"),
        (FORD, ["capital_evidence"], "Build step capital_evidence requires active module M2"),
    ],
    ids=["unknown-step", "wrong-order", "inactive-module", "inactive-capital-evidence"],
)
def test_case_build_rejects_invalid_or_out_of_scope_recipe(
    tmp_path: Path, case_source: Path, steps: list[str], message: str
) -> None:
    case_dir = _copy_case(case_source, tmp_path / "source")
    recipe_path = case_dir / "00_charter" / "build_recipe.json"
    recipe_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "steps": steps,
                "scope_limitations": ["Test-only malformed recipe."],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        build_case(case_dir, tmp_path / "build")
    assert not (tmp_path / "build" / case_dir.name).exists()


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("testability_state", "NOT_A_CREDIT_STATE", "NOT_A_CREDIT_STATE"),
        ("direction", "SIDEWAYS", "SIDEWAYS"),
    ],
    ids=["testability", "direction"],
)
def test_malformed_credit_states_fail_closed_without_staging_a_bundle(
    tmp_path: Path,
    field: str,
    replacement: str,
    message: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    case_dir = _copy_case(FORD, tmp_path / "source")
    covenants_path = case_dir / "05_m3_credit_liquidity_claims" / "covenants.csv"
    with covenants_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames
        rows = list(reader)
    assert columns is not None
    rows[0][field] = replacement
    with covenants_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    assert main(["build-case", str(case_dir), "--build-root", str(tmp_path / "build")]) == 2
    output = capsys.readouterr().out
    assert "ERROR:" in output
    assert message in output
    assert not (tmp_path / "build" / case_dir.name).exists()


def test_missing_credit_covenant_column_is_a_controlled_cli_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    case_dir = _copy_case(FORD, tmp_path / "source")
    covenants_path = case_dir / "05_m3_credit_liquidity_claims" / "covenants.csv"
    with covenants_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames
        rows = list(reader)
    assert columns is not None
    columns.remove("direction")
    with covenants_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows({column: row[column] for column in columns} for row in rows)

    assert main(["build-case", str(case_dir), "--build-root", str(tmp_path / "build")]) == 2
    assert "ERROR: Missing credit CSV columns" in capsys.readouterr().out
    assert not (tmp_path / "build" / case_dir.name).exists()
