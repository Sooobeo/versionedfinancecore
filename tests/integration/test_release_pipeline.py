"""Synthetic control tests; these fixtures make no real company claim."""

from __future__ import annotations

import csv
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from versioned_finance_core.cli import main
from versioned_finance_core.contracts import GateStatus
from versioned_finance_core.contracts.enums import AccessClass, PublicationStatus
from versioned_finance_core.evidence import (
    ProvenancedFact,
    RawFact,
    SourceMetadata,
    append_raw_facts,
    load_source_ledger,
    register_source_locator,
)
from versioned_finance_core.orchestration import release
from versioned_finance_core.orchestration.scaffold import initialize_case
from versioned_finance_core.validation import GateResult, assess_release_gates

ROOT = Path(__file__).parents[2]
TEMPLATE = ROOT / "cases" / "_template"
MEMO = "03_m1_operating_forecast_valuation/memo.md"
OUTPUT = "outputs/core_result.json"


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _synthetic_case(
    tmp_path: Path,
    *,
    access_class: AccessClass = AccessClass.SYNTHETIC_TEST,
    cutoff_eligible: bool = True,
    first_public_at: datetime = datetime(2024, 12, 31, tzinfo=UTC),
    transformation_right: bool = True,
) -> tuple[Path, Path, Path, Path]:
    case_dir = initialize_case("synthetic_case", tmp_path / "cases", TEMPLATE)
    case_path = case_dir / "00_charter" / "case.json"
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case.update(
        decision_question="Synthetic calculation control?",
        perspective_id="CORPORATE_VALUE",
        as_of_date="2025-01-01",
        analysis_cutoff="2025-01-01T00:00:00+00:00",
        horizon_end="2026-01-01",
        economic_scope_id="SYNTHETIC_SCOPE",
        jurisdiction="TEST_ONLY",
        functional_currency="USD",
        reporting_currency="USD",
        active_modules=["M1"],
    )
    _write_json(case_path, case)
    (case_dir / MEMO).write_text(
        "# Synthetic control memo\n\noutput_id: fixture\n",
        encoding="utf-8",
    )

    activation_path = case_dir / "00_charter" / "activation_gates.json"
    activation = json.loads(activation_path.read_text(encoding="utf-8"))
    for gate in activation["case_gates"]:
        gate["status"] = "PASS"
        gate["evidence"] = "Synthetic gate-control fixture"
    activation["module_states"]["M1_VALUATION"] = "PASS"
    _write_json(activation_path, activation)

    gate_config = json.loads((ROOT / "config" / "defaults" / "release_gates.json").read_text(
        encoding="utf-8"
    ))
    gate_path = case_dir / "07_validation_governance" / "gate_results.csv"
    with gate_path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.writer(target)
        writer.writerow(
            ["gate_id", "module_id", "status", "evidence", "limitation", "evaluated_at"]
        )
        for gate_id in gate_config["common_gates"]:
            writer.writerow([gate_id, "", "PASS", "Synthetic gate-control fixture", "", ""])
        writer.writerow(
            ["M1_VALUATION", "M1", "PASS", "Synthetic gate-control fixture", "", ""]
        )

    register_source_locator(
        case_dir / "01_evidence_core",
        SourceMetadata(
            source_id="fixture_source",
            access_class=access_class,
            authority="Synthetic test fixture",
            title="Synthetic receipt control",
            url="https://example.invalid/fixture",
            document_id="",
            retrieved_at=first_public_at + timedelta(hours=1),
            publication_status=PublicationStatus.FILED,
            first_public_at=first_public_at,
            retention_right=False,
            transformation_right=transformation_right,
            redistribution_right=False,
            cutoff_eligible=cutoff_eligible,
        ),
        "a" * 64,
    )

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    _write_json(config_dir / "release_gates.json", gate_config)
    code_dir = tmp_path / "code"
    code_dir.mkdir()
    (code_dir / "model.py").write_text("VALUE = 1\n", encoding="utf-8")
    output_path = tmp_path / "core_result.json"
    output_path.write_text('{"output_id":"fixture","value":"1"}\n', encoding="utf-8")
    return case_dir, config_dir, code_dir, output_path


def _options(config_dir: Path, code_dir: Path, output_path: Path) -> dict[str, object]:
    return {
        "output_paths": (OUTPUT, MEMO),
        "memo_paths": (MEMO,),
        "external_outputs": {OUTPUT: output_path},
        "config_dir": config_dir,
        "code_dir": code_dir,
        "reproduction_command": "python -m pytest tests/integration/test_release_pipeline.py",
    }


