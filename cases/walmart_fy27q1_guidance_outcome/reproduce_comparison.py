"""Recreate the limited Q1 FY27 actual-to-public-guidance outcome artifact.

Run from the repository root with ``python cases/walmart_fy27q1_guidance_outcome/reproduce_comparison.py``.
Only local numeric facts and source locators are read; no network fetch is needed.
"""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "src"))

from versioned_finance_core.contracts import (
    FinancialVersion,
    MappingRule,
    MetricDefinition,
    RawFact,
    ScopeBridge,
    VersionType,
)
from versioned_finance_core.evidence import (
    load_provenanced_facts,
    load_source_ledger,
)
from versioned_finance_core.financial_core import normalize_actuals
from versioned_finance_core.modules.m1 import (
    ComparableMetric,
    PublicGuidanceRange,
    compare_actual_to_public_guidance_range,
)

CASE = Path(__file__).resolve().parent
GUIDANCE_SOURCE = "wmt_guidance_fy27q1_20260219"
ACTUAL_SOURCE = "wmt_actual_fy27q1_presentation_20260521"


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    evidence = CASE / "01_evidence_core"
    core = CASE / "02_financial_core"
    m1 = CASE / "03_m1_operating_forecast_valuation"
    case = json.loads((CASE / "00_charter" / "case.json").read_text(encoding="utf-8"))
    cutoff = datetime.fromisoformat(case["analysis_cutoff"])
    receipts = {}
    for receipt in load_source_ledger(evidence):
        if receipt.source_id in receipts:
            raise ValueError(f"Explicit snapshot selection required: {receipt.source_id}")
        receipts[receipt.source_id] = receipt
    for source_id in (GUIDANCE_SOURCE, ACTUAL_SOURCE):
        receipt = receipts[source_id]
        if not receipt.metadata.cutoff_eligible or not receipt.metadata.transformation_right:
            raise ValueError(f"Source is not eligible for numeric transformation: {source_id}")
        if receipt.first_public_at is None or receipt.first_public_at > cutoff:
            raise ValueError(f"Source is unavailable at cutoff: {source_id}")

    versions = tuple(FinancialVersion.from_mapping(row) for row in _rows(core / "versions.csv"))
    version_by_id = {version.version_id: version for version in versions}
    normalized = normalize_actuals(
        case["case_id"],
        (RawFact.from_mapping(entry.as_csv_row()) for entry in load_provenanced_facts(evidence)),
        (MappingRule.from_mapping(row) for row in _rows(evidence / "mappings.csv")),
        (MetricDefinition.from_mapping(row) for row in _rows(evidence / "metric_dictionary.csv")),
        versions,
        cutoff,
        scope_bridges=(
            ScopeBridge.from_mapping(row) for row in _rows(evidence / "scope_bridges.csv")
        ),
    )
    stored = _rows(core / "normalized_actuals.csv")
    generated = [fact.as_csv_row() for fact in normalized]
    if stored != generated:
        raise ValueError("Pinned normalized_actuals.csv differs from Core normalization")
    if len(normalized) != 3:
        raise ValueError("This limited case expects three same-definition actual metrics")

    guidance_rows = _rows(m1 / "forecast_versions.csv")
    if len(guidance_rows) != 6:
        raise ValueError("The public guidance requires lower and upper bounds for three metrics")
    guidance_by_key = {(row["metric_id"], row["scenario_id"]): row for row in guidance_rows}
    if len(guidance_by_key) != len(guidance_rows):
        raise ValueError("Duplicate public guidance bound")
    guidance_receipt = receipts[GUIDANCE_SOURCE]
    outputs = []
    for fact in normalized:
        lower = guidance_by_key[(fact.metric_id, "PUBLIC_GUIDANCE_LOWER")]
        upper = guidance_by_key[(fact.metric_id, "PUBLIC_GUIDANCE_UPPER")]
        if lower["version_id"] != upper["version_id"]:
            raise ValueError("Guidance bounds have different versions")
        if lower["driver_or_assumption_id"] != GUIDANCE_SOURCE or upper["driver_or_assumption_id"] != GUIDANCE_SOURCE:
            raise ValueError("Guidance bounds lack original source")
        for row in (lower, upper):
            if (
                row["metric_id"] != fact.metric_id
                or row["economic_scope_id"] != fact.scope.economic_scope_id
                or row["period_start"] != fact.period.start.isoformat()
                or row["period_end"] != fact.period.end.isoformat()
                or row["currency"] != fact.currency
                or row["unit"] != fact.unit
            ):
                raise ValueError(f"Guidance and actual grain differs: {fact.metric_id}")
            if (
                row["source_snapshot_id"] != guidance_receipt.snapshot_id
                or row["source_content_sha256"] != guidance_receipt.content_sha256
                or datetime.fromisoformat(row["source_first_public_at"])
                != guidance_receipt.first_public_at
            ):
                raise ValueError(f"Guidance bound source receipt differs: {fact.metric_id}")
        guidance_version = version_by_id[lower["version_id"]]
        actual_version = version_by_id[fact.version_id]
        if guidance_version.version_type is not VersionType.PUBLIC_TARGET_OR_GUIDANCE:
            raise ValueError("The comparison reference must remain public company guidance")
        if actual_version.version_type is not VersionType.PUBLIC_ACTUAL:
            raise ValueError("The outcome must remain a public actual")
        if guidance_version.information_cutoff >= actual_version.information_cutoff:
            raise ValueError("Guidance version is not prior to actual version")
        if guidance_version.information_cutoff != guidance_receipt.first_public_at:
            raise ValueError("Guidance version is not pinned to its source publication bound")
        if not isinstance(fact.value, Decimal):
            raise TypeError(f"Actual metric is not a known Decimal: {fact.metric_id}")
        guidance = PublicGuidanceRange(
            metric_id=fact.metric_id,
            economic_scope_id=fact.scope.economic_scope_id,
            legal_entity_id=fact.scope.legal_entity_id,
            period_start=fact.period.start,
            period_end=fact.period.end,
            currency=fact.currency,
            unit=fact.unit,
            version_id=guidance_version.version_id,
            available_at=guidance_receipt.first_public_at,
            lower_bound=Decimal(lower["value"]),
            upper_bound=Decimal(upper["value"]),
            source_id=GUIDANCE_SOURCE,
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
        result = compare_actual_to_public_guidance_range(
            guidance,
            actual,
            actual_source_id=fact.provenance.source_id,
            comparison_basis_id=f"basis_{fact.metric_id}_v1",
            information_cutoff=cutoff,
        )
        outputs.append(result.as_dict())
    artifact = {
        "schema_version": 1,
        "case_id": case["case_id"],
        "analysis_cutoff": case["analysis_cutoff"],
        "coverage_state": "FEASIBILITY_ONLY",
        "claim_scope": "Published Q1 actual versus prior public guidance bounds; no cause attribution",
        "source_ids": [GUIDANCE_SOURCE, ACTUAL_SOURCE],
        "comparisons": sorted(outputs, key=lambda item: item["metric_id"]),
    }
    print(json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
