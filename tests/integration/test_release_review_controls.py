"""Generated review reports must remain stronger than manually edited PASS gates."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from versioned_finance_core.contracts.json_io import strict_json_loads
from versioned_finance_core.orchestration import release
from versioned_finance_core.orchestration.scaffold import initialize_case
from versioned_finance_core.validation.gates import load_gate_results

ROOT = Path(__file__).parents[2]
TEMPLATE = ROOT / "cases" / "_template"
MEMO = "03_m1_operating_forecast_valuation/memo.md"
OUTPUT = "outputs/control_output.json"
REPORT = "outputs/review_report.json"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _control_case(tmp_path: Path) -> tuple[Path, Path, Path]:
    case_dir = initialize_case("review_control", tmp_path / "cases", TEMPLATE)
    case_path = case_dir / "00_charter" / "case.json"
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case.update(
        decision_question="Does the generated review control block publication?",
        perspective_id="CORPORATE_VALUE",
        as_of_date="2025-01-01",
        analysis_cutoff="2025-01-01T00:00:00+00:00",
        horizon_end="2026-01-01",
        economic_scope_id="REVIEW_CONTROL_SCOPE",
        jurisdiction="TEST_ONLY",
        functional_currency="USD",
        reporting_currency="USD",
        active_modules=["M1"],
    )
    _write_json(case_path, case)

    activation_path = case_dir / "00_charter" / "activation_gates.json"
    activation = json.loads(activation_path.read_text(encoding="utf-8"))
    for gate in activation["case_gates"]:
        gate["status"] = "PASS"
        gate["evidence"] = "Synthetic release-control fixture"
    activation["module_states"]["M1_VALUATION"] = "PASS"
    _write_json(activation_path, activation)

    policy = json.loads((ROOT / "config" / "defaults" / "release_gates.json").read_text(
        encoding="utf-8"
    ))
    gate_path = case_dir / "07_validation_governance" / "gate_results.csv"
    with gate_path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.writer(target)
        writer.writerow(
            ["gate_id", "module_id", "status", "evidence", "limitation", "evaluated_at"]
        )
        for gate_id in policy["common_gates"]:
            writer.writerow([gate_id, "", "PASS", "Synthetic release-control fixture", "", ""])
        writer.writerow(["M1_VALUATION", "M1", "PASS", "Synthetic release-control fixture", "", ""])

    (case_dir / MEMO).write_text(
        "# Synthetic review-control memo\n\noutput_id: control_output\n", encoding="utf-8"
    )
    output_path = tmp_path / "control_output.json"
    output_path.write_text('{"output_id":"control_output","value":"1"}\n', encoding="utf-8")
    report_path = tmp_path / "review_report.json"
    return case_dir, output_path, report_path


def _report(case_dir: Path, *, blockers: object = ()) -> dict[str, object]:
    case = json.loads((case_dir / "00_charter" / "case.json").read_text(encoding="utf-8"))
    return {
        "schema_version": 1,
        "kind": "CASE_BUILD_REVIEW",
        "case_id": case["case_id"],
        "analysis_cutoff": case["analysis_cutoff"],
        "expected_modules": case["active_modules"],
        "publication_state": "WITHHELD",
        "release_blockers": list(blockers) if isinstance(blockers, tuple) else blockers,
    }


def _options(output_path: Path, report_path: Path, *, select_report: bool = True) -> dict[str, object]:
    output_paths = [OUTPUT, MEMO]
    if select_report:
        output_paths.append(REPORT)
    return {
        "output_paths": tuple(output_paths),
        "memo_paths": (MEMO,),
        "external_outputs": {OUTPUT: output_path, REPORT: report_path},
        "reproduction_command": "python -m pytest tests/integration/test_release_review_controls.py",
    }


def test_pipeline_review_blocker_overrides_passing_gate_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_dir, output_path, report_path = _control_case(tmp_path)
    monkeypatch.setattr(release, "_source_snapshot_fingerprint", lambda *_: ("a" * 64, []))

    _write_json(report_path, _report(case_dir, blockers=()))
    ready = release.build_manifest(case_dir, **_options(output_path, report_path))
    assert ready["release_ready"], ready["known_limitations"]

    _write_json(report_path, _report(case_dir, blockers=("M1 eligibility is WITHHELD",)))
    blocked = release.build_manifest(case_dir, **_options(output_path, report_path))
    assert not blocked["release_ready"]
    assert "Pipeline review report blocks release: M1 eligibility is WITHHELD" in blocked[
        "known_limitations"
    ]
    assert all(gate["status"] == "PASS" for gate in blocked["gate_results"])


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema_version", True, "unsupported schema_version"),
        ("kind", "OTHER_REPORT", "invalid kind"),
        ("case_id", "other_case", "case_id differs"),
        ("analysis_cutoff", "2025-01-02T00:00:00+00:00", "analysis_cutoff differs"),
        ("expected_modules", [], "expected_modules differ"),
        ("publication_state", "PUBLISHED", "publication_state must be WITHHELD"),
        ("release_blockers", [""], "release_blockers contains a blank"),
    ],
)
def test_pipeline_review_report_contract_is_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
    message: str,
) -> None:
    case_dir, output_path, report_path = _control_case(tmp_path)
    monkeypatch.setattr(release, "_source_snapshot_fingerprint", lambda *_: ("a" * 64, []))
    report = _report(case_dir, blockers=())
    report[field] = value
    _write_json(report_path, report)

    manifest = release.build_manifest(case_dir, **_options(output_path, report_path))
    assert not manifest["release_ready"]
    assert any(message in issue for issue in manifest["known_limitations"])


def test_existing_pipeline_review_report_must_be_selected(tmp_path: Path) -> None:
    case_dir, output_path, report_path = _control_case(tmp_path)
    _write_json(report_path, _report(case_dir, blockers=()))

    manifest = release.build_manifest(
        case_dir, **_options(output_path, report_path, select_report=False)
    )
    assert not manifest["release_ready"]
    assert any("exists but is not selected as an output" in issue for issue in manifest["known_limitations"])


def test_pipeline_review_report_invalid_json_fails_closed(tmp_path: Path) -> None:
    case_dir, output_path, report_path = _control_case(tmp_path)
    report_path.write_text("{", encoding="utf-8")

    manifest = release.build_manifest(case_dir, **_options(output_path, report_path))
    assert not manifest["release_ready"]
    assert any("invalid JSON" in issue for issue in manifest["known_limitations"])


def test_duplicate_review_blocker_key_cannot_hide_a_withheld_control(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_dir, output_path, report_path = _control_case(tmp_path)
    monkeypatch.setattr(release, "_source_snapshot_fingerprint", lambda *_: ("a" * 64, []))
    report = _report(case_dir, blockers=())
    report.pop("release_blockers")
    report_path.write_text(
        json.dumps(report, ensure_ascii=False)[:-1]
        + ',"release_blockers":["M1 eligibility is WITHHELD"],"release_blockers":[]}',
        encoding="utf-8",
    )

    manifest = release.build_manifest(case_dir, **_options(output_path, report_path))
    assert not manifest["release_ready"]
    assert any("Duplicate JSON object key: release_blockers" in issue
               for issue in manifest["known_limitations"])


def test_duplicate_gate_policy_key_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    case_dir, output_path, report_path = _control_case(tmp_path)
    monkeypatch.setattr(release, "_source_snapshot_fingerprint", lambda *_: ("a" * 64, []))
    _write_json(report_path, _report(case_dir, blockers=()))
    policy = json.loads((ROOT / "config" / "defaults" / "release_gates.json").read_text(
        encoding="utf-8"
    ))
    policy_path = tmp_path / "duplicate_release_gates.json"
    policy_path.write_text(
        json.dumps(policy, ensure_ascii=False)[:-1] + ',"schema_version":2}', encoding="utf-8"
    )

    manifest = release.build_manifest(
        case_dir, gate_config_path=policy_path, **_options(output_path, report_path)
    )
    assert not manifest["release_ready"]
    assert any("Release gate policy is unavailable or invalid: Duplicate JSON object key: schema_version"
               in issue for issue in manifest["known_limitations"])


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ('{"nested":{"control":1,"control":2}}', "Duplicate JSON object key: control"),
        ('{"value":NaN}', "Non-finite JSON numeric constant is not allowed: NaN"),
        ('{"value":Infinity}', "Non-finite JSON numeric constant is not allowed: Infinity"),
        ('{"value":-Infinity}', "Non-finite JSON numeric constant is not allowed: -Infinity"),
    ],
)
def test_strict_json_loader_rejects_ambiguous_or_nonfinite_values(
    payload: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        strict_json_loads(payload)


def test_duplicate_gate_status_column_fails_closed_instead_of_masking_withheld(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_dir, output_path, report_path = _control_case(tmp_path)
    monkeypatch.setattr(release, "_source_snapshot_fingerprint", lambda *_: ("a" * 64, []))
    _write_json(report_path, _report(case_dir, blockers=()))
    policy = json.loads((ROOT / "config" / "defaults" / "release_gates.json").read_text(
        encoding="utf-8"
    ))
    gate_path = case_dir / "07_validation_governance" / "gate_results.csv"
    with gate_path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.writer(target)
        writer.writerow(
            ["gate_id", "module_id", "status", "status", "evidence", "limitation", "evaluated_at"]
        )
        for gate_id in policy["common_gates"]:
            writer.writerow([gate_id, "", "WITHHELD", "PASS", "Synthetic fixture", "", ""])
        writer.writerow(["M1_VALUATION", "M1", "WITHHELD", "PASS", "Synthetic fixture", "", ""])

    manifest = release.build_manifest(case_dir, **_options(output_path, report_path))
    assert not manifest["release_ready"]
    assert any("gate_results.csv has duplicate columns" in issue
               for issue in manifest["known_limitations"])


def test_duplicate_review_finding_status_column_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_dir, output_path, report_path = _control_case(tmp_path)
    monkeypatch.setattr(release, "_source_snapshot_fingerprint", lambda *_: ("a" * 64, []))
    _write_json(report_path, _report(case_dir, blockers=()))
    findings = case_dir / "07_validation_governance" / "review_findings.csv"
    with findings.open("w", newline="", encoding="utf-8") as target:
        writer = csv.writer(target)
        writer.writerow([
            "finding_id", "reviewer", "severity", "finding", "evidence", "response",
            "resolution", "retest_result", "status", "status",
        ])
        writer.writerow([
            "FINDING-1", "synthetic reviewer", "BLOCKING", "must remain blocked",
            "synthetic evidence", "synthetic response", "synthetic resolution", "synthetic retest",
            "OPEN", "CLOSED",
        ])

    manifest = release.build_manifest(case_dir, **_options(output_path, report_path))
    assert not manifest["release_ready"]
    assert any("review_findings.csv has duplicate columns" in issue
               for issue in manifest["known_limitations"])


def test_gate_and_review_csv_row_widths_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate_path = tmp_path / "gate_results.csv"
    gate_path.write_text("gate_id,status\nCOMMON,PASS,hidden\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid row width"):
        load_gate_results(gate_path)

    case_dir, output_path, report_path = _control_case(tmp_path / "case")
    monkeypatch.setattr(release, "_source_snapshot_fingerprint", lambda *_: ("a" * 64, []))
    _write_json(report_path, _report(case_dir, blockers=()))
    findings = case_dir / "07_validation_governance" / "review_findings.csv"
    findings.write_text(
        "finding_id,reviewer,severity,finding,evidence,response,resolution,retest_result,status\n"
        "FINDING-1,reviewer,BLOCKING,finding,evidence,response,resolution,retest,OPEN,hidden\n",
        encoding="utf-8",
    )

    manifest = release.build_manifest(case_dir, **_options(output_path, report_path))
    assert not manifest["release_ready"]
    assert any("review_findings.csv has invalid row width" in issue
               for issue in manifest["known_limitations"])


def test_stage_failure_does_not_leave_a_partial_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_dir, output_path, report_path = _control_case(tmp_path)
    _write_json(report_path, _report(case_dir, blockers=()))

    def fail_copy(*_: object, **__: object) -> None:
        raise OSError("synthetic copy failure")

    monkeypatch.setattr(release.shutil, "copy2", fail_copy)
    stage_root = tmp_path / "stage"
    with pytest.raises(OSError, match="synthetic copy failure"):
        release.stage_release(case_dir, stage_root, **_options(output_path, report_path))
    case_stage_root = stage_root / "review_control"
    assert not case_stage_root.exists() or list(case_stage_root.iterdir()) == []