def _raw_fixture_fact(source_id: str, snapshot_id: str) -> RawFact:
    return RawFact(
        fact_id="synthetic_fact",
        source_id=source_id,
        snapshot_id=snapshot_id,
        version_id="fixture_version",
        economic_scope_id="SYNTHETIC_SCOPE",
        accounting_scope="CONSOLIDATED",
        metric_id="fixture_metric",
        period_start=date(2024, 1, 1),
        period_end=date(2024, 12, 31),
        period_type="FY",
        currency="USD",
        unit="USD",
        raw_value="1",
        raw_label="Synthetic test value",
        extraction_method="TEST_FIXTURE",
        review_status="TEST_ONLY",
        raw_account_id="fixture_account",
    )


def test_gate_policy_fails_closed_on_missing_duplicate_and_not_applicable() -> None:
    passing = GateResult("COMMON", GateStatus.PASS, evidence="control")
    module = GateResult("M1_VALUATION", GateStatus.PASS, evidence="control", module_id="M1")
    policy = {
        "required_common_gates": ("COMMON",),
        "active_modules": ("M1",),
        "required_module_gates": {"M1": ("M1_VALUATION",)},
        "require_evidence": True,
    }
    assert assess_release_gates([passing, module], **policy).allowed
    assert not assess_release_gates([passing], **policy).allowed
    assert not assess_release_gates([passing, module, module], **policy).allowed
    na = GateResult("COMMON", GateStatus.NOT_APPLICABLE, evidence="control")
    assert not assess_release_gates([na, module], **policy).allowed
    assert not assess_release_gates([GateResult("COMMON", GateStatus.PASS), module], **policy).allowed


def test_manifest_hashes_are_reproducible_and_exclude_sensitive_files(tmp_path: Path) -> None:
    case_dir, config_dir, code_dir, output_path = _synthetic_case(tmp_path)
    (case_dir / "private").mkdir()
    (case_dir / "private" / "restricted.csv").write_text("restricted", encoding="utf-8")
    (case_dir / "01_evidence_core" / "raw_snapshots" / "receipt.txt").write_text(
        "raw receipt", encoding="utf-8"
    )
    (case_dir / "local.secret.txt").write_text("secret", encoding="utf-8")
    options = _options(config_dir, code_dir, output_path)
    first = release.build_manifest(case_dir, **options)
    second = release.build_manifest(case_dir, **options)
    assert first["publication_state"] == "WITHHELD"
    assert not first["release_ready"]
    assert first["content_hash"] == second["content_hash"]
    assert first["output_hash"] == second["output_hash"]
    assert first["source_snapshot_hash"] == second["source_snapshot_hash"]
    assert OUTPUT in first["file_hashes"]
    assert not any(
        "raw_snapshots" in name or "private" in name or "secret" in name
        for name in first["file_hashes"]
    )
    output_path.write_text('{"output_id":"fixture","value":"2"}\n', encoding="utf-8")
    changed = release.build_manifest(case_dir, **options)
    assert changed["output_hash"] != first["output_hash"]
    assert changed["content_hash"] != first["content_hash"]


def test_manifest_staging_never_overwrites_and_withholds_synthetic_case(tmp_path: Path) -> None:
    case_dir, config_dir, code_dir, output_path = _synthetic_case(tmp_path)
    options = _options(config_dir, code_dir, output_path)
    manifest_path = release.write_manifest(case_dir, **options)
    assert manifest_path.is_relative_to(tmp_path / "build")
    with pytest.raises(FileExistsError):
        release.write_manifest(case_dir, **options)
    with pytest.raises(FileExistsError):
        release.write_manifest(case_dir, output=manifest_path, **options)

    stage = release.stage_release(case_dir, tmp_path / "stage", **options)
    assert (stage / OUTPUT).is_file()
    assert not (stage / "01_evidence_core" / "raw_snapshots" / "README.md").exists()
    with pytest.raises(ValueError, match="WITHHELD"):
        release.publish_release(stage, tmp_path / "releases", config_dir=config_dir, code_dir=code_dir)
    assert not (tmp_path / "releases").exists()


