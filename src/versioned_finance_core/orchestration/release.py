"""Deterministic manifests, rebuildable staging, and immutable publication."""

from __future__ import annotations

import csv
import json
import os
import platform
import re
import shutil
import stat
import tempfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from versioned_finance_core.contracts.enums import AccessClass
from versioned_finance_core.contracts.json_io import strict_json_loads
from versioned_finance_core.contracts.models import CaseContract
from versioned_finance_core.evidence import load_provenanced_facts, load_source_ledger, sha256_file
from versioned_finance_core.orchestration.scaffold import validate_case
from versioned_finance_core.validation.gates import (
    GateResult,
    assess_release_gates,
    load_gate_results,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EXCLUDED_PARTS = {"private", "quarantine", "__pycache__", "raw_snapshots", ".git"}
EXCLUDED_NAMES = {".env", "credentials.json", "secrets.json"}
CASE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
MANIFEST_PATHS = {"release/release_manifest.json", "release_manifest.json"}
MATERIAL_FINDING_SEVERITIES = {"BLOCKING", "CRITICAL", "MATERIAL"}
RESOLVED_FINDING_STATES = {"CLOSED", "RESOLVED"}
PIPELINE_REVIEW_REPORT_PATH = "outputs/review_report.json"
PIPELINE_REVIEW_SCHEMA_VERSION = 1
PIPELINE_REVIEW_KIND = "CASE_BUILD_REVIEW"


def _hash_json(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(payload.encode("utf-8")).hexdigest()


def _is_secret(name: str) -> bool:
    lower = name.lower()
    return (
        lower in EXCLUDED_NAMES
        or lower.startswith(".env.")
        or any(word in lower for word in ("credential", "secret", "cookie", "private_key"))
        or lower.endswith((".pem", ".key", ".p12", ".pfx"))
    )


def _hash_tree(path: Path, *, python_only: bool = False) -> str | None:
    if not path.is_dir():
        return None
    files: dict[str, str] = {}
    for item in sorted(path.rglob("*")):
        if item.is_symlink():
            raise ValueError(f"Symlink is not allowed in release dependency: {item}")
        if not item.is_file() or (python_only and item.suffix != ".py"):
            continue
        relative = item.relative_to(path)
        if EXCLUDED_PARTS.intersection(relative.parts) or _is_secret(item.name):
            continue
        files[relative.as_posix()] = sha256_file(item)
    return _hash_json(files) if files else None


def _case_file_hashes(case_dir: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(case_dir.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Symlink is not allowed in a release case: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(case_dir)
        name = relative.as_posix()
        if name in MANIFEST_PATHS or EXCLUDED_PARTS.intersection(relative.parts):
            continue
        if _is_secret(path.name):
            continue
        files[name] = sha256_file(path)
    return files


def _external_file_hashes(
    external_outputs: Mapping[str, Path], case_hashes: Mapping[str, str]
) -> dict[str, str]:
    files: dict[str, str] = {}
    for name, raw_path in external_outputs.items():
        relative = Path(name)
        if (
            relative.is_absolute()
            or relative.drive
            or not relative.parts
            or ".." in relative.parts
            or EXCLUDED_PARTS.intersection(relative.parts)
            or _is_secret(relative.name)
            or relative.as_posix() in MANIFEST_PATHS
        ):
            raise ValueError(f"Unsafe external output path: {name}")
        key = relative.as_posix()
        if key in case_hashes or key in files:
            raise ValueError(f"Duplicate release file path: {key}")
        path = Path(raw_path)
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"External output is missing or a symlink: {path}")
        files[key] = sha256_file(path)
    return files


def _source_snapshot_fingerprint(
    case_dir: Path, cutoff: datetime | None
) -> tuple[str | None, list[str]]:
    evidence_dir = case_dir / "01_evidence_core"
    try:
        receipts = load_source_ledger(evidence_dir)
        facts = load_provenanced_facts(evidence_dir)
    except (OSError, TypeError, ValueError, KeyError) as exc:
        return None, [f"Source receipts or raw facts failed validation: {exc}"]
    if not receipts:
        return None, ["No source snapshot hashes were recorded"]

    public_classes = {
        AccessClass.PUBLIC_OFFICIAL,
        AccessClass.PUBLIC_COMPANY,
        AccessClass.PUBLIC_REGULATORY,
    }
    issues: list[str] = []
    for receipt in receipts:
        meta = receipt.metadata
        label = f"{receipt.source_id}/{receipt.snapshot_id}"
        if meta.access_class not in public_classes:
            issues.append(f"Source {label} cannot support a public case release")
        if not meta.cutoff_eligible or meta.first_public_at is None:
            issues.append(f"Source {label} is not cutoff eligible")
        elif cutoff is None or meta.first_public_at > cutoff:
            issues.append(f"Source {label} was first public after the analysis cutoff")
        if not meta.transformation_right:
            issues.append(f"Source {label} lacks transformation rights for derived facts")
    if not facts:
        issues.append("No validated raw facts were recorded")
    fingerprint = _hash_json(
        sorted(
            [receipt.source_id, receipt.snapshot_id, receipt.content_sha256]
            for receipt in receipts
        )
    )
    return fingerprint, issues


def _check_staging_source_access(case_dir: Path) -> None:
    evidence_dir = case_dir / "01_evidence_core"
    receipts = load_source_ledger(evidence_dir)
    facts = load_provenanced_facts(evidence_dir)
    restricted = {
        AccessClass.LICENSED_OPTIONAL,
        AccessClass.ACCOUNT_OR_FEE_ACCESSIBLE,
        AccessClass.INTERNAL_OR_CONFIDENTIAL,
    }
    if any(receipt.metadata.access_class in restricted for receipt in receipts):
        raise ValueError("Restricted or licensed source cannot be copied to release staging")
    if any(not fact.receipt.metadata.transformation_right for fact in facts):
        raise ValueError("Raw facts without transformation rights cannot enter release staging")


def _gate_policy(
    case: Mapping[str, object], gate_config_path: Path
) -> tuple[tuple[str, ...], dict[str, tuple[str, ...]], list[str]]:
    issues: list[str] = []
    try:
        config = strict_json_loads(gate_config_path.read_text(encoding="utf-8"))
        common = config["common_gates"]
        module_config = config["module_gates"]
        if not isinstance(common, list) or not common or not isinstance(module_config, dict):
            raise ValueError("Release gate policy is incomplete")
        if any(not isinstance(item, str) or not item for item in common):
            raise ValueError("Common release gate IDs must be nonempty strings")
        if config.get("schema_version") != case.get("schema_version"):
            raise ValueError("Release gate policy schema version differs from the case")
    except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        return (), {}, [f"Release gate policy is unavailable or invalid: {exc}"]

    module_rules: dict[str, tuple[str, ...]] = {}
    for module in case.get("active_modules", []):
        module_id = str(module)
        rule = module_config.get(module_id)
        if isinstance(rule, dict):
            rule = rule.get(case.get("perspective_id"))
        if not isinstance(rule, str) or not rule:
            issues.append(f"No configured release gate for active module {module_id}")
        else:
            module_rules[module_id] = (rule,)
    return tuple(common), module_rules, issues


def _activation_issues(
    case_dir: Path, required_module_gates: Mapping[str, Sequence[str]]
) -> list[str]:
    path = case_dir / "00_charter" / "activation_gates.json"
    try:
        activation = strict_json_loads(path.read_text(encoding="utf-8"))
        states = activation["module_states"]
        if not isinstance(states, dict):
            raise ValueError("module_states must be an object")  # noqa: TRY004
        case_gates = activation["case_gates"]
        if not isinstance(case_gates, list) or not case_gates:
            raise ValueError("case_gates must be a nonempty list")
    except (FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        return [f"Module activation states are unavailable or invalid: {exc}"]
    issues = [
        f"Module activation gate did not pass: {gate_id}"
        for gate_ids in required_module_gates.values()
        for gate_id in gate_ids
        if states.get(gate_id) != "PASS"
    ]
    for gate in case_gates:
        if not isinstance(gate, dict) or not gate.get("gate_id"):
            issues.append("A case activation gate has no gate_id")
        elif gate.get("status") != "PASS":
            issues.append(f"Case activation gate did not pass: {gate['gate_id']}")
        elif not gate.get("evidence"):
            issues.append(f"Case activation gate has no evidence: {gate['gate_id']}")
    return issues


def _review_finding_issues(case_dir: Path) -> list[str]:
    """An unresolved material finding cannot be overridden by a PASS gate row."""

    path = case_dir / "07_validation_governance" / "review_findings.csv"
    required = {
        "finding_id", "reviewer", "severity", "finding", "evidence",
        "response", "resolution", "retest_result", "status",
    }
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            if not reader.fieldnames or not required.issubset(reader.fieldnames):
                raise ValueError("review_findings.csv is missing required columns")
            if len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise ValueError("review_findings.csv has duplicate columns")
            rows = list(reader)
        if any(None in row or any(value is None for value in row.values()) for row in rows):
            raise ValueError("review_findings.csv has invalid row width")
    except (OSError, ValueError, csv.Error) as exc:
        return [f"Review finding ledger is unavailable or invalid: {exc}"]

    issues: list[str] = []
    seen: set[str] = set()
    for line_number, row in enumerate(rows, start=2):
        finding_id = (row.get("finding_id") or "").strip()
        if not finding_id:
            issues.append(f"Review finding line {line_number} has no finding_id")
            continue
        if finding_id in seen:
            issues.append(f"Duplicate review finding: {finding_id}")
        seen.add(finding_id)
        severity = (row.get("severity") or "").strip().upper()
        status = (row.get("status") or "").strip().upper()
        if not severity or not status:
            issues.append(f"Review finding {finding_id} lacks severity or status")
            continue
        if severity not in MATERIAL_FINDING_SEVERITIES:
            continue
        if status not in RESOLVED_FINDING_STATES:
            issues.append(f"Material review finding remains unresolved: {finding_id}")
            continue
        missing = [
            field for field in ("reviewer", "finding", "evidence", "response", "resolution", "retest_result")
            if not (row.get(field) or "").strip()
        ]
        if missing:
            issues.append(
                f"Resolved material review finding {finding_id} lacks challenge/response/retest: "
                + ", ".join(missing)
            )
    return issues


def _release_gate_controls(
    case_dir: Path, case: Mapping[str, object], gate_config_path: Path
) -> tuple[tuple[str, ...], dict[str, tuple[str, ...]], list[GateResult], list[str]]:
    """Share the same gate assessment between the CLI and release manifest."""

    required_common, required_modules, issues = _gate_policy(case, gate_config_path)
    issues.extend(_activation_issues(case_dir, required_modules))
    issues.extend(_review_finding_issues(case_dir))
    try:
        gate_results = load_gate_results(case_dir / "07_validation_governance" / "gate_results.csv")
    except (FileNotFoundError, ValueError) as exc:
        gate_results = []
        issues.append(f"Release gate ledger is unavailable or invalid: {exc}")
    gate_assessment = assess_release_gates(
        gate_results,
        required_common_gates=required_common,
        active_modules=tuple(str(item) for item in case.get("active_modules", [])),
        required_module_gates=required_modules,
        require_evidence=True,
    )
    issues.extend(gate_assessment.issues)
    return required_common, required_modules, gate_results, issues


def case_release_readiness_issues(case_dir: Path) -> list[str]:
    """Check source eligibility and configured gates without building a manifest.

    The CLI calls this only after structural validation. Selected outputs,
    memo references, reproduction commands, and code/config hashes remain
    publication checks in build_manifest and publish_release.
    """

    case_dir = Path(case_dir)
    case = strict_json_loads((case_dir / "00_charter" / "case.json").read_text(encoding="utf-8"))
    contract = CaseContract.from_mapping(case)
    _, source_issues = _source_snapshot_fingerprint(case_dir, contract.analysis_cutoff)
    gate_path = PROJECT_ROOT / "config" / "defaults" / "release_gates.json"
    _, _, _, gate_issues = _release_gate_controls(case_dir, case, gate_path)
    return source_issues + gate_issues


def _selected_hashes(
    file_hashes: Mapping[str, str], paths: Sequence[str], label: str
) -> tuple[str | None, list[str]]:
    if not paths:
        return None, [f"No {label} paths were selected"]
    selected: dict[str, str] = {}
    issues: list[str] = []
    for name in paths:
        if name not in file_hashes:
            issues.append(f"{label} file is missing or excluded: {name}")
        else:
            selected[name] = file_hashes[name]
    return (_hash_json(selected) if selected else None), issues


def _collect_output_ids(value: object) -> set[str]:
    if isinstance(value, dict):
        ids = {
            item.strip() for key, item in value.items()
            if key == "output_id" and isinstance(item, str) and item.strip()
        }
        for item in value.values():
            ids.update(_collect_output_ids(item))
        return ids
    if isinstance(value, list):
        ids: set[str] = set()
        for item in value:
            ids.update(_collect_output_ids(item))
        return ids
    return set()


def _memo_issues(
    case_dir: Path,
    memo_paths: Sequence[str],
    output_paths: Sequence[str],
    external: Mapping[str, Path],
    file_hashes: Mapping[str, str],
) -> list[str]:
    issues: list[str] = []
    canonical_ids: set[str] = set()
    for name in output_paths:
        if name in memo_paths or name not in file_hashes or Path(name).suffix.lower() != ".json":
            continue
        path = Path(external[name]) if name in external else case_dir / name
        try:
            canonical_ids.update(_collect_output_ids(strict_json_loads(path.read_text(encoding="utf-8"))))
        except (OSError, UnicodeError, ValueError) as exc:
            issues.append(f"Selected JSON output cannot be read for memo reconciliation: {name}: {exc}")
    for name in memo_paths:
        if name not in file_hashes:
            continue
        path = Path(external[name]) if name in external else case_dir / name
        if not path.is_file():
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            issues.append(f"Memo cannot be read: {name}: {exc}")
            continue
        if not body.strip() or re.search(r"(?m)^Status:\s*`?NOT_STARTED`?\s*$", body):
            issues.append(f"Memo is empty or still a template: {name}")
            continue
        if path.suffix.lower() == ".json":
            try:
                references = _collect_output_ids(strict_json_loads(body))
            except ValueError as exc:
                issues.append(f"Memo JSON is invalid: {name}: {exc}")
                continue
        else:
            references = set(re.findall(
                r"(?im)^\s*output_id\s*:\s*`?([A-Za-z0-9_.:-]+)`?", body
            ))
            references.update(re.findall(
                r"(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9_]*_[0-9a-f]{64}(?![A-Za-z0-9_])",
                body,
            ))
        if not references:
            issues.append(f"Memo has no canonical output ID reference: {name}")
        for output_id in sorted(references - canonical_ids):
            issues.append(f"Memo {name} references an unselected output ID: {output_id}")
    return issues


def _pipeline_review_report_issues(
    case_dir: Path,
    contract: CaseContract,
    output_paths: Sequence[str],
    external_outputs: Mapping[str, Path],
    file_hashes: Mapping[str, str],
) -> list[str]:
    """Validate an optional generated review report before it can be staged.

    The generic release API remains usable for manually assembled snapshots.  A
    pipeline-generated report is different: once its canonical path is present,
    it must be selected and its case, cutoff, modules, and blockers must be
    reconciled with the case contract.  A manual PASS gate row cannot override
    a blocker emitted by that report.
    """

    report_is_present = PIPELINE_REVIEW_REPORT_PATH in file_hashes
    report_is_selected = PIPELINE_REVIEW_REPORT_PATH in output_paths
    if not report_is_present:
        return []
    if not report_is_selected:
        return [
            (
                "Pipeline review report exists but is not selected as an output: "
                f"{PIPELINE_REVIEW_REPORT_PATH}"
            )
        ]

    report_path = case_dir / PIPELINE_REVIEW_REPORT_PATH
    for name, path in external_outputs.items():
        if Path(name).as_posix() == PIPELINE_REVIEW_REPORT_PATH:
            report_path = Path(path)
            break
    if not report_path.is_file() or report_path.is_symlink():
        return [f"Pipeline review report is missing or unsafe: {PIPELINE_REVIEW_REPORT_PATH}"]
    try:
        report = strict_json_loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        return [f"Pipeline review report is invalid JSON: {PIPELINE_REVIEW_REPORT_PATH}: {exc}"]
    if not isinstance(report, dict):
        return [f"Pipeline review report must be a JSON object: {PIPELINE_REVIEW_REPORT_PATH}"]

    issues: list[str] = []
    if type(report.get("schema_version")) is not int or (
        report.get("schema_version") != PIPELINE_REVIEW_SCHEMA_VERSION
    ):
        issues.append(
            "Pipeline review report has an unsupported schema_version: "
            f"{PIPELINE_REVIEW_REPORT_PATH}"
        )
    if report.get("kind") != PIPELINE_REVIEW_KIND:
        issues.append(f"Pipeline review report has an invalid kind: {PIPELINE_REVIEW_REPORT_PATH}")
    if report.get("case_id") != contract.case_id:
        issues.append(f"Pipeline review report case_id differs from case.json: {PIPELINE_REVIEW_REPORT_PATH}")

    report_cutoff = report.get("analysis_cutoff")
    if not isinstance(report_cutoff, str) or not report_cutoff:
        issues.append(
            "Pipeline review report analysis_cutoff is missing or invalid: "
            f"{PIPELINE_REVIEW_REPORT_PATH}"
        )
    else:
        try:
            parsed_cutoff = datetime.fromisoformat(report_cutoff)
            if parsed_cutoff.tzinfo is None or parsed_cutoff.utcoffset() is None:
                raise ValueError("timestamp has no UTC offset")
        except ValueError:
            issues.append(
                "Pipeline review report analysis_cutoff is missing or invalid: "
                f"{PIPELINE_REVIEW_REPORT_PATH}"
            )
        else:
            if contract.analysis_cutoff is None or parsed_cutoff != contract.analysis_cutoff:
                issues.append(
                    "Pipeline review report analysis_cutoff differs from case.json: "
                    f"{PIPELINE_REVIEW_REPORT_PATH}"
                )

    expected_modules = report.get("expected_modules")
    case_modules = [module.value for module in contract.active_modules]
    if (
        not isinstance(expected_modules, list)
        or any(not isinstance(module, str) or not module for module in expected_modules)
        or expected_modules != case_modules
    ):
        issues.append(
            "Pipeline review report expected_modules differ from case.json active_modules: "
            f"{PIPELINE_REVIEW_REPORT_PATH}"
        )
    if report.get("publication_state") != "WITHHELD":
        issues.append(
            "Pipeline review report publication_state must be WITHHELD: "
            f"{PIPELINE_REVIEW_REPORT_PATH}"
        )

    blockers = report.get("release_blockers")
    if not isinstance(blockers, list):
        issues.append(
            "Pipeline review report release_blockers must be a list: "
            f"{PIPELINE_REVIEW_REPORT_PATH}"
        )
        return issues
    if any(not isinstance(blocker, str) or not blocker.strip() for blocker in blockers):
        issues.append(
            "Pipeline review report release_blockers contains a blank or non-string value: "
            f"{PIPELINE_REVIEW_REPORT_PATH}"
        )
        return issues
    if len(blockers) != len(set(blockers)):
        issues.append(
            "Pipeline review report release_blockers contains duplicates: "
            f"{PIPELINE_REVIEW_REPORT_PATH}"
        )
        return issues
    issues.extend(f"Pipeline review report blocks release: {blocker}" for blocker in blockers)
    return issues


def _gate_dict(result: GateResult) -> dict[str, str]:
    return {
        "gate_id": result.gate_id,
        "module_id": result.module_id,
        "status": str(result.status),
        "evidence": result.evidence,
        "limitation": result.limitation,
    }


def build_manifest(
    case_dir: Path,
    *,
    output_paths: Sequence[str] = (),
    memo_paths: Sequence[str] = (),
    external_outputs: Mapping[str, Path] | None = None,
    config_dir: Path | None = None,
    code_dir: Path | None = None,
    gate_config_path: Path | None = None,
    reproduction_command: str | None = None,
    review_state: str = "SELF_REVIEWED_LIMITED_USE",
    known_limitations: Sequence[str] = (),
    supersedes_release_id: str | None = None,
) -> dict[str, object]:
    """Build a fail-closed manifest; this function never marks a case published."""

    case_dir = Path(case_dir)
    case = strict_json_loads((case_dir / "00_charter" / "case.json").read_text(encoding="utf-8"))
    contract = CaseContract.from_mapping(case)
    file_hashes = _case_file_hashes(case_dir)
    external = external_outputs or {}
    file_hashes.update(_external_file_hashes(external, file_hashes))
    selected_outputs = tuple(dict.fromkeys(output_paths))
    selected_memos = tuple(dict.fromkeys(memo_paths))
    config_dir = config_dir or PROJECT_ROOT / "config" / "defaults"
    code_dir = code_dir or PROJECT_ROOT / "src" / "versioned_finance_core"
    gate_config_path = gate_config_path or config_dir / "release_gates.json"

    issues, _ = validate_case(case_dir, release_ready=True)
    if (case_dir / "release_manifest.json").is_file():
        issues = [
            issue for issue in issues
            if issue != "Missing required file: release/release_manifest.json"
        ]
        if case_dir.parent.name == contract.case_id:
            issues = [
                issue for issue in issues
                if issue != "case.json case_id does not match the case directory"
            ]
    source_hash, source_issues = _source_snapshot_fingerprint(case_dir, contract.analysis_cutoff)
    issues.extend(source_issues)
    config_hash = _hash_tree(config_dir)
    code_hash = _hash_tree(code_dir)
    if config_hash is None:
        issues.append("Configuration hash is unavailable")
    if code_hash is None:
        issues.append("Code hash is unavailable")

    output_hash, output_issues = _selected_hashes(file_hashes, selected_outputs, "output")
    memo_hash, memo_issues = _selected_hashes(file_hashes, selected_memos, "memo")
    issues.extend(output_issues + memo_issues)
    issues.extend(_memo_issues(
        case_dir, selected_memos, selected_outputs, external, file_hashes
    ))
    issues.extend(_pipeline_review_report_issues(
        case_dir, contract, selected_outputs, external, file_hashes
    ))
    if any(name not in selected_outputs for name in selected_memos):
        issues.append("Every memo must also be a selected output")
    if any(name not in selected_outputs for name in external):
        issues.append("Every external build artifact must be selected as an output")
    input_hashes = {name: digest for name, digest in file_hashes.items() if name not in selected_outputs}
    input_hash = _hash_json(input_hashes) if input_hashes else None
    if input_hash is None:
        issues.append("No release input files were selected")

    required_common, required_modules, gate_results, control_issues = _release_gate_controls(
        case_dir, case, gate_config_path
    )
    issues.extend(control_issues)
    if not reproduction_command or not reproduction_command.strip():
        issues.append("Reproduction command is not recorded")
    if not review_state.strip():
        issues.append("Review state is not recorded")

    content_basis = {
        "program_id": contract.program_id,
        "case_id": contract.case_id,
        "cutoff_timestamp": case.get("analysis_cutoff"),
        "schema_version": case.get("schema_version"),
        "source_snapshot_hash": source_hash,
        "input_hash": input_hash,
        "config_hash": config_hash,
        "formula_or_code_hash": code_hash,
        "output_hash": output_hash,
        "memo_hash": memo_hash,
    }
    content_hash = _hash_json(content_basis) if all(content_basis.values()) else None
    limitations = list(dict.fromkeys([*known_limitations, *issues]))
    return {
        "schema_version": case.get("schema_version", 1),
        "contract_version": case.get("schema_version", 1),
        "program_id": contract.program_id,
        "case_id": contract.case_id,
        "release_id": None,
        "supersedes_release_id": supersedes_release_id,
        "cutoff_timestamp": case.get("analysis_cutoff"),
        "coverage_state": "FEASIBILITY_ONLY" if issues else "CASE_EVALUATED",
        "review_state": review_state,
        "publication_state": "WITHHELD",
        "source_snapshot_hash": source_hash,
        "input_hash": input_hash,
        "config_hash": config_hash,
        "formula_or_code_hash": code_hash,
        "output_hash": output_hash,
        "memo_hash": memo_hash,
        "content_hash": content_hash,
        "file_hashes": file_hashes,
        "output_paths": list(selected_outputs),
        "memo_paths": list(selected_memos),
        "required_common_gates": list(required_common),
        "required_module_gates": {key: list(value) for key, value in required_modules.items()},
        "gate_results": [_gate_dict(result) for result in gate_results],
        "known_limitations": limitations,
        "declared_limitations": list(known_limitations),
        "release_ready": not issues,
        "runtime_environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "reproduction_command": reproduction_command,
        "generated_at": datetime.now(UTC).isoformat(),
        "released_at": None,
    }


def _staging_id(manifest: Mapping[str, object]) -> str:
    stable = {
        key: value
        for key, value in manifest.items()
        if key not in {"generated_at", "released_at", "runtime_environment"}
    }
    return _hash_json(stable)[:24]


def _write_new_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, indent=2)
        output.write("\n")


def write_manifest(case_dir: Path, output: Path | None = None, **kwargs: object) -> Path:
    """Write a withheld manifest into deterministic staging without overwriting."""

    manifest = build_manifest(case_dir, **kwargs)
    case_id = str(manifest["case_id"])
    if not CASE_ID_PATTERN.fullmatch(case_id):
        raise ValueError("Invalid case_id for a release path")
    target = output or (
        Path(case_dir).parent.parent
        / "build"
        / case_id
        / _staging_id(manifest)
        / "release_manifest.json"
    )
    _write_new_json(Path(target), manifest)
    return Path(target)


def stage_release(case_dir: Path, stage_root: Path, **kwargs: object) -> Path:
    """Copy a safe case snapshot into a new, rebuildable staging directory."""

    _check_staging_source_access(Path(case_dir))
    manifest = build_manifest(case_dir, **kwargs)
    external_outputs = {
        Path(name).as_posix(): Path(path)
        for name, path in (kwargs.get("external_outputs") or {}).items()
    }
    case_id = str(manifest["case_id"])
    if not CASE_ID_PATTERN.fullmatch(case_id):
        raise ValueError("Invalid case_id for a release path")
    destination = Path(stage_root) / case_id / _staging_id(manifest)
    if destination.exists():
        raise FileExistsError(f"Release stage already exists: {destination}")
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    if parent.is_symlink():
        raise ValueError(f"Release stage parent cannot be a symlink: {parent}")
    resolved_parent = parent.resolve()
    staging = Path(tempfile.mkdtemp(prefix=".release_staging_", dir=parent))
    try:
        for name in manifest["file_hashes"]:
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source = external_outputs[name] if name in external_outputs else Path(case_dir) / name
            shutil.copy2(source, target)
        _write_new_json(staging / "release_manifest.json", manifest)
        _assert_exact_stage_files(staging, manifest["file_hashes"])
        if (staging.resolve().parent != resolved_parent
                or destination.resolve().parent != resolved_parent):
            raise ValueError("Release stage or target escaped the build case directory")
        if destination.exists():
            raise FileExistsError(f"Release stage already exists: {destination}")
        staging.rename(destination)
    finally:
        if staging.exists():
            if staging.is_symlink() or staging.resolve().parent != resolved_parent:
                raise ValueError("Refusing cleanup outside the temporary release directory")
            shutil.rmtree(staging)
    return destination


def _assert_exact_stage_files(stage_dir: Path, file_hashes: Mapping[str, str]) -> None:
    observed: set[str] = set()
    for path in stage_dir.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Symlink is not allowed in a release stage: {path}")
        if path.is_file():
            observed.add(path.relative_to(stage_dir).as_posix())
    expected = set(file_hashes) | {"release_manifest.json"}
    if observed != expected:
        raise ValueError("Stage files differ from the manifest file list")
    if _case_file_hashes(stage_dir) != dict(file_hashes):
        raise ValueError("Stage file hashes differ from the manifest")


def publish_release(
    stage_dir: Path,
    releases_root: Path,
    *,
    config_dir: Path | None = None,
    code_dir: Path | None = None,
    gate_config_path: Path | None = None,
) -> Path:
    """Publish a validated stage to a new release ID; never replace a release."""

    stage_dir = Path(stage_dir)
    staged = strict_json_loads((stage_dir / "release_manifest.json").read_text(encoding="utf-8"))
    if not isinstance(staged, dict):
        raise ValueError("Stage manifest must be a JSON object")  # noqa: TRY004
    if staged.get("publication_state") != "WITHHELD":
        raise ValueError("Only withheld staging manifests may be published")
    file_hashes = staged.get("file_hashes")
    if not isinstance(file_hashes, dict):
        raise ValueError("Stage manifest has no file hash map")  # noqa: TRY004
    _assert_exact_stage_files(stage_dir, file_hashes)
    fresh = build_manifest(
        stage_dir,
        output_paths=staged.get("output_paths", ()),
        memo_paths=staged.get("memo_paths", ()),
        config_dir=config_dir,
        code_dir=code_dir,
        gate_config_path=gate_config_path,
        reproduction_command=staged.get("reproduction_command"),
        review_state=staged.get("review_state", ""),
        known_limitations=staged.get("declared_limitations", ()),
        supersedes_release_id=staged.get("supersedes_release_id"),
    )
    stable_fields = (
        "schema_version", "contract_version", "program_id", "case_id", "cutoff_timestamp",
        "source_snapshot_hash", "input_hash", "config_hash", "formula_or_code_hash",
        "output_hash", "memo_hash", "content_hash", "file_hashes", "gate_results",
        "required_common_gates", "required_module_gates", "release_ready", "known_limitations",
    )
    changed = [key for key in stable_fields if staged.get(key) != fresh.get(key)]
    if changed:
        raise ValueError(
            "Stage manifest no longer matches case, code, or configuration: "
            + ", ".join(changed)
        )
    if not fresh["release_ready"] or not fresh["content_hash"]:
        raise ValueError("Release gates or required provenance are incomplete; state remains WITHHELD")

    release_id = "r-" + _hash_json(
        {
            "content_hash": fresh["content_hash"],
            "gate_results": fresh["gate_results"],
            "review_state": fresh["review_state"],
            "known_limitations": fresh["known_limitations"],
            "supersedes_release_id": fresh["supersedes_release_id"],
        }
    )[:24]
    case_id = str(fresh["case_id"])
    if not CASE_ID_PATTERN.fullmatch(case_id):
        raise ValueError("Invalid case_id for a release path")
    destination = Path(releases_root) / case_id / release_id
    if destination.exists():
        raise FileExistsError(f"Immutable release already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    # Assemble outside the final ID and rename only after the manifest is complete.
    with tempfile.TemporaryDirectory(prefix=".pending-", dir=destination.parent) as pending:
        payload = Path(pending) / "payload"
        shutil.copytree(stage_dir, payload)
        publication = dict(fresh)
        publication["release_id"] = release_id
        publication["publication_state"] = "PUBLISHED"
        publication["released_at"] = datetime.now(UTC).isoformat()
        (payload / "release_manifest.json").write_text(
            json.dumps(publication, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        for path in payload.rglob("*"):
            if path.is_file():
                path.chmod(stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
        if destination.exists():
            raise FileExistsError(f"Immutable release already exists: {destination}")
        os.rename(payload, destination)
    return destination
