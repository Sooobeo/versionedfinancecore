"""Two fresh offline builds with an explicit, non-human handover receipt."""

from __future__ import annotations

import json
import tempfile
from hashlib import sha256
from pathlib import Path

from versioned_finance_core.contracts.json_io import strict_json_loads
from versioned_finance_core.contracts.reproduction import (
    COMPARISON_FIELDS,
    REPRODUCTION_KIND,
    REPRODUCTION_SCHEMA_VERSION,
)
from versioned_finance_core.orchestration.case_build import build_case, verify_case_build
from versioned_finance_core.reporting.reproduction import render_reproduction


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _object(path: Path) -> dict[str, object]:
    value = strict_json_loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")  # noqa: TRY004
    return value


def _relative_stage(root: Path, name: object) -> Path:
    if not isinstance(name, str) or not name or "\\" in name:
        raise ValueError("Reproduction stage must be a relative POSIX path")
    relative = Path(name)
    if relative.is_absolute() or any(part in {".", ".."} for part in name.split("/")):
        raise ValueError("Unsafe reproduction stage path")
    candidate = root / relative
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError("Reproduction stage escapes its bundle")
    return candidate


def _compare(first: dict[str, object], second: dict[str, object]) -> None:
    missing = [field for field in COMPARISON_FIELDS if field not in first or field not in second]
    if missing:
        raise ValueError("Reproduction manifest fields missing: " + ", ".join(missing))
    changed = [field for field in COMPARISON_FIELDS
               if _json_bytes(first[field]) != _json_bytes(second[field])]
    if changed:
        raise ValueError("Fresh builds differ: " + ", ".join(changed))


def _make_report(root: Path, first: Path, second: Path) -> dict[str, object]:
    first_check, second_check = verify_case_build(first), verify_case_build(second)
    if first_check != second_check:
        raise ValueError("Fresh build verification results differ")
    first_manifest = _object(first / "release_manifest.json")
    second_manifest = _object(second / "release_manifest.json")
    _compare(first_manifest, second_manifest)
    review = _object(first / "outputs/review_report.json")
    report = {
        "schema_version": REPRODUCTION_SCHEMA_VERSION,
        "kind": REPRODUCTION_KIND,
        "case_id": first_manifest["case_id"],
        "analysis_cutoff": first_manifest["cutoff_timestamp"],
        "first_stage": first.relative_to(root).as_posix(),
        "second_stage": second.relative_to(root).as_posix(),
        "automated_reproduction_state": "PASS",
        "human_review_state": "NOT_PERFORMED",
        "publication_state": "WITHHELD",
        "release_ready": False,
        "compared_fields": list(COMPARISON_FIELDS),
        "verified_identity": {field: first_manifest[field] for field in COMPARISON_FIELDS},
        "review_output_id": review["output_id"],
        "remaining_release_blockers": review["release_blockers"],
        "limitations": [
            "Two fresh offline builds verify deterministic reproduction, not financial validity.",
            "The same installed runtime is used twice; this is not cross-platform verification.",
            "Source availability, unresolved assumptions and case release gates remain separate.",
            "Independent human challenge, response and retest are not performed or waived.",
        ],
    }
    report["output_id"] = "reproduction_" + sha256(_json_bytes(report)).hexdigest()
    return report


def reproduce_case(case_dir: Path, output_dir: Path) -> Path:
    """Write two fresh builds and their verification receipt without source edits.

    The destination must not exist. A failed run never leaves a final handover
    bundle. No gate in the source case is promoted by this command.
    """
    case_dir, output_dir = Path(case_dir).resolve(), Path(output_dir).resolve()
    if output_dir.is_relative_to(case_dir) or case_dir.is_relative_to(output_dir):
        raise ValueError("Reproduction output must be separate from the source case")
    if output_dir.exists():
        raise FileExistsError(f"Reproduction output already exists: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".vfc-reproduction-", dir=output_dir.parent) as scratch:
        root = Path(scratch) / "bundle"
        first = build_case(case_dir, root / "first")
        second = build_case(case_dir, root / "second")
        report = _make_report(root, first, second)
        (root / "reproduction_report.json").write_bytes(_json_bytes(report))
        (root / "reproduction_memo.md").write_text(render_reproduction(report), encoding="utf-8")
        verify_reproduction(root)
        # A second existence check also protects a destination created during the run.
        if output_dir.exists():
            raise FileExistsError(f"Reproduction output already exists: {output_dir}")
        if output_dir.parent.resolve() != root.parent.parent.resolve():
            raise ValueError("Reproduction output parent changed during the build")
        root.rename(output_dir)
    return output_dir


def verify_reproduction(bundle_dir: Path) -> dict[str, object]:
    """Verify both builds and the deterministic handover report under current code."""
    root = Path(bundle_dir)
    if root.is_symlink():
        raise ValueError("Reproduction bundle cannot be a symlink")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Reproduction bundle cannot contain symlinks")
    report = _object(root / "reproduction_report.json")
    first = _relative_stage(root, report.get("first_stage"))
    second = _relative_stage(root, report.get("second_stage"))
    first_parts, second_parts = first.relative_to(root).parts, second.relative_to(root).parts
    if (len(first_parts) != 3 or len(second_parts) != 3
            or first_parts[0] != "first" or second_parts[0] != "second"):
        raise ValueError("Reproduction requires separate first and second build trees")
    expected = _make_report(root, first, second)
    if _json_bytes(report) != _json_bytes(expected):
        raise ValueError("Reproduction report does not match the verified builds")
    if (root / "reproduction_memo.md").read_text(encoding="utf-8") != render_reproduction(report):
        raise ValueError("Reproduction memo does not match the report")
    expected_files = {"reproduction_report.json", "reproduction_memo.md"}
    for stage in (first, second):
        manifest = _object(stage / "release_manifest.json")
        prefix = stage.relative_to(root).as_posix()
        expected_files.add(f"{prefix}/release_manifest.json")
        expected_files.update(f"{prefix}/{name}" for name in manifest["file_hashes"])
    actual_files = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if expected_files != actual_files:
        raise ValueError("Reproduction bundle file inventory differs from its manifests")
    return {
        "case_id": report["case_id"], "integrity_state": "VERIFIED",
        "automated_reproduction_state": "PASS", "human_review_state": "NOT_PERFORMED",
        "publication_state": "WITHHELD", "output_id": report["output_id"],
    }
