"""Offline case recipe runner: fresh calculations, review report, immutable stage."""

from __future__ import annotations

import csv
import json
import tempfile
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

from versioned_finance_core.contracts.build_recipe import STEP_MODULES, BuildRecipe
from versioned_finance_core.contracts.json_io import strict_json_loads
from versioned_finance_core.evidence import load_source_ledger, verify_snapshot_content
from versioned_finance_core.orchestration import release
from versioned_finance_core.orchestration.core_build import build_core
from versioned_finance_core.orchestration.credit_evidence import review_credit_evidence
from versioned_finance_core.orchestration.scaffold import validate_case
from versioned_finance_core.reporting.case_review import render_case_review

RECIPE_PATH = "00_charter/build_recipe.json"
CORE_FILES = ("normalized_actuals.csv", "core_outputs.json", "memo_fields.json", "build_metadata.json")
AUTOMATED_REVIEW_NOTE = "Automated reproduction does not complete independent human challenge, response and retest."


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f"Invalid CSV header: {path}")
        rows = list(reader)
    if any(None in row or None in row.values() for row in rows):
        raise ValueError(f"Invalid CSV row width: {path}")
    return rows


def _dependency_hashes(case_dir: Path) -> dict[str, object]:
    # Include all case-local code/config, not only the old D0 Python dependency list.
    # Raw bytes are excluded from publication bundles but remain dependencies.
    # Track both availability and verified identity to catch mid-build changes.
    evidence_dir = case_dir / "01_evidence_core"
    snapshots = {
        receipt.snapshot_id: (
            receipt.content_sha256 if verify_snapshot_content(evidence_dir, receipt) else None
        )
        for receipt in load_source_ledger(evidence_dir)
    }
    return {
        "retained_snapshots": snapshots,
        "case_files": release._case_file_hashes(case_dir),
        "case_manifest": sha256((case_dir / "release/release_manifest.json").read_bytes()).hexdigest(),
        "code_hash": release._hash_tree(Path(__file__).resolve().parents[1]),
        "config_hash": release._hash_tree(release.PROJECT_ROOT / "config/defaults"),
    }


