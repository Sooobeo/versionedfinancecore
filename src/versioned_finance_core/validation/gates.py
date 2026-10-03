"""Non-compensatory validation of common and active-module release gates."""

from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from versioned_finance_core.contracts.enums import GateStatus


@dataclass(frozen=True)
class GateResult:
    gate_id: str
    status: GateStatus
    evidence: str = ""
    limitation: str = ""
    module_id: str = ""


@dataclass(frozen=True)
class GateAssessment:
    allowed: bool
    issues: tuple[str, ...]


def load_gate_results(path: Path) -> list[GateResult]:
    """Read the case gate ledger without assigning favorable defaults to blank rows."""

    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames or not {"gate_id", "status"}.issubset(reader.fieldnames):
            raise ValueError("gate_results.csv requires gate_id and status columns")
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("gate_results.csv has duplicate columns")
        results: list[GateResult] = []
        for line_number, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"gate_results.csv line {line_number}: invalid row width")
            gate_id = (row.get("gate_id") or "").strip()
            if not gate_id:
                raise ValueError(f"gate_results.csv line {line_number}: gate_id is blank")
            try:
                status = GateStatus((row.get("status") or "").strip())
            except ValueError as exc:
                raise ValueError(
                    f"gate_results.csv line {line_number}: invalid gate status"
                ) from exc
            results.append(
                GateResult(
                    gate_id=gate_id,
                    status=status,
                    evidence=(row.get("evidence") or "").strip(),
                    limitation=(row.get("limitation") or "").strip(),
                    module_id=(row.get("module_id") or "").strip(),
                )
            )
    return results


def assess_release_gates(
    results: Iterable[GateResult],
    *,
    required_common_gates: Sequence[str] = (),
    active_modules: Sequence[str] = (),
    required_module_gates: Mapping[str, Sequence[str]] | None = None,
    require_evidence: bool = False,
) -> GateAssessment:
    """Fail closed for missing, duplicated, invalid, or failed gate decisions.

    Every configured common gate and every gate required for an active module
    must explicitly pass. A NOT_APPLICABLE result may only describe an optional
    gate; it cannot satisfy a required gate.
    """

    items = list(results)
    issues: list[str] = []
    if not items:
        issues.append("No release gate results were recorded")

    by_id: dict[str, GateResult] = {}
    for result in items:
        gate_id = result.gate_id.strip() if isinstance(result.gate_id, str) else ""
        if not gate_id:
            issues.append("A release gate has no gate_id")
            continue
        if gate_id in by_id:
            issues.append(f"Duplicate release gate: {gate_id}")
            continue
        by_id[gate_id] = result
        try:
            status = GateStatus(result.status)
        except (TypeError, ValueError):
            issues.append(f"Invalid status for release gate: {gate_id}")
            continue
        if status not in (GateStatus.PASS, GateStatus.NOT_APPLICABLE):
            issues.append(f"Release gate {gate_id} is {status.value}")
        elif require_evidence and not (result.evidence or result.limitation):
            issues.append(f"Release gate {gate_id} has no evidence or reason")

    for gate_id in dict.fromkeys(required_common_gates):
        result = by_id.get(gate_id)
        if result is None:
            issues.append(f"Required common gate is missing: {gate_id}")
        elif result.module_id:
            issues.append(f"Common gate {gate_id} has module_id {result.module_id}")
        elif result.status != GateStatus.PASS:
            issues.append(f"Required common gate did not pass: {gate_id}")

    module_rules = required_module_gates or {}
    for module_id in dict.fromkeys(active_modules):
        gate_ids = tuple(module_rules.get(module_id, ()))
        if not gate_ids:
            issues.append(f"No release gate policy for active module: {module_id}")
            continue
        for gate_id in dict.fromkeys(gate_ids):
            result = by_id.get(gate_id)
            if result is None:
                issues.append(f"Required {module_id} gate is missing: {gate_id}")
            elif result.module_id != module_id:
                issues.append(f"Gate {gate_id} must be scoped to {module_id}")
            elif result.status != GateStatus.PASS:
                issues.append(f"Required {module_id} gate did not pass: {gate_id}")

    return GateAssessment(allowed=not issues, issues=tuple(issues))


def release_allowed(results: list[GateResult]) -> bool:
    """Compatibility check for a set of already selected gate results."""

    return assess_release_gates(results).allowed