def test_publish_validated_temporary_control_release_is_immutable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_dir, config_dir, code_dir, output_path = _synthetic_case(tmp_path)
    options = _options(config_dir, code_dir, output_path)
    # The temporary fixture stays explicitly synthetic. Only the rights/provenance
    # predicate is mocked so this test can exercise the publication file controls.
    monkeypatch.setattr(release, "_source_snapshot_fingerprint", lambda *_: ("a" * 64, []))
    stage = release.stage_release(case_dir, tmp_path / "stage", **options)
    manifest = json.loads((stage / "release_manifest.json").read_text(encoding="utf-8"))
    assert manifest["release_ready"], manifest["known_limitations"]
    fresh = release.build_manifest(
        stage,
        output_paths=manifest["output_paths"],
        memo_paths=manifest["memo_paths"],
        config_dir=config_dir,
        code_dir=code_dir,
        reproduction_command=manifest["reproduction_command"],
    )
    assert fresh["known_limitations"] == manifest["known_limitations"]
    target = release.publish_release(
        stage, tmp_path / "releases", config_dir=config_dir, code_dir=code_dir
    )
    published = json.loads((target / "release_manifest.json").read_text(encoding="utf-8"))
    assert published["publication_state"] == "PUBLISHED"
    assert published["content_hash"] == manifest["content_hash"]
    assert target.name == published["release_id"]
    with pytest.raises(FileExistsError):
        release.publish_release(stage, tmp_path / "releases", config_dir=config_dir, code_dir=code_dir)
    # Let the test runner clean up this temporary, synthetic publication on Windows.
    for path in target.rglob("*"):
        if path.is_file():
            path.chmod(0o666)


def test_publish_rejects_stage_file_tampering(tmp_path: Path) -> None:
    case_dir, config_dir, code_dir, output_path = _synthetic_case(tmp_path)
    stage = release.stage_release(case_dir, tmp_path / "stage", **_options(config_dir, code_dir, output_path))
    (stage / OUTPUT).write_text("altered", encoding="utf-8")
    with pytest.raises(ValueError, match="hashes differ"):
        release.publish_release(stage, tmp_path / "releases", config_dir=config_dir, code_dir=code_dir)