def build_case(case_dir: Path, build_root: Path) -> Path:
    """Execute only declared built-in adapters, then stage newly computed outputs.

    A successful command means reproduction succeeded, not decision eligibility.
    Every bundle remains WITHHELD. Original case files and older builds are never
    updated. Recipe files cannot execute Python commands or name arbitrary scripts.
    """
    case_dir = Path(case_dir).resolve()
    build_root = Path(build_root).resolve()
    if build_root.is_relative_to(case_dir):
        raise ValueError("Build root must be outside the source case")
    errors, warnings = validate_case(case_dir)
    if errors:
        raise ValueError("Case validation failed: " + "; ".join(errors))
    recipe_path = case_dir / RECIPE_PATH
    if not recipe_path.is_file() or recipe_path.is_symlink():
        raise ValueError(f"Missing regular build recipe: {recipe_path}")
    recipe = BuildRecipe.from_mapping(strict_json_loads(recipe_path.read_text(encoding="utf-8")))
    if not recipe.steps:
        raise ValueError("Build recipe has no calculation steps; configure it after the evidence pilot")
    charter = strict_json_loads((case_dir / "00_charter/case.json").read_text(encoding="utf-8"))
    recipe.validate_modules(tuple(charter["active_modules"]))
    initial = _dependency_hashes(case_dir)
    command = (
        "python -m versioned_finance_core build-case "
        f"cases/{charter['case_id']} --build-root <fresh-build-root>"
    )
    with tempfile.TemporaryDirectory(prefix="vfc-case-review-") as scratch:
        scratch_path = Path(scratch)
        external: dict[str, Path] = {}
        memos: list[str] = []
        executed: list[dict[str, object]] = []
        adapter_limitations: list[str] = []
        core_dir: Path | None = None

        def add(name: str, payload: object, *, text: bool = False) -> None:
            if name in external:
                raise ValueError(f"Duplicate generated artifact: {name}")
            target = scratch_path / "artifacts" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload.encode("utf-8") if text else _json_bytes(payload))
            external[name] = target

        for step in recipe.steps:
            before = set(external)
            if step == "core_cash":
                core_dir = build_core(case_dir, scratch_path / "core")
                for name in CORE_FILES:
                    external[f"outputs/core/{name}"] = core_dir / name
                memos.append("outputs/core/memo_fields.json")
                core_output = strict_json_loads(
                    (core_dir / "core_outputs.json").read_text(encoding="utf-8")
                )
                identity = core_output["cash_identity"]
                if (identity["knowledge_state"] != "KNOWN" or identity["residual"] is None
                        or Decimal(identity["residual"]) != 0):
                    adapter_limitations.append("Core cash identity is unknown or has a nonzero residual.")
            elif step == "conditional_valuation":
                from versioned_finance_core.orchestration.conditional_model import (
                    build_review_artifacts,
                    review_csvs,
                )

                if core_dir is None:
                    raise ValueError("conditional_valuation requires a fresh Core build")
                config_path = case_dir / "02_financial_core/conditional_model_config.json"
                result = build_review_artifacts(
                    case_dir=case_dir, normalized_actuals=core_dir / "normalized_actuals.csv",
                    config_path=config_path,
                )
                for filename, key in (
                    ("conditional_linked_forecast.json", "forecast"),
                    ("conditional_valuation_screen.json", "valuation"),
                    ("conditional_memo_fields.json", "memo_fields"),
                ):
                    add(f"outputs/m1/{filename}", result[key])
                for filename, body in review_csvs(result, config_path=config_path).items():
                    add(f"outputs/m1/{filename}", body, text=True)
                memos.append("outputs/m1/conditional_memo_fields.json")
                adapter_limitations.extend(result["valuation"].get("limitations", []))
                adapter_limitations.append("Conditional valuation inputs and claims remain WITHHELD.")
            elif step in {"guidance_comparison", "dfs_reproduction", "capital_evidence"}:
                from versioned_finance_core.orchestration.public_reproductions import (
                    reproduce_dfs,
                    reproduce_guidance,
                    reproduce_m2_evidence,
                )

                function = {
                    "guidance_comparison": reproduce_guidance,
                    "dfs_reproduction": reproduce_dfs,
                    "capital_evidence": reproduce_m2_evidence,
                }[step]
                result = function(case_dir)
                folder = "m1" if step == "guidance_comparison" else "m2"
                add(f"outputs/{folder}/{step}.json", result)
                adapter_limitations.extend(result["limitations"])
                if result.get("release_status") != "PASS":
                    adapter_limitations.append(f"{step} has no release-eligible decision output.")
            elif step == "credit_evidence":
                if core_dir is None:
                    raise ValueError("credit_evidence requires a fresh Core build")
                result = review_credit_evidence(case_dir, core_dir)
                add("outputs/m3/credit_evidence.json", result)
                adapter_limitations.extend(result["limitations"])
                if result.get("release_status") != "PASS":
                    adapter_limitations.append("credit_evidence has no release-eligible decision output.")
            executed.append({
                "step": step, "execution_state": "REPRODUCED",
                "artifacts": sorted(set(external) - before),
            })

        readiness_errors, _ = validate_case(case_dir, release_ready=True)
        covered_modules = {STEP_MODULES[step] for step in recipe.steps if step in STEP_MODULES}
        missing_modules = [f"No module adapter executed for active module {module}."
                           for module in charter["active_modules"] if module not in covered_modules]
        blockers = list(dict.fromkeys([
            *readiness_errors, *release.case_release_readiness_issues(case_dir),
            *recipe.scope_limitations, *adapter_limitations, *missing_modules,
        ]))
        report = {
            "schema_version": 1, "kind": "CASE_BUILD_REVIEW", "case_id": charter["case_id"],
            "analysis_cutoff": charter["analysis_cutoff"], "publication_state": "WITHHELD",
            "expected_modules": charter["active_modules"], "executed_steps": executed,
            "review_note": AUTOMATED_REVIEW_NOTE,
            "structure_warnings": warnings, "release_blockers": blockers,
            "gate_results": _read_rows(case_dir / "07_validation_governance/gate_results.csv"),
            "review_findings": _read_rows(case_dir / "07_validation_governance/review_findings.csv"),
            "artifact_hashes": {name: sha256(path.read_bytes()).hexdigest()
                                for name, path in sorted(external.items())},
            "reproduction_command": command,
        }
        report["output_id"] = "case_review_" + sha256(_json_bytes(report)).hexdigest()
        add("outputs/review_report.json", report)
        add("outputs/review_memo.md", render_case_review(report), text=True)
        memos.append("outputs/review_memo.md")
        if _dependency_hashes(case_dir) != initial:
            raise ValueError("Case, code or configuration changed during the review build")
        target = release.stage_release(
            case_dir, build_root, external_outputs=external,
            output_paths=tuple(external), memo_paths=tuple(memos),
            reproduction_command=command,
            review_state="AUTOMATED_REPRODUCTION_NOT_INDEPENDENT_REVIEW",
            known_limitations=tuple(blockers),
        )
    return target


