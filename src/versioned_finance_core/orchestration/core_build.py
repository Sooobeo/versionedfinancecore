"""D0 evidence-to-core staging adapter; financial calculations stay in Core."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import tempfile
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from pathlib import Path

from versioned_finance_core.contracts import (
    SCHEMA_VERSION,
    CaseContract,
    FinancialVersion,
    MappingRule,
    MetricDefinition,
    NormalizedFact,
    RawFact,
    ScopeBridge,
    VersionType,
)
from versioned_finance_core.evidence import (
    known_at_cutoff,
    load_provenanced_facts,
    load_source_ledger,
    select_known_facts,
    verify_snapshot_content,
)
from versioned_finance_core.financial_core.cash_components import (
    CashComponentInput,
    CashComponentRule,
    CashInclusionResult,
    aggregate_cash_components,
)
from versioned_finance_core.financial_core.cash_identity import (
    CashIdentitySpec,
    evaluate_cash_identity,
)
from versioned_finance_core.financial_core.normalization import normalize_actuals
from versioned_finance_core.financial_core.scenario_cash import project_cash_scenario
from versioned_finance_core.financial_core.scenarios import (
    ScenarioDriverOverride,
    parse_scenario_rows,
)
from versioned_finance_core.reporting import cash_identity_memo_field, scenario_cash_memo_field

CASE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

INPUT_FILES = (
    "00_charter/case.json",
    "01_evidence_core/source_ledger.csv",
    "01_evidence_core/raw_facts.csv",
    "01_evidence_core/mappings.csv",
    "01_evidence_core/metric_dictionary.csv",
    "01_evidence_core/scope_bridges.csv",
    "02_financial_core/versions.csv",
    "02_financial_core/cash_identity_checks.csv",
    "02_financial_core/scenarios.csv",
    "02_financial_core/cash_components.csv",
    "02_financial_core/normalized_actuals.csv",  # output contract header only
    "07_validation_governance/assumptions.csv",
)
CODE_FILES = (
    "contracts/__init__.py",
    "contracts/enums.py",
    "contracts/models.py",
    "contracts/records.py",
    "evidence/__init__.py",
    "evidence/cutoff.py",
    "evidence/dart_cash.py",
    "evidence/facts.py",
    "evidence/hashing.py",
    "evidence/ledger.py",
    "financial_core/cash_identity.py",
    "financial_core/cash_components.py",
    "financial_core/identities.py",
    "financial_core/normalization.py",
    "financial_core/scenario_cash.py",
    "financial_core/scenarios.py",
    "orchestration/core_build.py",
    "reporting/__init__.py",
    "reporting/fields.py",
)
REQUIRED_CSV_COLUMNS = {
    "mappings.csv": ("mapping_id", "source_id", "raw_account_id", "normalized_metric_id",
                     "effective_from", "effective_to", "sign_multiplier", "review_status"),
    "metric_dictionary.csv": ("metric_id", "grain", "period_type", "currency_policy",
                              "unit", "sign_convention", "review_status"),
    "scope_bridges.csv": ("bridge_id", "economic_scope_id", "legal_entity_id", "relation",
                          "source_id", "snapshot_id", "content_sha256", "first_public_at",
                          "retrieved_at", "review_status"),
    "versions.csv": ("version_id", "version_type", "as_of_date", "publication_status",
                     "supersedes_version_id", "information_cutoff", "immutable"),
    "cash_identity_checks.csv": ("identity_id", "version_id", "opening_cash_fact_id",
                                 "operating_cash_flow_fact_id", "investing_cash_flow_fact_id",
                                 "financing_cash_flow_fact_id", "fx_and_other_fact_id",
                                 "closing_cash_fact_id"),
    "scenarios.csv": ("scenario_id", "scenario_purpose", "version_id", "driver_id",
                      "period_start", "period_end", "input_value", "input_unit",
                      "evidence_or_assumption_id", "mechanism", "dependency_group",
                      "review_status", "baseline_version_id"),
    "assumptions.csv": ("assumption_id", "variable", "scenario_id", "value",
                        "unit", "mechanism", "status"),
    "cash_components.csv": ("cash_component_id", "metric_id", "tax_basis",
                            "included_in_fcff", "included_in_fcfe", "included_in_cfads",
                            "included_in_debt_service", "included_in_liquidity",
                            "included_in_sources_uses"),
}


def build_core(case_dir: Path, build_root: Path) -> Path:
    """Stage one case's pinned cash identity and optional cash scenario.

    The returned directory is ``build_root/<case_id>/core_<content hash>``.
    Repeating a build with the same inputs raises FileExistsError; this adapter
    never publishes a release or overwrites an existing build.
    """

    case_dir = Path(case_dir)
    build_root = Path(build_root)
    case_json = json.loads(_read_regular_file(case_dir / "00_charter" / "case.json"))
    if case_json.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"case schema_version must be {SCHEMA_VERSION}")
    case = CaseContract.from_mapping(case_json)
    if not CASE_ID_PATTERN.fullmatch(case.case_id) or case_dir.name != case.case_id:
        raise ValueError("case_id must be safe and match the case directory name")
    if case.analysis_cutoff is None:
        raise ValueError("case analysis_cutoff is required for a core build")
    if not case.reporting_currency:
        raise ValueError("case reporting_currency is required for a core build")
    initial_input_hashes = _file_hashes(case_dir, INPUT_FILES)

    evidence_dir = case_dir / "01_evidence_core"
    core_dir = case_dir / "02_financial_core"
    receipts = load_source_ledger(evidence_dir)
    receipt_by_id = {receipt.snapshot_id: receipt for receipt in receipts}
    entries = select_known_facts(load_provenanced_facts(evidence_dir), case.analysis_cutoff)
    if not entries:
        raise ValueError("No cutoff-eligible raw facts are available")
    locator_only: set[str] = set()
    for entry in entries:
        if not entry.receipt.metadata.transformation_right:
            raise ValueError(f"Source lacks transformation right: {entry.fact.source_id}")
        if not verify_snapshot_content(evidence_dir, entry.receipt):
            locator_only.add(entry.fact.snapshot_id)
    raw_facts = tuple(RawFact.from_mapping(entry.as_csv_row()) for entry in entries)

    mappings = tuple(
        MappingRule.from_mapping(row) for row in _csv_rows(evidence_dir / "mappings.csv")
    )
    metrics = tuple(
        MetricDefinition.from_mapping(row)
        for row in _csv_rows(evidence_dir / "metric_dictionary.csv")
    )
    bridges = tuple(
        ScopeBridge.from_mapping(row)
        for row in _csv_rows(evidence_dir / "scope_bridges.csv")
    )
    for bridge in bridges:
        provenance = bridge.provenance
        receipt = receipt_by_id.get(provenance.snapshot_id)
        if receipt is None or (
            provenance.source_id != receipt.source_id
            or provenance.content_sha256 != receipt.content_sha256
            or provenance.first_public_at != receipt.first_public_at
            or provenance.retrieved_at != receipt.retrieved_at
        ):
            raise ValueError(
                f"Scope bridge provenance does not match a receipt: {bridge.bridge_id}"
            )
        if not receipt.metadata.cutoff_eligible or not known_at_cutoff(
            receipt.first_public_at, case.analysis_cutoff
        ):
            raise ValueError(f"Scope bridge source is not eligible at cutoff: {bridge.bridge_id}")
        if not receipt.metadata.transformation_right:
            raise ValueError(f"Scope bridge source lacks transformation right: {bridge.bridge_id}")
        if not verify_snapshot_content(evidence_dir, receipt):
            locator_only.add(receipt.snapshot_id)
    versions = tuple(
        FinancialVersion.from_mapping(row)
        for row in _csv_rows(core_dir / "versions.csv")
    )
    version_by_id = {version.version_id: version for version in versions}
    if len(version_by_id) != len(versions):
        raise ValueError("versions.csv contains duplicate version_id")
    for entry in entries:
        version = version_by_id.get(entry.fact.version_id)
        if version is None:
            raise ValueError(f"Unknown raw fact version_id: {entry.fact.version_id}")
        if entry.receipt.metadata.publication_status is not version.publication_status:
            raise ValueError(
                f"Raw fact publication status differs from version: {entry.fact.fact_id}"
            )
    normalized = normalize_actuals(
        case.case_id,
        raw_facts,
        mappings,
        metrics,
        versions,
        case.analysis_cutoff,
        scope_bridges=bridges,
    )
    if not normalized:
        raise ValueError("No facts survived financial-core normalization")
    currencies = {fact.currency for fact in normalized}
    if currencies != {case.reporting_currency}:
        raise ValueError(
            "Normalized fact currency must match case reporting_currency; "
            "D0 has no FX conversion"
        )

    component_rules = tuple(
        CashComponentRule.from_mapping(row)
        for row in _csv_rows(core_dir / "cash_components.csv")
    )
    component_results = _aggregate_component_groups(case.case_id, normalized, component_rules)

    identity_rows = _csv_rows(core_dir / "cash_identity_checks.csv")
    if len(identity_rows) != 1:
        raise ValueError("D0 core build requires exactly one cash identity specification")
    spec = CashIdentitySpec.from_mapping(identity_rows[0])
    identity = evaluate_cash_identity(spec, normalized)

    scenario_rows = _csv_rows(core_dir / "scenarios.csv")
    scenario_result = None
    if scenario_rows:
        baseline_ids = {row.get("baseline_version_id", "").strip() for row in scenario_rows}
        if baseline_ids != {spec.version_id}:
            raise ValueError("scenario baseline_version_id must pin the cash identity version")
        overrides = parse_scenario_rows(scenario_rows)
        if len({(row.scenario_id, row.version_id) for row in overrides}) != 1:
            raise ValueError("D0 core build supports one scenario ID and version at a time")
        scenario_version = version_by_id.get(overrides[0].version_id)
        if scenario_version is None or scenario_version.version_type is not VersionType.SCENARIO:
            raise ValueError("scenario override version must exist with type SCENARIO")
        if (
            not scenario_version.immutable
            or scenario_version.information_cutoff > case.analysis_cutoff
        ):
            raise ValueError("scenario version must be immutable and known at analysis cutoff")
        assumption_rows = _csv_rows(
            case_dir / "07_validation_governance" / "assumptions.csv"
        )
        assumption_ids = [row["assumption_id"].strip() for row in assumption_rows]
        if not all(assumption_ids) or len(assumption_ids) != len(set(assumption_ids)):
            raise ValueError("assumption IDs must be nonempty and unique")
        assumption_by_id = dict(zip(assumption_ids, assumption_rows))
        known_source_ids = {
            receipt.source_id for receipt in receipts
            if receipt.metadata.cutoff_eligible
            and known_at_cutoff(receipt.first_public_at, case.analysis_cutoff)
        }
        known_evidence_ids = set(assumption_by_id) | known_source_ids
        unresolved = sorted({
            override.evidence_or_assumption_id for override in overrides
            if override.evidence_or_assumption_id not in known_evidence_ids
        })
        if unresolved:
            raise ValueError(f"Scenario evidence or assumption ID is unresolved: {unresolved}")
        for override in overrides:
            assumption = assumption_by_id.get(override.evidence_or_assumption_id)
            if assumption is not None:
                _verify_scenario_assumption(override, assumption)
        scenario_result = project_cash_scenario(spec, normalized, overrides)

    normalized_header = _csv_header(core_dir / "normalized_actuals.csv")
    normalized_rows = tuple(fact.as_csv_row() for fact in normalized)
    if set(normalized_header) != set(normalized_rows[0]):
        raise ValueError("normalized_actuals.csv header does not match the Core output contract")
    outputs = {
        "schema_version": SCHEMA_VERSION,
        "case_id": case.case_id,
        "analysis_cutoff": case.analysis_cutoff.isoformat(),
        "cash_identity": identity.as_dict(),
        "scenario_cash": scenario_result.as_dict() if scenario_result else None,
        "cash_components": [result.as_dict() for result in component_results],
    }
    memo_fields = [cash_identity_memo_field(identity).as_dict()]
    if scenario_result:
        memo_fields.append(scenario_cash_memo_field(scenario_result).as_dict())
    memo = {"schema_version": SCHEMA_VERSION, "case_id": case.case_id, "fields": memo_fields}
    artifacts = {
        "normalized_actuals.csv": _csv_bytes(normalized_header, normalized_rows),
        "core_outputs.json": _json_bytes(outputs),
        "memo_fields.json": _json_bytes(memo),
    }

    input_file_hashes = _file_hashes(case_dir, INPUT_FILES)
    if input_file_hashes != initial_input_hashes:
        raise ValueError("Core build inputs changed during calculation")
    for entry in entries:
        verify_snapshot_content(evidence_dir, entry.receipt)
    for bridge in bridges:
        verify_snapshot_content(evidence_dir, receipt_by_id[bridge.provenance.snapshot_id])
    code_root = Path(__file__).resolve().parents[1]
    code_file_hashes = _file_hashes(code_root, CODE_FILES)
    output_file_hashes = {name: _sha256(data) for name, data in sorted(artifacts.items())}
    input_hash = _sha256(_json_bytes(input_file_hashes))
    code_hash = _sha256(_json_bytes(code_file_hashes))
    output_hash = _sha256(_json_bytes(output_file_hashes))
    build_hash = _sha256(
        _json_bytes({"input_hash": input_hash, "code_hash": code_hash, "output_hash": output_hash})
    )
    build_id = f"core_{build_hash}"
    build_dir = build_root / case.case_id / build_id
    if build_dir.exists():
        raise FileExistsError(f"Core build already exists: {build_dir}")
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "case_id": case.case_id,
        "build_id": build_id,
        "build_state": "STAGING_ONLY",
        "analysis_cutoff": case.analysis_cutoff.isoformat(),
        "source_snapshot_ids": sorted(
            {entry.fact.snapshot_id for entry in entries}
            | {bridge.provenance.snapshot_id for bridge in bridges}
        ),
        "locator_only_snapshot_ids": sorted(locator_only),
        "input_hash": input_hash,
        "code_hash": code_hash,
        "output_hash": output_hash,
        "input_file_hashes": input_file_hashes,
        "code_file_hashes": code_file_hashes,
        "output_file_hashes": output_file_hashes,
    }
    artifacts["build_metadata.json"] = _json_bytes(metadata)

    _write_new_build(build_dir, artifacts)
    return build_dir


def _csv_rows(path: Path) -> tuple[dict[str, str], ...]:
    """Read a case CSV contract; domain constructors validate its populated rows."""

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f"Invalid CSV header: {path}")
        required = REQUIRED_CSV_COLUMNS[path.name]
        if not set(required).issubset(reader.fieldnames):
            raise ValueError(f"Missing required CSV columns: {path}")
        rows = tuple(dict(row) for row in reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError(f"CSV row width does not match its header: {path}")
    return rows


def _verify_scenario_assumption(
    override: ScenarioDriverOverride, row: Mapping[str, str]
) -> None:
    """Require a registered assumption to describe the exact scenario override."""

    assumption_id = override.evidence_or_assumption_id
    try:
        value = Decimal(row["value"].strip())
    except InvalidOperation as exc:
        raise ValueError(f"Scenario assumption value is not decimal: {assumption_id}") from exc
    if not value.is_finite():
        raise ValueError(f"Scenario assumption value is not finite: {assumption_id}")
    matches = (
        row["scenario_id"].strip() == override.scenario_id
        and row["variable"].strip() == override.driver_id
        and value == override.input_value
        and row["unit"].strip() == override.input_unit
        and row["mechanism"].strip() == override.mechanism
    )
    if not matches:
        raise ValueError(f"Scenario assumption does not match override: {assumption_id}")
    if row["status"].strip().upper() not in {
        "REVIEWED", "APPROVED", "REVIEWED_SYNTHETIC"
    }:
        raise ValueError(f"Scenario assumption is not reviewed or approved: {assumption_id}")


def _aggregate_component_groups(
    case_id: str, normalized: tuple[NormalizedFact, ...], rules: tuple[CashComponentRule, ...]
) -> tuple[CashInclusionResult, ...]:
    if not rules:
        return ()
    by_metric: dict[str, CashComponentRule] = {}
    for rule in rules:
        if rule.metric_id in by_metric:
            raise ValueError(f"Multiple cash component rules for metric: {rule.metric_id}")
        by_metric[rule.metric_id] = rule
    groups: dict[tuple[str, ...], list[CashComponentInput]] = {}
    found_metrics: set[str] = set()
    for fact in normalized:
        rule = by_metric.get(fact.metric_id)
        if rule is None:
            continue
        found_metrics.add(fact.metric_id)
        key = (
            fact.case_id, fact.version_id, *fact.scope.key(), *fact.period.key(),
            fact.currency, fact.unit,
        )
        groups.setdefault(key, []).append(CashComponentInput(rule, fact))
    missing = set(by_metric) - found_metrics
    if missing:
        raise ValueError(f"Cash component metric has no normalized fact: {sorted(missing)}")
    return tuple(
        aggregate_cash_components(
            groups[key], case_id=case_id, version_id=groups[key][0].fact.version_id
        )
        for key in sorted(groups)
    )


def _write_new_build(build_dir: Path, artifacts: Mapping[str, bytes]) -> None:
    """Write complete staging files, then rename into an unused content ID."""

    parent = build_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    if parent.is_symlink() or build_dir.exists():
        raise FileExistsError(f"Core build already exists or has an unsafe parent: {build_dir}")
    staging = Path(tempfile.mkdtemp(prefix=".core_staging_", dir=parent))
    try:
        for name, payload in artifacts.items():
            with (staging / name).open("xb") as handle:
                handle.write(payload)
        resolved_parent = parent.resolve()
        if (
            staging.resolve().parent != resolved_parent
            or build_dir.resolve().parent != resolved_parent
        ):
            raise ValueError("Core build staging or target escaped the build case directory")
        if build_dir.exists():
            raise FileExistsError(f"Core build already exists: {build_dir}")
        staging.rename(build_dir)
    finally:
        if staging.exists():
            for name in artifacts:
                (staging / name).unlink(missing_ok=True)
            staging.rmdir()


def _csv_header(path: Path) -> tuple[str, ...]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle), None)
    if not header or len(header) != len(set(header)):
        raise ValueError(f"Invalid CSV header: {path}")
    return tuple(header)


def _csv_bytes(header: tuple[str, ...], rows: tuple[Mapping[str, str], ...]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=header, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_regular_file(path: Path) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Expected a regular input file: {path}")
    return path.read_bytes()


def _file_hashes(root: Path, paths: tuple[str, ...]) -> dict[str, str]:
    return {name: _sha256(_read_regular_file(root / name)) for name in sorted(paths)}