def test_cutoff_and_rights_metadata_fail_closed(tmp_path: Path) -> None:
    late_case, late_config, late_code, late_output = _synthetic_case(
        tmp_path / "late",
        access_class=AccessClass.PUBLIC_COMPANY,
        first_public_at=datetime(2025, 1, 2, tzinfo=UTC),
    )
    late = release.build_manifest(late_case, **_options(late_config, late_code, late_output))
    assert not late["release_ready"]
    assert any("after the analysis cutoff" in item for item in late["known_limitations"])

    ineligible_case, config_dir, code_dir, output = _synthetic_case(
        tmp_path / "ineligible", cutoff_eligible=False
    )
    ineligible = release.build_manifest(ineligible_case, **_options(config_dir, code_dir, output))
    assert any("not cutoff eligible" in item for item in ineligible["known_limitations"])

    ledger = ineligible_case / "01_evidence_core" / "source_ledger.csv"
    with ledger.open("r", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        rows = list(reader)
        columns = reader.fieldnames
    assert columns is not None
    rows[0]["redistribution_right"] = "MAYBE"
    with ledger.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    invalid = release.build_manifest(ineligible_case, **_options(config_dir, code_dir, output))
    assert any("failed validation" in item for item in invalid["known_limitations"])
    with pytest.raises(ValueError, match="YES or NO"):
        release.stage_release(ineligible_case, tmp_path / "stage", **_options(config_dir, code_dir, output))


def test_licensed_raw_facts_never_enter_release_staging(tmp_path: Path) -> None:
    case_dir, config_dir, code_dir, output_path = _synthetic_case(
        tmp_path, access_class=AccessClass.LICENSED_OPTIONAL
    )
    evidence_dir = case_dir / "01_evidence_core"
    receipt = load_source_ledger(evidence_dir)[0]
    append_raw_facts(evidence_dir, [_raw_fixture_fact(receipt.source_id, receipt.snapshot_id)])
    manifest = release.build_manifest(case_dir, **_options(config_dir, code_dir, output_path))
    assert not manifest["release_ready"]
    assert any("cannot support a public case release" in item for item in manifest["known_limitations"])
    with pytest.raises(ValueError, match="Restricted or licensed source"):
        release.stage_release(
            case_dir, tmp_path / "stage", **_options(config_dir, code_dir, output_path)
        )
    assert not (tmp_path / "stage").exists()


def test_raw_fact_without_transformation_right_is_not_staged(tmp_path: Path) -> None:
    case_dir, config_dir, code_dir, output_path = _synthetic_case(
        tmp_path,
        access_class=AccessClass.PUBLIC_COMPANY,
        transformation_right=False,
    )
    evidence_dir = case_dir / "01_evidence_core"
    receipt = load_source_ledger(evidence_dir)[0]
    row = ProvenancedFact(
        _raw_fixture_fact(receipt.source_id, receipt.snapshot_id), receipt
    ).as_csv_row()
    raw_path = evidence_dir / "raw_facts.csv"
    with raw_path.open("r", newline="", encoding="utf-8") as source:
        columns = next(csv.reader(source))
    with raw_path.open("a", newline="", encoding="utf-8") as target:
        csv.DictWriter(target, fieldnames=columns).writerow(row)
    with pytest.raises(ValueError, match="transformation rights"):
        release.stage_release(case_dir, tmp_path / "stage", **_options(config_dir, code_dir, output_path))
    assert not (tmp_path / "stage").exists()


def test_material_review_finding_overrides_a_manual_pass_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_dir, config_dir, code_dir, output_path = _synthetic_case(tmp_path)
    options = _options(config_dir, code_dir, output_path)
    monkeypatch.setattr(release, "_source_snapshot_fingerprint", lambda *_: ("a" * 64, []))
    assert release.build_manifest(case_dir, **options)["release_ready"]

    path = case_dir / "07_validation_governance" / "review_findings.csv"
    with path.open("r", encoding="utf-8", newline="") as source:
        fieldnames = next(csv.reader(source))
    finding = {
        "finding_id": "SYN-001",
        "reviewed_at": "2025-01-01T00:00:00+00:00",
        "reviewer": "synthetic_challenger",
        "scope": "fixture",
        "severity": "BLOCKING",
        "finding": "Synthetic source-to-model mismatch",
        "evidence": "synthetic_check_id",
        "response": "",
        "resolution": "",
        "retest_result": "",
        "remaining_limitation": "",
        "status": "OPEN",
    }

    def write_finding() -> None:
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow(finding)

    write_finding()
    open_manifest = release.build_manifest(case_dir, **options)
    assert not open_manifest["release_ready"]
    assert any("Material review finding remains unresolved: SYN-001" in issue
               for issue in open_manifest["known_limitations"])

    finding.update(status="CLOSED", response="Recomputed from source",
                   resolution="Fixed mapping", retest_result="")
    write_finding()
    untested = release.build_manifest(case_dir, **options)
    assert not untested["release_ready"]
    assert any("lacks challenge/response/retest: retest_result" in issue
               for issue in untested["known_limitations"])

    finding["retest_result"] = "Synthetic reconciliation passed"
    write_finding()
    assert release.build_manifest(case_dir, **options)["release_ready"]


def test_memo_must_reference_a_selected_canonical_output_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_dir, config_dir, code_dir, output_path = _synthetic_case(tmp_path)
    options = _options(config_dir, code_dir, output_path)
    monkeypatch.setattr(release, "_source_snapshot_fingerprint", lambda *_: ("a" * 64, []))
    assert release.build_manifest(case_dir, **options)["release_ready"]

    memo_path = case_dir / MEMO
    memo_path.write_text("# Synthetic memo\n\noutput_id: invented\n", encoding="utf-8")
    mismatch = release.build_manifest(case_dir, **options)
    assert not mismatch["release_ready"]
    assert any("references an unselected output ID: invented" in issue
               for issue in mismatch["known_limitations"])

    memo_path.write_text("# Synthetic memo\n\nA number: 1\n", encoding="utf-8")
    unlinked = release.build_manifest(case_dir, **options)
    assert not unlinked["release_ready"]
    assert any("Memo has no canonical output ID reference" in issue
               for issue in unlinked["known_limitations"])

    memo_path.write_text("# Synthetic memo\n\noutput_id: fixture\n", encoding="utf-8")
    output_path.write_text('{"output_id":"revised","value":"1"}\n', encoding="utf-8")
    stale = release.build_manifest(case_dir, **options)
    assert not stale["release_ready"]
    assert any("references an unselected output ID: fixture" in issue
               for issue in stale["known_limitations"])


def test_validate_case_release_ready_checks_gates_and_returns_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    case_dir, _, _, _ = _synthetic_case(tmp_path)
    monkeypatch.setattr(release, "_source_snapshot_fingerprint", lambda *_: ("a" * 64, []))
    assert main(["validate-case", str(case_dir), "--release-ready"]) == 0
    assert "release gates are valid" in capsys.readouterr().out

    gates_path = case_dir / "07_validation_governance" / "gate_results.csv"
    with gates_path.open("r", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        fieldnames = reader.fieldnames
        rows = list(reader)
    assert fieldnames is not None
    next(row for row in rows if row["gate_id"] == "M1_VALUATION")["status"] = "WITHHELD"
    with gates_path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    assert main(["validate-case", str(case_dir)]) == 0
    assert "Case structure is valid" in capsys.readouterr().out
    assert main(["validate-case", str(case_dir), "--release-ready"]) == 1
    output = capsys.readouterr().out
    assert "M1_VALUATION" in output
    assert "WITHHELD" in output
    assert "Case structure is valid" not in output
