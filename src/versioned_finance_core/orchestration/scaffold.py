from __future__ import annotations

import csv
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from versioned_finance_core.contracts.models import CaseContract
from versioned_finance_core.evidence import load_provenanced_facts, load_source_ledger

CASE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

REQUIRED_PATHS = (
    "00_charter/case.json",
    "00_charter/intended_and_prohibited_use.md",
    "00_charter/activation_gates.json",
    "01_evidence_core/source_ledger.csv",
    "01_evidence_core/raw_facts.csv",
    "01_evidence_core/mappings.csv",
    "01_evidence_core/scope_bridges.csv",
    "01_evidence_core/metric_dictionary.csv",
    "02_financial_core/normalized_actuals.csv",
    "02_financial_core/cash_components.csv",
    "02_financial_core/versions.csv",
    "02_financial_core/scenarios.csv",
    "02_financial_core/cash_identity_checks.csv",
    "03_m1_operating_forecast_valuation/README.md",
    "04_m2_capital_allocation/README.md",
    "05_m3_credit_liquidity_claims/README.md",
    "07_validation_governance/gate_results.csv",
    "release/release_manifest.json",
)

REQUIRED_CSV_COLUMNS = {
    "01_evidence_core/source_ledger.csv": {
        "source_id", "snapshot_id", "content_sha256", "first_public_at", "retrieved_at",
        "access_class", "retention_right", "transformation_right", "redistribution_right",
    },
    "01_evidence_core/raw_facts.csv": {
        "fact_id", "source_id", "snapshot_id", "content_sha256", "first_public_at",
        "retrieved_at", "version_id", "economic_scope_id", "accounting_scope",
        "period_start", "period_end", "period_type", "currency", "unit",
        "raw_account_id", "raw_value", "mapping_version", "claim_tag",
    },
    "01_evidence_core/mappings.csv": {
        "mapping_id", "source_id", "raw_account_id", "normalized_metric_id",
        "sign_multiplier", "review_status",
    },
    "01_evidence_core/scope_bridges.csv": {
        "bridge_id", "economic_scope_id", "legal_entity_id", "source_id",
        "first_public_at", "retrieved_at", "snapshot_id", "content_sha256",
        "review_status",
    },
    "01_evidence_core/metric_dictionary.csv": {
        "metric_id", "grain", "period_type", "currency_policy", "unit",
        "sign_convention", "review_status",
    },
    "02_financial_core/normalized_actuals.csv": {
        "fact_id", "source_fact_id", "source_id", "snapshot_id", "content_sha256",
        "first_public_at", "retrieved_at", "case_id", "economic_scope_id",
        "accounting_scope", "metric_id", "period_start", "period_end",
        "period_type", "currency", "unit", "value", "version_id", "claim_tag",
    },
    "02_financial_core/cash_components.csv": {
        "cash_component_id", "metric_id", "tax_basis", "obligation_id",
        "funding_source_id", "included_in_fcff", "included_in_fcfe",
        "included_in_cfads", "included_in_debt_service",
        "included_in_liquidity", "included_in_sources_uses", "double_count_check",
    },
    "02_financial_core/versions.csv": {
        "version_id", "version_type", "as_of_date", "publication_status",
        "supersedes_version_id", "information_cutoff", "immutable",
    },
    "02_financial_core/scenarios.csv": {
        "scenario_id", "scenario_purpose", "version_id", "baseline_version_id",
        "driver_id", "period_start", "period_end", "input_value", "input_unit",
        "evidence_or_assumption_id", "mechanism", "review_status",
    },
    "02_financial_core/cash_identity_checks.csv": {
        "identity_id", "version_id", "opening_cash_fact_id", "operating_cash_flow_fact_id",
        "investing_cash_flow_fact_id", "financing_cash_flow_fact_id",
        "fx_and_other_fact_id", "closing_cash_fact_id",
    },
}


