"""Synthetic D0 path from immutable evidence to staged Core and memo output."""

from __future__ import annotations

import csv
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from versioned_finance_core.contracts.enums import AccessClass, PublicationStatus
from versioned_finance_core.evidence import (
    RawFact,
    SourceMetadata,
    append_raw_facts,
    content_path,
    ingest_snapshot,
)
from versioned_finance_core.orchestration.core_build import build_core
from versioned_finance_core.orchestration.release import publish_release, stage_release
from versioned_finance_core.orchestration.scaffold import initialize_case

TEMPLATE = Path(__file__).parents[2] / "cases" / "_template"
ROLES = (
    "opening_cash",
    "operating_cash_flow",
    "investing_cash_flow",
    "financing_cash_flow",
    "fx_and_other",
    "closing_cash",
)
VALUES = {
    "opening_cash": "100",
    "operating_cash_flow": "30",
    "investing_cash_flow": "-10",
    "financing_cash_flow": "5",
    "fx_and_other": "0",
    "closing_cash": "125",
}


def _append_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("r", encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle))
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writerows(rows)


def _synthetic_case(
    tmp_path: Path, *, with_scenario: bool = True, with_assumption: bool = True,
    with_components: bool = False, with_bridge: bool = False,
) -> tuple[Path, Path]:
    case_dir = initialize_case("synthetic_d0", tmp_path / "cases", TEMPLATE)
    case_path = case_dir / "00_charter" / "case.json"
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case.update(
        as_of_date="2027-01-17",
        analysis_cutoff="2027-01-17T00:00:00+00:00",
        economic_scope_id="synthetic_group",
        reporting_currency="USD",
    )
    case_path.write_text(json.dumps(case, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    evidence_dir = case_dir / "01_evidence_core"
    source_file = tmp_path / "synthetic_source.json"
    source_file.write_text(json.dumps(VALUES, sort_keys=True), encoding="utf-8")
    metadata = SourceMetadata(
        source_id="synthetic_financials",
        access_class=AccessClass.SYNTHETIC_TEST,
        authority="Synthetic fixture",
        title="Synthetic cash flow statement",
        url="https://example.invalid/synthetic-d0",
        document_id="SYNTHETIC-D0",
        retrieved_at=datetime(2027, 1, 16, tzinfo=UTC),
        publication_status=PublicationStatus.FILED,
        first_public_at=datetime(2027, 1, 15, tzinfo=UTC),
        period_start=date(2026, 1, 1),
        period_end=date(2026, 12, 31),
        entity_scope="synthetic_group",
        currency="USD",
        unit="USD",
        retention_right=True,
        transformation_right=True,
        redistribution_right=True,
        cutoff_eligible=True,
        notes="SYNTHETIC_TEST only; no real-company claim",
    )
    receipt = ingest_snapshot(evidence_dir, source_file, metadata)
    if with_bridge:
        _append_csv(
            evidence_dir / "scope_bridges.csv",
            [{
                "bridge_id": "synthetic_bridge",
                "economic_scope_id": "synthetic_group",
                "legal_entity_id": "synthetic_legal_entity",
                "relation": "SYNTHETIC_SCOPE_RELATION",
                "source_id": receipt.source_id,
                "snapshot_id": receipt.snapshot_id,
                "content_sha256": receipt.content_sha256,
                "first_public_at": receipt.first_public_at.isoformat(),
                "retrieved_at": receipt.retrieved_at.isoformat(),
                "review_status": "APPROVED",
            }],
        )
    facts: list[RawFact] = []
    mappings: list[dict[str, str]] = []
    metrics: list[dict[str, str]] = []
    for role in ROLES:
        instant = role in {"opening_cash", "closing_cash"}
        period_start = (
            date(2025, 12, 31) if role == "opening_cash"
            else date(2026, 12, 31) if role == "closing_cash"
            else date(2026, 1, 1)
        )
        period_end = date(2025, 12, 31) if role == "opening_cash" else date(2026, 12, 31)
        facts.append(
            RawFact(
                fact_id=f"raw_{role}",
                source_id="synthetic_financials",
                snapshot_id=receipt.snapshot_id,
                version_id="actual_v1",
                economic_scope_id="synthetic_group",
                accounting_scope="CONSOLIDATED",
                metric_id=role,
                period_start=period_start,
                period_end=period_end,
                period_type="INSTANT" if instant else "YEAR",
                currency="USD",
                unit="USD",
                raw_value=VALUES[role],
                raw_label=f"Synthetic {role}",
                extraction_method="synthetic_fixture",
                review_status="REVIEWED_SYNTHETIC",
                legal_entity_id="synthetic_legal_entity" if with_bridge else "",
                economic_legal_scope_bridge_id="synthetic_bridge" if with_bridge else "",
                raw_account_id=role,
                mapping_version=f"map_{role}",
            )
        )
        mappings.append(
            {
                "mapping_id": f"map_{role}",
                "source_id": "synthetic_financials",
                "raw_account_id": role,
                "normalized_metric_id": role,
                "sign_multiplier": "+1",
                "review_status": "APPROVED",
            }
        )
        metrics.append(
            {
                "metric_id": role,
                "grain": "ECONOMIC_SCOPE",
                "period_type": "INSTANT" if instant else "YEAR",
                "currency_policy": "USD",
                "unit": "USD",
                "sign_convention": "SIGNED_CASH",
                "review_status": "APPROVED",
            }
        )
    append_raw_facts(evidence_dir, facts)
    _append_csv(evidence_dir / "mappings.csv", mappings)
    _append_csv(evidence_dir / "metric_dictionary.csv", metrics)

    core_dir = case_dir / "02_financial_core"
    versions = [
        {
            "version_id": "actual_v1",
            "version_type": "PUBLIC_ACTUAL",
            "as_of_date": "2026-12-31",
            "publication_status": "FILED",
            "information_cutoff": "2027-01-17T00:00:00+00:00",
            "immutable": "true",
        }
    ]
    if with_scenario:
        versions.append(
            {
                "version_id": "scenario_v1",
                "version_type": "SCENARIO",
                "as_of_date": "2027-01-17",
                "publication_status": "PRELIMINARY",
                "information_cutoff": "2027-01-17T00:00:00+00:00",
                "immutable": "true",
            }
        )
    _append_csv(core_dir / "versions.csv", versions)
    _append_csv(
        core_dir / "cash_identity_checks.csv",
        [{
            "identity_id": "cash_fy2026",
            "version_id": "actual_v1",
            **{f"{role}_fact_id": f"raw_{role}" for role in ROLES},
        }],
    )
    if with_components:
        _append_csv(
            core_dir / "cash_components.csv",
            [
                {
                    "cash_component_id": f"component_{role}",
                    "display_name": f"Synthetic {role}",
                    "metric_id": role,
                    "tax_basis": "AFTER_TAX",
                    "included_in_fcff": "YES",
                    "included_in_fcfe": "NO",
                    "included_in_cfads": "YES" if role == "operating_cash_flow" else "NO",
                    "included_in_debt_service": "NO",
                    "included_in_liquidity": "YES",
                    "included_in_sources_uses": "NO",
                    "double_count_check": "SYNTHETIC_TEST",
                }
                for role in ("operating_cash_flow", "investing_cash_flow")
            ],
        )
    if with_scenario:
        _append_csv(
            core_dir / "scenarios.csv",
            [{
                "scenario_id": "synthetic_downside",
                "scenario_purpose": "EVIDENCE_DOWNSIDE",
                "version_id": "scenario_v1",
                "driver_id": "operating_cash_flow",
                "period_start": "2026-01-01",
                "period_end": "2026-12-31",
                "input_value": "20",
                "input_unit": "USD",
                "evidence_or_assumption_id": "synthetic_assumption_1",
                "mechanism": "ABSOLUTE_OVERRIDE",
                "dependency_group": "synthetic_demand",
                "review_status": "REVIEWED_SYNTHETIC",
                "baseline_version_id": "actual_v1",
            }],
        )
        if with_assumption:
            _append_csv(
                case_dir / "07_validation_governance" / "assumptions.csv",
                [{
                    "assumption_id": "synthetic_assumption_1",
                    "variable": "operating_cash_flow",
                    "scenario_id": "synthetic_downside",
                    "value": "20",
                    "unit": "USD",
                    "basis": "Synthetic boundary fixture",
                    "source_id": "synthetic_financials",
                    "mechanism": "ABSOLUTE_OVERRIDE",
                    "claim_tag": "A",
                    "status": "REVIEWED_SYNTHETIC",
                }],
            )
    return case_dir, content_path(evidence_dir, receipt)


def test_d0_build_runs_source_to_memo_and_never_overwrites(tmp_path: Path) -> None:
    case_dir, _ = _synthetic_case(tmp_path)
    build_root = tmp_path / "build"
    build_dir = build_core(case_dir, build_root)

    assert build_dir.parent == build_root / "synthetic_d0"
    assert build_dir.name.startswith("core_")
    with (build_dir / "normalized_actuals.csv").open(encoding="utf-8", newline="") as handle:
        normalized = list(csv.DictReader(handle))
    assert len(normalized) == 6
    assert {row["source_fact_id"] for row in normalized} == {f"raw_{role}" for role in ROLES}
    assert {row["snapshot_id"] for row in normalized} == {normalized[0]["snapshot_id"]}

    outputs = json.loads((build_dir / "core_outputs.json").read_text(encoding="utf-8"))
    memo = json.loads((build_dir / "memo_fields.json").read_text(encoding="utf-8"))
    metadata = json.loads((build_dir / "build_metadata.json").read_text(encoding="utf-8"))
    assert outputs["cash_identity"]["residual"] == "0"
    assert outputs["scenario_cash"]["projected_closing_cash"] == "115"
    assert outputs["scenario_cash"]["baseline_output_id"] == outputs["cash_identity"]["output_id"]
    assert [field["output_id"] for field in memo["fields"]] == [
        outputs["cash_identity"]["output_id"], outputs["scenario_cash"]["output_id"]
    ]
    assert [field["value"] for field in memo["fields"]] == ["0", "115"]
    assert metadata["build_state"] == "STAGING_ONLY"
    assert all(len(metadata[key]) == 64 for key in ("input_hash", "code_hash", "output_hash"))
    assert len(metadata["source_snapshot_ids"]) == 1
    assert not metadata["locator_only_snapshot_ids"]
    with pytest.raises(FileExistsError, match="already exists"):
        build_core(case_dir, build_root)


def test_d0_build_content_identity_is_independent_of_staging_path(tmp_path: Path) -> None:
    case_dir, _ = _synthetic_case(tmp_path)
    first = build_core(case_dir, tmp_path / "build_one")
    second = build_core(case_dir, tmp_path / "build_two")
    assert first.name == second.name
    for name in (
        "normalized_actuals.csv", "core_outputs.json", "memo_fields.json",
        "build_metadata.json",
    ):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_d0_build_without_scenario_keeps_memo_on_canonical_identity(tmp_path: Path) -> None:
    case_dir, _ = _synthetic_case(tmp_path, with_scenario=False)
    build_dir = build_core(case_dir, tmp_path / "build")
    outputs = json.loads((build_dir / "core_outputs.json").read_text(encoding="utf-8"))
    memo = json.loads((build_dir / "memo_fields.json").read_text(encoding="utf-8"))
    assert outputs["scenario_cash"] is None
    assert len(memo["fields"]) == 1
    assert memo["fields"][0]["output_id"] == outputs["cash_identity"]["output_id"]


def test_d0_build_rejects_tampered_retained_snapshot(tmp_path: Path) -> None:
    case_dir, content = _synthetic_case(tmp_path)
    content.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="snapshot content hash mismatch"):
        build_core(case_dir, tmp_path / "build")
    assert not (tmp_path / "build").exists()


def test_d0_build_rejects_unresolved_scenario_assumption(tmp_path: Path) -> None:
    case_dir, _ = _synthetic_case(tmp_path, with_assumption=False)
    with pytest.raises(ValueError, match="evidence or assumption ID is unresolved"):
        build_core(case_dir, tmp_path / "build")
    assert not (tmp_path / "build").exists()


def test_d0_build_accepts_cutoff_eligible_direct_source_evidence(tmp_path: Path) -> None:
    case_dir, _ = _synthetic_case(tmp_path, with_assumption=False)
    scenario_path = case_dir / "02_financial_core" / "scenarios.csv"
    with scenario_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames
        rows = list(reader)
    assert header is not None
    rows[0]["evidence_or_assumption_id"] = "synthetic_financials"
    with scenario_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)
    assert build_core(case_dir, tmp_path / "build").is_dir()


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("scenario_id", "other_scenario", "does not match override"),
        ("variable", "investing_cash_flow", "does not match override"),
        ("value", "21", "does not match override"),
        ("unit", "EUR", "does not match override"),
        ("mechanism", "PERCENT_SHOCK", "does not match override"),
        ("status", "DRAFT", "not reviewed or approved"),
    ],
)
def test_d0_build_rejects_assumption_that_differs_from_override(
    tmp_path: Path, field: str, replacement: str, message: str
) -> None:
    case_dir, _ = _synthetic_case(tmp_path)
    assumption_path = case_dir / "07_validation_governance" / "assumptions.csv"
    with assumption_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames
        rows = list(reader)
    assert header is not None
    rows[0][field] = replacement
    with assumption_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match=message):
        build_core(case_dir, tmp_path / "build")
    assert not (tmp_path / "build").exists()