def verify_case_build(stage_dir: Path) -> dict[str, object]:
    """Check bytes, report references and current code/config without publication.

    This is an integrity check, not an independent financial review or rerun.
    Repeat build-case into another root to rerun the actual calculations.
    """
    stage_dir = Path(stage_dir)
    if stage_dir.is_symlink():
        raise ValueError("Review build cannot be a symlink")
    staged = strict_json_loads((stage_dir / "release_manifest.json").read_text(encoding="utf-8"))
    if not isinstance(staged, dict):
        raise ValueError("Build manifest must be a JSON object")  # noqa: TRY004
    for field in ("schema_version", "contract_version"):
        if type(staged.get(field)) is not int:
            raise ValueError(f"Build manifest requires an integer: {field}")
    for field in ("case_id", "cutoff_timestamp", "reproduction_command", "review_state"):
        if not isinstance(staged.get(field), str) or not staged[field].strip():
            raise ValueError(f"Build manifest requires nonempty text: {field}")
    for field in ("output_paths", "memo_paths", "declared_limitations"):
        value = staged.get(field)
        if (not isinstance(value, list)
                or any(not isinstance(item, str) or not item.strip() for item in value)):
            raise ValueError(f"Build manifest requires a list of strings: {field}")
        if len(value) != len(set(value)):
            raise ValueError(f"Build manifest contains duplicate {field}")
    hashes = staged.get("file_hashes")
    if not isinstance(hashes, dict) or any(
        not isinstance(name, str) or not name or not isinstance(digest, str)
        for name, digest in hashes.items()
    ):
        raise ValueError("Build manifest must contain file_hashes")
    if staged["review_state"] != "AUTOMATED_REPRODUCTION_NOT_INDEPENDENT_REVIEW":
        raise ValueError("Build manifest cannot promote automated reproduction to human review")
    if staged.get("supersedes_release_id") is not None:
        raise ValueError("Build manifest cannot declare publication supersession")
    release._assert_exact_stage_files(stage_dir, hashes)
    report = strict_json_loads((stage_dir / "outputs/review_report.json").read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ValueError("Review report must be a JSON object")  # noqa: TRY004
    report_basis = {key: value for key, value in report.items() if key != "output_id"}
    if report.get("output_id") != "case_review_" + sha256(_json_bytes(report_basis)).hexdigest():
        raise ValueError("Review report output ID does not match its content")
    if staged["reproduction_command"] != report.get("reproduction_command"):
        raise ValueError("Build manifest reproduction command differs from its review report")
    if _json_bytes(staged["declared_limitations"]) != _json_bytes(report.get("release_blockers")):
        raise ValueError("Build manifest declared limitations differ from its review report")
    artifact_hashes = report.get("artifact_hashes")
    expected_artifacts = set(staged["output_paths"]) - {
        "outputs/review_report.json", "outputs/review_memo.md",
    }
    if not isinstance(artifact_hashes, dict) or set(artifact_hashes) != expected_artifacts:
        raise ValueError("Review report artifact inventory differs from selected outputs")
    if any(hashes.get(name) != digest for name, digest in artifact_hashes.items()):
        raise ValueError("Review report artifact hashes differ from the manifest")
    fresh = release.build_manifest(
        stage_dir, output_paths=staged["output_paths"], memo_paths=staged["memo_paths"],
        reproduction_command=staged["reproduction_command"], review_state=staged["review_state"],
        known_limitations=staged.get("declared_limitations", ()),
        supersedes_release_id=staged.get("supersedes_release_id"),
    )
    stable = ("schema_version", "contract_version", "program_id", "release_id", "coverage_state",
              "case_id", "cutoff_timestamp", "source_snapshot_hash", "input_hash", "config_hash",
              "formula_or_code_hash", "output_hash", "memo_hash", "content_hash",
              "gate_results", "required_common_gates", "required_module_gates",
              "release_ready", "known_limitations", "publication_state")
    if changed := [key for key in stable if _json_bytes(staged.get(key)) != _json_bytes(fresh.get(key))]:
        raise ValueError("Review build no longer matches code/configuration/controls: " + ", ".join(changed))
    return {"case_id": staged["case_id"], "integrity_state": "VERIFIED",
            "publication_state": staged["publication_state"],
            "release_ready": staged["release_ready"], "output_hash": staged["output_hash"]}