def initialize_case(case_id: str, cases_dir: Path, template_dir: Path) -> Path:
    """Copy the canonical case template without overwriting an existing case."""

    if not CASE_ID_PATTERN.fullmatch(case_id):
        raise ValueError("case_id must use lowercase letters, digits, underscores or hyphens")
    if case_id == "_template":
        raise ValueError("_template is reserved")
    if not template_dir.is_dir():
        raise FileNotFoundError(f"Template directory not found: {template_dir}")

    destination = cases_dir / case_id
    if destination.exists():
        raise FileExistsError(f"Case already exists: {destination}")

    cases_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(template_dir, destination)
    case_path = destination / "00_charter" / "case.json"
    data = json.loads(case_path.read_text(encoding="utf-8"))
    data["case_id"] = case_id
    data["status"] = "DRAFT"
    case_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_path = destination / "release" / "release_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["case_id"] = case_id
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return destination


def validate_case(case_dir: Path, release_ready: bool = False) -> tuple[list[str], list[str]]:
    """Return structural errors and readiness warnings for a case directory."""

    errors: list[str] = []
    warnings: list[str] = []
    if not case_dir.is_dir():
        return [f"Case directory not found: {case_dir}"], warnings

    for relative_path in REQUIRED_PATHS:
        if not (case_dir / relative_path).is_file():
            errors.append(f"Missing required file: {relative_path}")

    for relative_path, required in REQUIRED_CSV_COLUMNS.items():
        path = case_dir / relative_path
        if not path.is_file():
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            header = next(csv.reader(handle), [])
        if len(header) != len(set(header)):
            errors.append(f"Duplicate CSV columns: {relative_path}")
        missing = required.difference(header)
        if missing:
            errors.append(
                f"Missing CSV columns in {relative_path}: {', '.join(sorted(missing))}"
            )

    evidence_dir = case_dir / "01_evidence_core"
    if (evidence_dir / "source_ledger.csv").is_file():
        try:
            load_source_ledger(evidence_dir)
        except (ValueError, TypeError, KeyError, csv.Error) as exc:
            errors.append(f"Invalid source_ledger.csv: {exc}")
    if (evidence_dir / "raw_facts.csv").is_file():
        try:
            load_provenanced_facts(evidence_dir)
        except (ValueError, TypeError, KeyError, csv.Error) as exc:
            errors.append(f"Invalid raw_facts.csv lineage: {exc}")

    case_path = case_dir / "00_charter" / "case.json"
    contract: CaseContract | None = None
    if case_path.is_file():
        try:
            data = json.loads(case_path.read_text(encoding="utf-8"))
            contract = CaseContract.from_mapping(data)
            if case_dir.name != "_template" and contract.case_id != case_dir.name:
                errors.append("case.json case_id does not match the case directory")
            readiness = contract.release_readiness_issues()
            if release_ready:
                errors.extend(readiness)
            else:
                warnings.extend(readiness)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            errors.append(f"Invalid case.json: {exc}")

    manifest_path = case_dir / "release" / "release_manifest.json"
    if case_dir.name != "_template" and manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(manifest, dict):
                raise TypeError("manifest must be a JSON object")
            if manifest.get("case_id") != case_dir.name:
                errors.append("release_manifest.json case_id does not match the case directory")
            if manifest.get("publication_state") != "WITHHELD":
                errors.append("case-local release_manifest.json must remain WITHHELD")
            if contract and contract.status != "DRAFT" and contract.analysis_cutoff:
                raw_cutoff = manifest.get("cutoff_timestamp")
                if not isinstance(raw_cutoff, str):
                    errors.append("release_manifest.json cutoff differs from case.json")
                else:
                    manifest_cutoff = datetime.fromisoformat(raw_cutoff)
                    if manifest_cutoff.tzinfo is None or manifest_cutoff != contract.analysis_cutoff:
                        errors.append("release_manifest.json cutoff differs from case.json")
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            errors.append(f"Invalid release_manifest.json: {exc}")

    return errors, warnings