def test_d0_build_rejects_currency_without_explicit_conversion(tmp_path: Path) -> None:
    case_dir, _ = _synthetic_case(tmp_path)
    case_path = case_dir / "00_charter" / "case.json"
    case = json.loads(case_path.read_text(encoding="utf-8"))
    case["reporting_currency"] = "EUR"
    case_path.write_text(json.dumps(case, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must match case reporting_currency"):
        build_core(case_dir, tmp_path / "build")
    assert not (tmp_path / "build").exists()


def test_d0_build_aggregates_explicit_cash_component_flags_once(tmp_path: Path) -> None:
    case_dir, _ = _synthetic_case(tmp_path, with_components=True)
    build_dir = build_core(case_dir, tmp_path / "build")
    outputs = json.loads((build_dir / "core_outputs.json").read_text(encoding="utf-8"))
    assert len(outputs["cash_components"]) == 1
    views = {view["view"]: view for view in outputs["cash_components"][0]["views"]}
    assert views["FCFF"]["value"] == "20"
    assert views["CFADS"]["value"] == "30"
    assert views["LIQUIDITY"]["value"] == "20"
    assert views["DEBT_SERVICE"]["value"] == "NOT_APPLICABLE"
    assert len(views["FCFF"]["normalized_fact_ids"]) == 2


def test_d0_build_checks_scope_bridge_receipt_lineage(tmp_path: Path) -> None:
    case_dir, _ = _synthetic_case(tmp_path, with_bridge=True)
    assert build_core(case_dir, tmp_path / "build").is_dir()
    bridge_path = case_dir / "01_evidence_core" / "scope_bridges.csv"
    with bridge_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames
        rows = list(reader)
    assert header is not None
    rows[0]["content_sha256"] = "b" * 64
    with bridge_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="Scope bridge provenance does not match"):
        build_core(case_dir, tmp_path / "another_build")


def test_d0_build_rejects_actual_publication_status_version_mismatch(tmp_path: Path) -> None:
    case_dir, _ = _synthetic_case(tmp_path)
    version_path = case_dir / "02_financial_core" / "versions.csv"
    with version_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames
        rows = list(reader)
    assert header is not None
    rows[0]["publication_status"] = "RESTATED"
    with version_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="publication status differs from version"):
        build_core(case_dir, tmp_path / "build")


