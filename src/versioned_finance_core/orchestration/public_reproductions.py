"""Offline, reproducible public-evidence adapters for bounded case outputs.

These adapters coordinate local case inputs with the canonical Core and module
functions.  They intentionally do not invent a baseline, dates, or financing
assumptions when a public case does not contain them.  A successful arithmetic
check can therefore still have a ``WITHHELD`` release status.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
from typing import Any

from versioned_finance_core.contracts import (
    CaseContract,
    ClaimTag,
    FinancialVersion,
    GateStatus,
    KnowledgeState,
    MappingRule,
    MetricDefinition,
    ModuleId,
    NormalizedFact,
    RawFact,
    ScopeBridge,
    VersionType,
)
from versioned_finance_core.contracts.json_io import strict_json_loads
from versioned_finance_core.evidence import load_provenanced_facts, load_source_ledger
from versioned_finance_core.evidence.ledger import SnapshotReceipt
from versioned_finance_core.financial_core import audit_reported_project_cash, normalize_actuals
from versioned_finance_core.modules.m1 import (
    ComparableMetric,
    PublicGuidanceRange,
    compare_actual_to_public_guidance_range,
)
from versioned_finance_core.modules.m2 import (
    M2PublicEvidenceCriterion,
    PublicEvidenceCoverage,
    PublicM2EvidenceItem,
    assess_public_m2_evidence,
)


def _rows(path: Path, *, required_columns: tuple[str, ...] = ()) -> list[dict[str, str]]:
    """Read a local CSV deterministically and reject a missing contract column."""

    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, strict=True)
            if not reader.fieldnames:
                raise ValueError(f"CSV has no header: {path}")
            missing = set(required_columns).difference(reader.fieldnames)
            if missing:
                raise ValueError(
                    f"CSV is missing required columns in {path}: {', '.join(sorted(missing))}"
                )
            result = list(reader)
    except csv.Error as exc:
        raise ValueError(f"malformed CSV: {path}") from exc
    if any(None in row or None in row.values() for row in result):
        raise ValueError(f"CSV has an invalid row width: {path}")
    return result


def _text(row: Mapping[str, str], field: str, context: str) -> str:
    value = row.get(field, "").strip()
    if not value:
        raise ValueError(f"{context} is missing {field}")
    return value


def _decimal(value: str, context: str) -> Decimal:
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{context} is not a Decimal: {value!r}") from exc
    if not result.is_finite():
        raise ValueError(f"{context} must be finite")
    return result


def _moment(value: str, context: str) -> datetime:
    try:
        result = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{context} is not an ISO timestamp: {value!r}") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{context} must include a UTC offset")
    return result


def _load_case(case_dir: Path) -> tuple[dict[str, Any], CaseContract]:
    path = case_dir / "00_charter" / "case.json"
    data = strict_json_loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError("case.json must contain an object")
    contract = CaseContract.from_mapping(data)
    if contract.case_id != case_dir.name:
        raise ValueError("case.json case_id does not match the case directory")
    if contract.analysis_cutoff is None:
        raise ValueError("case.json analysis_cutoff is required")
    return data, contract


def _require_active_module(contract: CaseContract, module_id: ModuleId) -> None:
    if module_id not in contract.active_modules:
        raise ValueError(f"{module_id.value} is not active for case {contract.case_id}")


def _module_state(case_dir: Path, state_id: str) -> str:
    path = case_dir / "00_charter" / "activation_gates.json"
    data = strict_json_loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError("activation_gates.json must contain an object")
    states = data.get("module_states")
    if not isinstance(states, dict):
        raise TypeError("activation_gates.json is missing module_states")
    state = states.get(state_id)
    if not isinstance(state, str) or not state:
        raise ValueError(f"activation_gates.json is missing module state {state_id}")
    return state


def _receipt_index(evidence_dir: Path) -> dict[str, SnapshotReceipt]:
    receipts = load_source_ledger(evidence_dir)
    result = {receipt.snapshot_id: receipt for receipt in receipts}
    if len(result) != len(receipts):
        raise ValueError("source ledger contains duplicate snapshot_id")
    return result


def _eligible_receipt(receipt: SnapshotReceipt, cutoff: datetime, context: str) -> None:
    if not receipt.metadata.cutoff_eligible or not receipt.metadata.transformation_right:
        raise ValueError(f"{context} source is not eligible for numeric transformation")
    if receipt.first_public_at is None or receipt.first_public_at > cutoff:
        raise ValueError(f"{context} source was unavailable at the case cutoff")


def _receipt_for_guidance_row(
    row: Mapping[str, str], receipts: Mapping[str, SnapshotReceipt], cutoff: datetime
) -> SnapshotReceipt:
    context = f"guidance row for {_text(row, 'metric_id', 'guidance row')}"
    receipt = receipts.get(_text(row, "source_snapshot_id", context))
    if receipt is None:
        raise ValueError(f"{context} references an unknown source snapshot")
    source_id = _text(row, "driver_or_assumption_id", context)
    if source_id != receipt.source_id:
        raise ValueError(f"{context} source_id does not match its snapshot")
    if _text(row, "source_content_sha256", context) != receipt.content_sha256:
        raise ValueError(f"{context} content hash does not match its snapshot")
    first_public_at = _moment(_text(row, "source_first_public_at", context), context)
    if first_public_at != receipt.first_public_at:
        raise ValueError(f"{context} first_public_at does not match its snapshot")
    _eligible_receipt(receipt, cutoff, context)
    return receipt


def _receipt_for_normalized_fact(
    fact: NormalizedFact, receipts: Mapping[str, SnapshotReceipt], cutoff: datetime
) -> SnapshotReceipt:
    provenance = fact.provenance
    receipt = receipts.get(provenance.snapshot_id)
    if receipt is None:
        raise ValueError(f"normalized fact {fact.fact_id} references an unknown source snapshot")
    if (
        receipt.source_id != provenance.source_id
        or receipt.content_sha256 != provenance.content_sha256
        or receipt.first_public_at != provenance.first_public_at
    ):
        raise ValueError(f"normalized fact {fact.fact_id} has conflicting source lineage")
    _eligible_receipt(receipt, cutoff, f"normalized fact {fact.fact_id}")
    return receipt


def _stable_output_id(prefix: str, identity: Mapping[str, object]) -> str:
    payload = json.dumps(identity, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return f"{prefix}_{sha256(payload.encode('utf-8')).hexdigest()}"


def _guidance_grain(row: Mapping[str, str]) -> tuple[str, ...]:
    return (
        _text(row, "metric_id", "guidance row"),
        _text(row, "economic_scope_id", "guidance row"),
        row.get("segment_id", "").strip(),
        _text(row, "period_start", "guidance row"),
        _text(row, "period_end", "guidance row"),
        _text(row, "currency", "guidance row"),
        _text(row, "unit", "guidance row"),
    )


def _actual_grain(fact: NormalizedFact) -> tuple[str, ...]:
    scope = fact.scope
    period = fact.period
    return (
        fact.metric_id,
        scope.economic_scope_id,
        scope.segment_id or "",
        period.start.isoformat(),
        period.end.isoformat(),
        fact.currency,
        fact.unit,
    )


def reproduce_guidance(case_dir: Path) -> dict[str, object]:
    """Reproduce a bounded M1 public-guidance outcome from local case inputs.

    The adapter runs Core normalization before calling the M1 range comparison.
    It is deliberately limited to same-definition public guidance and actuals;
    its successful computations do not turn the case into a released M1 model.
    """

    case_dir = Path(case_dir)
    case_data, contract = _load_case(case_dir)
    _require_active_module(contract, ModuleId.M1)
    cutoff = contract.analysis_cutoff
    assert cutoff is not None  # Guaranteed by _load_case.

    evidence_dir = case_dir / "01_evidence_core"
    core_dir = case_dir / "02_financial_core"
    m1_dir = case_dir / "03_m1_operating_forecast_valuation"
    receipts = _receipt_index(evidence_dir)

    versions = tuple(
        FinancialVersion.from_mapping(row)
        for row in _rows(
            core_dir / "versions.csv",
            required_columns=(
                "version_id",
                "version_type",
                "information_cutoff",
                "immutable",
            ),
        )
    )
    version_by_id = {version.version_id: version for version in versions}
    if len(version_by_id) != len(versions):
        raise ValueError("versions.csv contains duplicate version_id")

    normalized = normalize_actuals(
        contract.case_id,
        (RawFact.from_mapping(entry.as_csv_row()) for entry in load_provenanced_facts(evidence_dir)),
        (
            MappingRule.from_mapping(row)
            for row in _rows(evidence_dir / "mappings.csv")
        ),
        (
            MetricDefinition.from_mapping(row)
            for row in _rows(evidence_dir / "metric_dictionary.csv")
        ),
        versions,
        cutoff,
        scope_bridges=(
            ScopeBridge.from_mapping(row)
            for row in _rows(evidence_dir / "scope_bridges.csv")
        ),
    )
    stored_normalized = _rows(core_dir / "normalized_actuals.csv")
    generated_normalized = [fact.as_csv_row() for fact in normalized]
    if stored_normalized != generated_normalized:
        raise ValueError("pinned normalized_actuals.csv differs from Core normalization")

    actuals_by_grain: dict[tuple[str, ...], NormalizedFact] = {}
    for fact in normalized:
        version = version_by_id.get(fact.version_id)
        if version is None or version.version_type is not VersionType.PUBLIC_ACTUAL:
            raise ValueError(f"normalized fact is not a public actual: {fact.fact_id}")
        if not isinstance(fact.value, Decimal):
            raise TypeError(f"guidance comparison requires a known actual: {fact.metric_id}")
        grain = _actual_grain(fact)
        if grain in actuals_by_grain:
            raise ValueError(f"multiple actuals match a guidance grain: {fact.metric_id}")
        actuals_by_grain[grain] = fact

    guidance_rows = _rows(
        m1_dir / "forecast_versions.csv",
        required_columns=(
            "version_id",
            "scenario_id",
            "metric_id",
            "period_start",
            "period_end",
            "economic_scope_id",
            "currency",
            "unit",
            "value",
            "driver_or_assumption_id",
            "source_snapshot_id",
            "source_content_sha256",
            "source_first_public_at",
        ),
    )
    guidance_by_grain: dict[tuple[str, ...], list[dict[str, str]]] = {}
    for row in guidance_rows:
        version_id = _text(row, "version_id", "guidance row")
        version = version_by_id.get(version_id)
        if version is None:
            raise ValueError(f"guidance references unknown version_id: {version_id}")
        if version.version_type is not VersionType.PUBLIC_TARGET_OR_GUIDANCE:
            continue
        guidance_by_grain.setdefault(_guidance_grain(row), []).append(row)
    if not guidance_by_grain:
        raise ValueError("forecast_versions.csv has no public guidance bounds")

    comparisons: list[dict[str, str | None]] = []
    guidance_source_ids: set[str] = set()
    actual_source_ids: set[str] = set()
    for grain, bounds in sorted(guidance_by_grain.items()):
        if len(bounds) != 2:
            raise ValueError(
                "each public guidance grain must have exactly two disclosed bounds: "
                f"{grain[0]}"
            )
        scenario_ids = {_text(row, "scenario_id", "guidance row") for row in bounds}
        if len(scenario_ids) != len(bounds):
            raise ValueError(f"guidance bounds are duplicated for {grain[0]}")
        guidance_versions = {_text(row, "version_id", "guidance row") for row in bounds}
        if len(guidance_versions) != 1:
            raise ValueError(f"guidance bounds have different versions for {grain[0]}")
        guidance_version = version_by_id[guidance_versions.pop()]

        bound_details = [
            (_decimal(_text(row, "value", "guidance row"), f"guidance {grain[0]}"), row)
            for row in bounds
        ]
        bound_details.sort(key=lambda item: item[0])
        lower_bound, lower_row = bound_details[0]
        upper_bound, upper_row = bound_details[1]
        lower_receipt = _receipt_for_guidance_row(lower_row, receipts, cutoff)
        upper_receipt = _receipt_for_guidance_row(upper_row, receipts, cutoff)
        if lower_receipt.snapshot_id != upper_receipt.snapshot_id:
            raise ValueError(f"guidance bounds use different source snapshots for {grain[0]}")
        if guidance_version.information_cutoff != lower_receipt.first_public_at:
            raise ValueError(f"guidance version is not pinned to source publication for {grain[0]}")

        fact = actuals_by_grain.get(grain)
        if fact is None:
            raise ValueError(f"no same-definition public actual is available for {grain[0]}")
        actual_receipt = _receipt_for_normalized_fact(fact, receipts, cutoff)
        actual_version = version_by_id[fact.version_id]
        if guidance_version.information_cutoff >= actual_version.information_cutoff:
            raise ValueError(f"guidance is not prior to the actual for {grain[0]}")

        guidance = PublicGuidanceRange(
            metric_id=fact.metric_id,
            economic_scope_id=fact.scope.economic_scope_id,
            legal_entity_id=fact.scope.legal_entity_id,
            period_start=fact.period.start,
            period_end=fact.period.end,
            currency=fact.currency,
            unit=fact.unit,
            version_id=guidance_version.version_id,
            available_at=lower_receipt.first_public_at,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            source_id=lower_receipt.source_id,
        )
        actual = ComparableMetric(
            metric_id=fact.metric_id,
            economic_scope_id=fact.scope.economic_scope_id,
            legal_entity_id=fact.scope.legal_entity_id,
            period_start=fact.period.start,
            period_end=fact.period.end,
            currency=fact.currency,
            unit=fact.unit,
            version_id=actual_version.version_id,
            version_type=actual_version.version_type,
            available_at=fact.provenance.first_public_at,
            value=fact.value,
        )
        comparison = compare_actual_to_public_guidance_range(
            guidance,
            actual,
            actual_source_id=actual_receipt.source_id,
            comparison_basis_id=f"basis_{fact.metric_id}_v1",
            information_cutoff=cutoff,
        )
        comparisons.append(comparison.as_dict())
        guidance_source_ids.add(lower_receipt.source_id)
        actual_source_ids.add(actual_receipt.source_id)

    comparisons.sort(key=lambda item: (str(item["metric_id"]), str(item["period_start"])))
    source_ids = [*sorted(guidance_source_ids), *sorted(actual_source_ids)]
    input_files = [
        "00_charter/case.json",
        "00_charter/activation_gates.json",
        "01_evidence_core/source_ledger.csv",
        "01_evidence_core/raw_facts.csv",
        "01_evidence_core/mappings.csv",
        "01_evidence_core/metric_dictionary.csv",
        "01_evidence_core/scope_bridges.csv",
        "02_financial_core/versions.csv",
        "02_financial_core/normalized_actuals.csv",
        "03_m1_operating_forecast_valuation/forecast_versions.csv",
    ]
    output_id = _stable_output_id(
        "m1_guidance_reproduction",
        {
            "adapter": "m1_public_guidance_reproduction_v1",
            "case_id": contract.case_id,
            "analysis_cutoff": case_data["analysis_cutoff"],
            "comparison_output_ids": [item["output_id"] for item in comparisons],
            "source_ids": source_ids,
        },
    )
    return {
        "schema_version": 1,
        "adapter": "m1_public_guidance_reproduction_v1",
        "output_id": output_id,
        "case_id": contract.case_id,
        "analysis_cutoff": case_data["analysis_cutoff"],
        "coverage_state": contract.status,
        "release_status": GateStatus.WITHHELD.value,
        "module_state": _module_state(case_dir, "M1_PERFORMANCE"),
        "calculation_state": GateStatus.PASS.value,
        "claim_scope": "Published Q1 actual versus prior public guidance bounds; no cause attribution",
        "source_ids": source_ids,
        "canonical_output_ids": [item["output_id"] for item in comparisons],
        "comparisons": comparisons,
        "limitations": [
            "This is a same-definition published guidance-range outcome comparison, not a driver attribution or analyst forecast.",
            "The case has no linked P&L, balance-sheet, cash-flow, or reforecast model, so the M1 performance release remains WITHHELD.",
            "The output is personal research, learning, and portfolio evidence only.",
        ],
        "input_files": input_files,
    }


def guidance_legacy_artifact(result: Mapping[str, object]) -> dict[str, object]:
    """Project the rich adapter result onto the pre-existing M1 artifact contract."""

    comparisons = result.get("comparisons")
    source_ids = result.get("source_ids")
    if not isinstance(comparisons, list) or not isinstance(source_ids, list):
        raise TypeError("guidance reproduction result is missing comparisons or source_ids")
    return {
        "schema_version": 1,
        "case_id": result["case_id"],
        "analysis_cutoff": result["analysis_cutoff"],
        "coverage_state": result["coverage_state"],
        "claim_scope": result["claim_scope"],
        "source_ids": source_ids,
        "comparisons": comparisons,
    }


@dataclass(frozen=True)
class _DfsInputs:
    model_version_id: str
    economic_scope_id: str
    currency: str
    unit: str
    source_id: str
    relative_periods: tuple[str, ...]
    omitted_periods: tuple[str, ...]
    cash: tuple[Decimal, ...]


def _load_dfs_inputs(case_dir: Path, contract: CaseContract) -> _DfsInputs:
    evidence_dir = case_dir / "01_evidence_core"
    model_path = case_dir / "04_m2_capital_allocation" / "dfs_project_model.csv"
    rows = _rows(
        model_path,
        required_columns=(
            "model_version_id",
            "relative_period",
            "reported_post_tax_unlevered_fcff",
            "knowledge_state",
            "currency",
            "unit",
            "economic_scope_id",
            "source_id",
            "snapshot_id",
            "first_public_at",
        ),
    )
    if not rows:
        raise ValueError("dfs_project_model.csv has no rows")
    receipts = _receipt_index(evidence_dir)
    model_version_ids: set[str] = set()
    scope_ids: set[str] = set()
    currencies: set[str] = set()
    units: set[str] = set()
    source_ids: set[str] = set()
    periods: list[str] = []
    omitted_periods: list[str] = []
    cash: list[Decimal] = []
    seen_periods: set[str] = set()
    seen_known_cash = False
    prior_period_number: int | None = None

    for row in rows:
        context = "DFS project-model row"
        model_version_ids.add(_text(row, "model_version_id", context))
        period = _text(row, "relative_period", context)
        if period in seen_periods:
            raise ValueError(f"dfs_project_model.csv has duplicate relative_period: {period}")
        seen_periods.add(period)
        try:
            period_number = int(period)
        except ValueError as exc:
            raise ValueError(f"DFS relative_period must be an integer label: {period}") from exc
        if period_number == 0:
            raise ValueError("SWA-style DFS relative periods must not introduce a year 0")
        if prior_period_number is not None:
            expected = 1 if prior_period_number == -1 else prior_period_number + 1
            if period_number != expected:
                raise ValueError("DFS relative-period rows are not in the supported ordered sequence")
        prior_period_number = period_number
        periods.append(period)
        scope_ids.add(_text(row, "economic_scope_id", context))
        currencies.add(_text(row, "currency", context))
        units.add(_text(row, "unit", context))
        source_id = _text(row, "source_id", context)
        source_ids.add(source_id)

        receipt = receipts.get(_text(row, "snapshot_id", context))
        if receipt is None:
            raise ValueError(f"DFS project-model row references an unknown source snapshot: {period}")
        if receipt.source_id != source_id:
            raise ValueError(f"DFS project-model source does not match its snapshot: {period}")
        if _moment(_text(row, "first_public_at", context), context) != receipt.first_public_at:
            raise ValueError(f"DFS project-model first_public_at differs from source receipt: {period}")
        _eligible_receipt(receipt, contract.analysis_cutoff, f"DFS project-model row {period}")

        knowledge_state = _text(row, "knowledge_state", context)
        value = row.get("reported_post_tax_unlevered_fcff", "").strip()
        if knowledge_state == KnowledgeState.KNOWN.value:
            if not value:
                raise ValueError(f"known DFS project-model cash is blank: {period}")
            seen_known_cash = True
            cash.append(_decimal(value, f"DFS project-model cash {period}"))
        elif knowledge_state == KnowledgeState.UNKNOWN.value:
            if value:
                raise ValueError(f"unknown DFS project-model cash must not carry a numeric value: {period}")
            if seen_known_cash:
                raise ValueError(
                    "SWA-style DFS reconciliation supports only leading unknown dash periods"
                )
            omitted_periods.append(period)
        else:
            raise ValueError(f"unsupported DFS project-model knowledge_state: {knowledge_state}")

    if len(model_version_ids) != 1 or len(scope_ids) != 1 or len(currencies) != 1 or len(units) != 1:
        raise ValueError("DFS project-model rows do not share one model, scope, currency, and unit")
    if len(source_ids) != 1:
        raise ValueError("DFS project-model rows do not share one source")
    if not cash:
        raise ValueError("DFS arithmetic reproduction requires known displayed cash rows")

    economic_scope_id = scope_ids.pop()
    if contract.economic_scope_id and economic_scope_id != contract.economic_scope_id:
        raise ValueError("DFS project-model economic scope differs from case.json")
    return _DfsInputs(
        model_version_id=model_version_ids.pop(),
        economic_scope_id=economic_scope_id,
        currency=currencies.pop(),
        unit=units.pop(),
        source_id=source_ids.pop(),
        relative_periods=tuple(periods),
        omitted_periods=tuple(omitted_periods),
        cash=tuple(cash),
    )


def _load_dfs_rounded_cash(case_dir: Path) -> tuple[Decimal, ...]:
    """Compatibility helper used by the legacy DFS script; performs no mutation."""

    _, contract = _load_case(case_dir)
    return _load_dfs_inputs(Path(case_dir), contract).cash


def _single_assumption(
    rows: list[dict[str, str]], variable: str, scenario_id: str | None = None
) -> dict[str, str]:
    matches = [row for row in rows if row.get("variable", "").strip() == variable]
    if scenario_id is not None:
        matches = [row for row in matches if row.get("scenario_id", "").strip() == scenario_id]
    if len(matches) != 1:
        scope = f" in scenario {scenario_id}" if scenario_id else ""
        raise ValueError(f"expected exactly one assumption for {variable}{scope}")
    return matches[0]


def _configured_decimal(
    row: Mapping[str, str], inputs: _DfsInputs, context: str
) -> Decimal:
    if _text(row, "source_id", context) != inputs.source_id:
        raise ValueError(f"{context} source_id does not match the public DFS model source")
    return _decimal(_text(row, "value", context), context)


def _relative_period_display(periods: tuple[str, ...]) -> str:
    """Retain negative labels and compact only a consecutive positive run."""

    display: list[str] = []
    index = 0
    while index < len(periods):
        label = periods[index]
        try:
            value = int(label)
        except ValueError as exc:
            raise ValueError(f"relative period must be an integer label: {label}") from exc
        if value <= 0:
            display.append(label)
            index += 1
            continue
        end = value
        next_index = index + 1
        while next_index < len(periods):
            try:
                candidate = int(periods[next_index])
            except ValueError:
                break
            if candidate != end + 1 or candidate <= 0:
                break
            end = candidate
            next_index += 1
        display.append(f"{value}..{end}" if end != value else label)
        index = next_index
    return ",".join(display)


def _load_public_m2_evidence(
    case_dir: Path, contract: CaseContract
) -> tuple[dict[str, object], list[dict[str, str]], list[str]]:
    """Load source-linked public M2 evidence without manufacturing cash flows."""

    path = case_dir / "04_m2_capital_allocation" / "public_m2_evidence.csv"
    rows = _rows(
        path,
        required_columns=(
            "evidence_id",
            "criterion",
            "coverage",
            "source_id",
            "snapshot_id",
            "first_public_at",
            "claim_tag",
            "statement",
            "limitation",
        ),
    )
    if not rows:
        raise ValueError("public_m2_evidence.csv has no rows")
    receipts = _receipt_index(case_dir / "01_evidence_core")
    items: list[PublicM2EvidenceItem] = []
    displayed_items: list[dict[str, str]] = []
    for row in rows:
        context = f"public M2 evidence row {_text(row, 'evidence_id', 'public M2 evidence')}"
        try:
            criterion = M2PublicEvidenceCriterion(_text(row, "criterion", context))
        except ValueError as exc:
            raise ValueError(f"{context} has an unsupported criterion") from exc
        try:
            coverage = PublicEvidenceCoverage(_text(row, "coverage", context))
        except ValueError as exc:
            raise ValueError(f"{context} has an unsupported coverage") from exc
        try:
            claim_tag = ClaimTag(_text(row, "claim_tag", context))
        except ValueError as exc:
            raise ValueError(f"{context} has an unsupported claim_tag") from exc
        source_id = row.get("source_id", "").strip() or None
        snapshot_id = row.get("snapshot_id", "").strip()
        first_public_at = row.get("first_public_at", "").strip()
        source_fields = (source_id, snapshot_id, first_public_at)
        receipt: SnapshotReceipt | None = None
        if coverage is not PublicEvidenceCoverage.MISSING or any(source_fields):
            if not all(source_fields):
                raise ValueError(f"{context} must provide complete source lineage or none")
            receipt = receipts.get(snapshot_id)
            if receipt is None:
                raise ValueError(f"{context} references an unknown source snapshot")
            if receipt.source_id != source_id:
                raise ValueError(f"{context} source_id does not match its source snapshot")
            if _moment(first_public_at, context) != receipt.first_public_at:
                raise ValueError(f"{context} first_public_at does not match its source snapshot")
            _eligible_receipt(receipt, contract.analysis_cutoff, context)
        disclosed_value = row.get("disclosed_value", "").strip()
        if disclosed_value:
            for field in ("unit", "economic_scope_id", "timing_basis"):
                _text(row, field, context)
        if (
            coverage is PublicEvidenceCoverage.MISSING
            and source_id is None
            and (claim_tag is ClaimTag.FACT or disclosed_value)
        ):
            raise ValueError(f"{context} cannot present an unlinked factual value as missing evidence")
        statement = _text(row, "statement", context)
        limitation = _text(row, "limitation", context)
        items.append(
            PublicM2EvidenceItem(
                evidence_id=_text(row, "evidence_id", context),
                criterion=criterion,
                coverage=coverage,
                source_id=source_id,
                statement=statement,
                limitation=limitation,
            )
        )
        displayed = {
            "evidence_id": _text(row, "evidence_id", context),
            "criterion": criterion.value,
            "coverage": coverage.value,
            "claim_tag": claim_tag.value,
            "statement": statement,
            "limitation": limitation,
        }
        if source_id is not None:
            assert receipt is not None
            displayed.update(
                {
                    "source_id": source_id,
                    "snapshot_id": snapshot_id,
                    "first_public_at": first_public_at,
                    "source_content_sha256": receipt.content_sha256,
                    "source_retrieved_at": receipt.metadata.retrieved_at.isoformat(),
                }
            )
        for field in ("disclosed_value", "unit", "currency", "economic_scope_id", "timing_basis"):
            value = disclosed_value if field == "disclosed_value" else row.get(field, "").strip()
            if value:
                displayed[field] = value
        displayed_items.append(displayed)

    assessment = assess_public_m2_evidence(items)
    assessment_dict = assessment.as_dict()
    assessment_dict["assessment_id"] = _stable_output_id(
        "m2_public_evidence",
        {
            "adapter": "m2_public_evidence_completeness_v1",
            "case_id": contract.case_id,
            "analysis_cutoff": contract.analysis_cutoff.isoformat(),
            "evidence_items": displayed_items,
        },
    )
    return assessment_dict, displayed_items, list(assessment.source_ids)


def _declared_status_quo_option_id(case_dir: Path) -> str:
    alternatives = _rows(
        case_dir / "04_m2_capital_allocation" / "alternatives.csv",
        required_columns=("option_id", "status_quo_flag"),
    )
    selected = [row for row in alternatives if row.get("status_quo_flag", "").strip() == "YES"]
    if len(selected) != 1:
        raise ValueError("public M2 evidence requires exactly one declared status-quo alternative")
    return _text(selected[0], "option_id", "status-quo alternative")


def reproduce_m2_evidence(case_dir: Path) -> dict[str, object]:
    """Reproduce a case's M2 public-evidence completeness result.

    The result remains fail-closed: it does not calculate a status-quo, an
    option-world cash flow, funding availability, or an NPV.
    """

    case_dir = Path(case_dir)
    case_data, contract = _load_case(case_dir)
    _require_active_module(contract, ModuleId.M2)
    module_state = _module_state(case_dir, "M2_CAPITAL_ALLOCATION")
    if module_state != GateStatus.WITHHELD.value:
        raise ValueError("the public M2 evidence adapter requires a WITHHELD M2 module state")
    assessment, evidence_items, source_ids = _load_public_m2_evidence(case_dir, contract)
    status_quo_option_id = _declared_status_quo_option_id(case_dir)
    output_id = _stable_output_id(
        "m2_public_evidence_reproduction",
        {
            "adapter": "m2_public_evidence_completeness_v1",
            "case_id": contract.case_id,
            "analysis_cutoff": case_data["analysis_cutoff"],
            "assessment_id": assessment["assessment_id"],
            "status_quo_option_id": status_quo_option_id,
        },
    )
    blocking = assessment["blocking_criteria"]
    assert isinstance(blocking, list)
    return {
        "schema_version": 1,
        "adapter": "m2_public_evidence_completeness_v1",
        "output_id": output_id,
        "case_id": contract.case_id,
        "analysis_cutoff": case_data["analysis_cutoff"],
        "coverage_state": contract.status,
        "release_status": GateStatus.WITHHELD.value,
        "module_state": module_state,
        "calculation_state": assessment["decision_state"],
        "declared_status_quo_option_id": status_quo_option_id,
        "m2_public_evidence_assessment": assessment,
        "evidence_items": evidence_items,
        "source_ids": source_ids,
        "limitations": [
            "This is a source-lineage and completeness assessment, not an option-world-minus-status-quo cash-flow calculation.",
            "A MISSING evidence row records an inadequate case evidence register; it does not assert that an obligation or right cannot exist outside the reviewed public material.",
            f"The blocked criteria are: {', '.join(str(item) for item in blocking)}.",
            "No undisclosed remaining spend, payment date, funding availability, deferral right, or penalty is converted to zero or a scenario assumption.",
        ],
        "input_files": [
            "00_charter/case.json",
            "00_charter/activation_gates.json",
            "01_evidence_core/source_ledger.csv",
            "04_m2_capital_allocation/alternatives.csv",
            "04_m2_capital_allocation/public_m2_evidence.csv",
        ],
    }


# Kept as a narrow compatibility alias while callers migrate to the generic
# M2-facing name used by the case-build registry.
reproduce_public_m2_evidence = reproduce_m2_evidence


def reproduce_dfs(case_dir: Path) -> dict[str, object]:
    """Reproduce the SWA-style public DFS cash row without inventing an M2 baseline.

    The Core performs the displayed-row arithmetic and timing reconciliation.
    Neither result is treated as an option-world or status-quo cash flow, and
    no M2 option valuation is made.
    """

    case_dir = Path(case_dir)
    case_data, contract = _load_case(case_dir)
    _require_active_module(contract, ModuleId.M2)
    inputs = _load_dfs_inputs(case_dir, contract)
    public_evidence_assessment, public_evidence_items, public_evidence_source_ids = (
        _load_public_m2_evidence(case_dir, contract)
    )
    assumptions = _rows(
        case_dir / "07_validation_governance" / "assumptions.csv",
        required_columns=("assumption_id", "variable", "scenario_id", "value", "unit", "source_id"),
    )
    rate_row = _single_assumption(assumptions, "project_discount_rate")
    scenario_id = _text(rate_row, "scenario_id", "project discount-rate assumption")
    annual_rate = _configured_decimal(rate_row, inputs, "project discount-rate assumption")
    published_total_row = _single_assumption(
        assumptions, "published_post_tax_unlevered_fcff_total", scenario_id
    )
    published_npv_row = _single_assumption(assumptions, "published_project_npv", scenario_id)
    published_irr_row = _single_assumption(assumptions, "published_project_irr", scenario_id)
    published_total = _configured_decimal(published_total_row, inputs, "published FCFF total")
    published_npv = _configured_decimal(published_npv_row, inputs, "published project NPV")
    published_irr = _configured_decimal(published_irr_row, inputs, "published project IRR")
    if _text(published_total_row, "unit", "published FCFF total") != inputs.unit:
        raise ValueError("published FCFF total unit differs from the displayed model row")
    if _text(published_npv_row, "unit", "published project NPV") != inputs.unit:
        raise ValueError("published NPV unit differs from the displayed model row")

    audit = audit_reported_project_cash(
        inputs.cash,
        annual_rate=annual_rate,
        published_total=published_total,
        published_npv=published_npv,
    )

    alternatives = _rows(
        case_dir / "04_m2_capital_allocation" / "alternatives.csv",
        required_columns=("option_id", "status_quo_flag", "evidence_state", "review_status"),
    )
    status_quo_rows = [row for row in alternatives if row.get("status_quo_flag", "").strip() == "YES"]
    if len(status_quo_rows) != 1:
        raise ValueError("M2 reproduction requires exactly one declared status-quo alternative")
    status_quo = status_quo_rows[0]
    status_quo_evidence_state = _text(status_quo, "evidence_state", "status-quo alternative")
    if status_quo_evidence_state == KnowledgeState.KNOWN.value:
        raise ValueError("this limited adapter cannot replace a populated M2 status-quo model")
    incremental_rows = _rows(
        case_dir / "04_m2_capital_allocation" / "incremental_cash_flows.csv",
        required_columns=(
            "option_world_cash",
            "status_quo_world_cash",
            "incremental_after_tax_cash",
        ),
    )
    sources_uses_rows = _rows(
        case_dir / "04_m2_capital_allocation" / "sources_uses.csv",
        required_columns=("option_id", "event_date", "amount", "committed_state"),
    )
    module_state = _module_state(case_dir, "M2_CAPITAL_ALLOCATION")
    if module_state != GateStatus.WITHHELD.value:
        raise ValueError("this public DFS adapter requires a WITHHELD M2 module state")

    reported_project_cash_audit = {
        "model_version_id": inputs.model_version_id,
        "economic_scope_id": inputs.economic_scope_id,
        "basis": inputs.unit,
        "relative_periods": _relative_period_display(inputs.relative_periods),
        "leading_unknown_relative_periods": list(inputs.omitted_periods),
        "annual_discount_rate": str(annual_rate),
        "annual_discount_rate_unit": _text(
            rate_row, "unit", "project discount-rate assumption"
        ),
        "published_total_fcff_F": str(published_total),
        "sum_of_rounded_annual_fcff_D": str(audit.displayed_total),
        "published_npv_F": str(published_npv),
        "npv_start_year_D": str(audit.start_period_npv),
        "npv_mid_year_hypothesis_D": str(audit.mid_period_npv),
        "npv_end_year_D": str(audit.end_period_npv),
        "mid_year_difference_from_published_D": str(audit.mid_period_difference_from_published),
        "maximum_annual_row_rounding_effect_D": str(
            audit.maximum_mid_period_rounding_effect
        ),
        "published_irr_F": str(published_irr),
        "irr_from_rounded_annual_fcff_D": str(audit.implied_irr),
        "timing_state": "MID_YEAR_IS_AN_INFERENCE_NOT_A_DISCLOSED_CONVENTION",
        "decision_state": contract.status,
    }
    input_files = [
        "00_charter/case.json",
        "00_charter/activation_gates.json",
        "01_evidence_core/source_ledger.csv",
        "04_m2_capital_allocation/dfs_project_model.csv",
        "04_m2_capital_allocation/alternatives.csv",
        "04_m2_capital_allocation/incremental_cash_flows.csv",
        "04_m2_capital_allocation/public_m2_evidence.csv",
        "04_m2_capital_allocation/sources_uses.csv",
        "07_validation_governance/assumptions.csv",
    ]
    output_id = _stable_output_id(
        "m2_dfs_reproduction",
        {
            "adapter": "m2_public_dfs_arithmetic_reproduction_v1",
            "case_id": contract.case_id,
            "analysis_cutoff": case_data["analysis_cutoff"],
            "source_id": inputs.source_id,
            "reported_project_cash_audit": reported_project_cash_audit,
            "public_evidence_assessment_id": public_evidence_assessment["assessment_id"],
        },
    )
    return {
        "schema_version": 1,
        "adapter": "m2_public_dfs_arithmetic_reproduction_v1",
        "output_id": output_id,
        "case_id": contract.case_id,
        "analysis_cutoff": case_data["analysis_cutoff"],
        "coverage_state": contract.status,
        "release_status": GateStatus.WITHHELD.value,
        "module_state": module_state,
        "calculation_state": GateStatus.PASS.value,
        "m2_option_evaluation_state": public_evidence_assessment["decision_state"],
        "m2_option_valuation": None,
        "m2_option_evaluation_reason": (
            "The public case has only relative-period project cash, while the declared "
            "status-quo cash obligations are incomplete; no no-build cash is assumed to be zero."
        ),
        "m2_input_coverage": {
            "status_quo_evidence_state": status_quo_evidence_state,
            "incremental_cash_flow_row_count": len(incremental_rows),
            "sources_uses_row_count": len(sources_uses_rows),
            "public_evidence_row_count": len(public_evidence_items),
            "incremental_cashflow_evidence_state": public_evidence_assessment[
                "incremental_cashflow_state"
            ],
            "funding_feasibility_evidence_state": public_evidence_assessment[
                "funding_feasibility_state"
            ],
        },
        "m2_public_evidence_assessment": public_evidence_assessment,
        "m2_public_evidence_items": public_evidence_items,
        "source_ids": sorted({inputs.source_id, *public_evidence_source_ids}),
        "assumptions": {
            "scenario_id": scenario_id,
            "discount_rate": {
                "assumption_id": _text(rate_row, "assumption_id", "project discount-rate assumption"),
                "value": str(annual_rate),
                "unit": _text(rate_row, "unit", "project discount-rate assumption"),
            },
        },
        "rounding": {
            "source": "Displayed values in 04_m2_capital_allocation/dfs_project_model.csv",
            "method": (
                "Each known displayed cash row contributes one-half of its Decimal display "
                "quantum, discounted under the middle-year timing hypothesis."
            ),
            "display_quantums": [str(value) for value in audit.display_quantums],
            "maximum_mid_year_discounted_effect": str(
                audit.maximum_mid_period_rounding_effect
            ),
        },
        "reported_project_cash_audit": reported_project_cash_audit,
        "limitations": [
            "This is an independent arithmetic check of a rounded project-level public forecast, not an option-world-minus-status-quo valuation.",
            "Relative periods have no disclosed calendar period start/end dates, so they cannot be emitted as dated Core cash components.",
            "Only ordered SWA-style rows with leading UNKNOWN dash periods are supported; the first known row begins the reconciliation timing hypothesis.",
            f"The declared status-quo alternative has {status_quo_evidence_state} evidence and is not expanded into an unconditional no-build cash path.",
            "Publicly disclosed lease and funding terms are retained as partial evidence only; no grant draw, JV contribution, or lease-payment date is assumed.",
            "The middle-year result is an inference for reconciliation only; it is not a disclosed timing convention, FID conclusion, or funding conclusion.",
        ],
        "input_files": input_files,
    }


def dfs_legacy_artifact(result: Mapping[str, object]) -> dict[str, str]:
    """Project the rich DFS adapter result onto the pre-existing JSON artifact."""

    audit = result.get("reported_project_cash_audit")
    if not isinstance(audit, dict):
        raise TypeError("DFS reproduction result is missing its arithmetic output")
    assumptions = result.get("assumptions")
    if not isinstance(assumptions, dict):
        raise TypeError("DFS reproduction result is missing its assumptions")
    discount_rate = assumptions.get("discount_rate")
    if not isinstance(discount_rate, dict):
        raise TypeError("DFS reproduction result is missing its discount-rate assumption")
    configured_rate = _decimal(str(discount_rate.get("value", "")), "legacy DFS discount rate")
    reported_rate = _decimal(str(audit.get("annual_discount_rate", "")), "reported DFS rate")
    if reported_rate != configured_rate:
        raise ValueError("DFS audit discount rate differs from its configured assumption")
    if configured_rate != Decimal("0.08"):
        raise ValueError("the legacy DFS artifact only labels a published NPV at 8%")
    omitted = audit.get("leading_unknown_relative_periods")
    if not isinstance(omitted, list) or len(omitted) != 1:
        raise ValueError("the legacy DFS artifact requires exactly one leading unknown dash period")

    fields = (
        "model_version_id",
        "economic_scope_id",
        "basis",
        "relative_periods",
        "published_total_fcff_F",
        "sum_of_rounded_annual_fcff_D",
        "published_npv_F",
        "npv_start_year_D",
        "npv_mid_year_hypothesis_D",
        "npv_end_year_D",
        "mid_year_difference_from_published_D",
        "maximum_annual_row_rounding_effect_D",
        "published_irr_F",
        "irr_from_rounded_annual_fcff_D",
        "timing_state",
        "decision_state",
    )
    missing = [field for field in fields if field not in audit]
    if missing:
        raise ValueError(f"DFS reproduction result is missing fields: {', '.join(missing)}")
    return {
        "model_version_id": str(audit["model_version_id"]),
        "economic_scope_id": str(audit["economic_scope_id"]),
        "basis": str(audit["basis"]),
        "relative_periods": str(audit["relative_periods"]),
        "excluded_dash_period": str(omitted[0]),
        "published_total_fcff_F": str(audit["published_total_fcff_F"]),
        "sum_of_rounded_annual_fcff_D": str(audit["sum_of_rounded_annual_fcff_D"]),
        "published_npv_8pct_F": str(audit["published_npv_F"]),
        "npv_start_year_D": str(audit["npv_start_year_D"]),
        "npv_mid_year_hypothesis_D": str(audit["npv_mid_year_hypothesis_D"]),
        "npv_end_year_D": str(audit["npv_end_year_D"]),
        "mid_year_difference_from_published_D": str(audit["mid_year_difference_from_published_D"]),
        "maximum_annual_row_rounding_effect_D": str(
            audit["maximum_annual_row_rounding_effect_D"]
        ),
        "published_irr_F": str(audit["published_irr_F"]),
        "irr_from_rounded_annual_fcff_D": str(audit["irr_from_rounded_annual_fcff_D"]),
        "timing_state": str(audit["timing_state"]),
        "decision_state": str(audit["decision_state"]),
    }
