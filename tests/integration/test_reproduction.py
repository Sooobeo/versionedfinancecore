"""Automated handover is repeatable and cannot waive human or evidence gates."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from versioned_finance_core.cli import main
from versioned_finance_core.orchestration import reproduction

ORION = Path(__file__).parents[2] / "cases/orion_jincheon_2026h1"


def _files(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def test_two_build_handover_preserves_case_and_is_deterministic(tmp_path: Path) -> None:
    before = _files(ORION)
    first = reproduction.reproduce_case(ORION, tmp_path / "first_handover")
    second = reproduction.reproduce_case(ORION, tmp_path / "second_handover")
    verified = reproduction.verify_reproduction(first)
    assert verified["automated_reproduction_state"] == "PASS"
    assert verified["human_review_state"] == "NOT_PERFORMED"
    assert verified["publication_state"] == "WITHHELD"
    assert (first / "reproduction_report.json").read_bytes() == (
        second / "reproduction_report.json"
    ).read_bytes()
    assert (first / "reproduction_memo.md").read_bytes() == (
        second / "reproduction_memo.md"
    ).read_bytes()
    report = json.loads((first / "reproduction_report.json").read_text(encoding="utf-8"))
    assert report["remaining_release_blockers"]
    assert report["release_ready"] is False
    assert before == _files(ORION)
    with pytest.raises(FileExistsError, match="already exists"):
        reproduction.reproduce_case(ORION, first)


@pytest.mark.parametrize("target", [
    "report", "memo", "extra_file", "stage", "schema_as_bool", "readiness_as_int",
])
def test_tampered_handover_is_rejected(tmp_path: Path, target: str) -> None:
    bundle = reproduction.reproduce_case(ORION, tmp_path / "bundle")
    report_path = bundle / "reproduction_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if target == "report":
        report["human_review_state"] = "PASS"
        report_path.write_text(json.dumps(report), encoding="utf-8")
    elif target in {"schema_as_bool", "readiness_as_int"}:
        if target == "schema_as_bool":
            report["schema_version"] = True
        else:
            report["release_ready"] = 0
        report_path.write_text(json.dumps(report), encoding="utf-8")
    elif target == "memo":
        (bundle / "reproduction_memo.md").write_text("Approved!", encoding="utf-8")
    elif target == "extra_file":
        (bundle / "extra.txt").write_text("untracked", encoding="utf-8")
    else:
        (bundle / report["second_stage"] / "outputs/review_memo.md").write_text(
            "Changed calculation memo", encoding="utf-8",
        )
    with pytest.raises(ValueError):
        reproduction.verify_reproduction(bundle)


@pytest.mark.parametrize("stage", ["../outside", "/outside", "first", "first/../outside", "first\\x"])
def test_malicious_stage_reference_fails_closed(tmp_path: Path, stage: str) -> None:
    (tmp_path / "reproduction_report.json").write_text(
        json.dumps({"first_stage": stage, "second_stage": "second/a/b"}), encoding="utf-8",
    )
    with pytest.raises(ValueError):
        reproduction.verify_reproduction(tmp_path)


def test_failure_during_second_build_leaves_no_final_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = reproduction.build_case
    calls = 0

    def fail_second(case_dir: Path, build_root: Path) -> Path:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("Synthetic second-build failure")
        return original(case_dir, build_root)

    monkeypatch.setattr(reproduction, "build_case", fail_second)
    with pytest.raises(ValueError, match="second-build failure"):
        reproduction.reproduce_case(ORION, tmp_path / "bundle")
    assert not (tmp_path / "bundle").exists()
    assert not list(tmp_path.glob(".vfc-reproduction-*"))


def test_handover_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bundle = tmp_path / "bundle"
    assert main(["reproduce-case", str(ORION), "--output-dir", str(bundle)]) == 0
    assert "human review was not performed" in capsys.readouterr().out
    assert main(["verify-reproduction", str(bundle)]) == 0
    assert "Human review: NOT_PERFORMED; publication: WITHHELD" in capsys.readouterr().out
    assert main(["reproduce-case", str(ORION), "--output-dir", str(bundle)]) == 2


def test_source_case_cannot_be_handover_destination() -> None:
    with pytest.raises(ValueError, match="separate"):
        reproduction.reproduce_case(ORION, ORION / "handover")