def test_synthetic_d0_build_can_be_staged_but_not_published(tmp_path: Path) -> None:
    case_dir, _ = _synthetic_case(tmp_path)
    build_dir = build_core(case_dir, tmp_path / "build")
    external = {
        f"d0/{name}": build_dir / name
        for name in (
            "normalized_actuals.csv", "core_outputs.json", "memo_fields.json", "build_metadata.json"
        )
    }
    stage = stage_release(
        case_dir,
        tmp_path / "stage",
        external_outputs=external,
        output_paths=tuple(external),
        memo_paths=("d0/memo_fields.json",),
        reproduction_command="python -m pytest tests/integration/test_d0_core_build.py",
    )
    manifest = json.loads((stage / "release_manifest.json").read_text(encoding="utf-8"))
    assert manifest["content_hash"] and len(manifest["content_hash"]) == 64
    assert manifest["output_hash"] and len(manifest["output_hash"]) == 64
    assert manifest["memo_hash"] and len(manifest["memo_hash"]) == 64
    assert manifest["publication_state"] == "WITHHELD"
    assert not manifest["release_ready"]
    assert any(
        "cannot support a public case release" in item
        for item in manifest["known_limitations"]
    )
    assert (stage / "d0" / "core_outputs.json").is_file()
    with pytest.raises(ValueError, match="WITHHELD"):
        publish_release(stage, tmp_path / "releases")
    assert not (tmp_path / "releases").exists()


def test_d0_build_write_failure_leaves_no_partial_core_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_dir, _ = _synthetic_case(tmp_path)
    original_open = Path.open

    def failing_open(path: Path, *args: object, **kwargs: object):
        if path.name == "memo_fields.json" and path.parent.name.startswith(".core_staging_"):
            raise OSError("synthetic write failure")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failing_open)
    with pytest.raises(OSError, match="synthetic write failure"):
        build_core(case_dir, tmp_path / "build")
    case_build_dir = tmp_path / "build" / "synthetic_d0"
    assert case_build_dir.is_dir()
    assert list(case_build_dir.iterdir()) == []
