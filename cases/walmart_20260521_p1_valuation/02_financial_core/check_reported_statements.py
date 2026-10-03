"""Project the staged Core facts into exact reported P&L/BS identity checks.

Run from the repository root, supplying a ``build-core`` staging directory::

    python cases/walmart_20260521_p1_valuation/02_financial_core/check_reported_statements.py \
      --normalized-actuals build/p1_pilot/walmart_20260521_p1_valuation/core_.../normalized_actuals.csv \
      --output cases/walmart_20260521_p1_valuation/02_financial_core/reported_statement_checks.json

The output uses an exclusive create and never overwrites an existing result.
There is no source fetching and no financial formula outside ``financial_core``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from versioned_finance_core.contracts import (
    CaseContract,
    ClaimTag,
    NormalizedFact,
    Period,
    PublicationStatus,
    ScopeRef,
    SourceProvenance,
    decimal_value,
)
from versioned_finance_core.financial_core import (
    evaluate_reported_balance_sheet_identity,
    evaluate_reported_operating_income_identity,
)

CASE = Path(__file__).resolve().parents[1]
YEAR_METRICS = (
    "net_sales_year",
    "operating_income_year",
    "operating_cash_flow_year",
    "capital_expenditure_payments_year",
)
PL_ROLES = ("total_revenue", "cost_of_sales", "operating_sga", "operating_income")
BS_ROLES = ("total_assets", "total_liabilities_equity")
FY26_10K_VERSION = "wmt_actual_fy26_10k_20260313"


def _normalized_fact(row: dict[str, str]) -> NormalizedFact:
    return NormalizedFact(
        fact_id=row["fact_id"],
        source_fact_id=row["source_fact_id"],
        provenance=SourceProvenance.from_mapping(row),
        case_id=row["case_id"],
        scope=ScopeRef.from_mapping(row),
        metric_id=row["metric_id"],
        period=Period.from_mapping(row),
        currency=row["currency"],
        unit=row["unit"],
        value=decimal_value(row["value"]),
        version_id=row["version_id"],
        publication_status=PublicationStatus(row["publication_status"]),
        normalization_rule=row["normalization_rule"],
        mapping_version=row["mapping_version"],
        claim_tag=ClaimTag(row["claim_tag"]),
    )


def _read_normalized(path: Path) -> tuple[tuple[NormalizedFact, ...], str]:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Expected a regular staged normalized file: {path}")
    data = path.read_bytes()
    text = data.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise ValueError("Staged normalized CSV has invalid or duplicate columns")
    facts = tuple(_normalized_fact(row) for row in reader)
    if not facts:
        raise ValueError("Staged normalized CSV contains no facts")
    return facts, hashlib.sha256(data).hexdigest()


def build_report(
    facts: tuple[NormalizedFact, ...], normalized_sha256: str, case: CaseContract
) -> dict[str, object]:
    """Assemble Core identity results and source fact projections, with no formulas."""

    if case.analysis_cutoff is None:
        raise ValueError("Case requires analysis_cutoff")
    if any(fact.case_id != case.case_id for fact in facts):
        raise ValueError("Staged normalized fact case_id differs from case charter")
    if any(fact.currency != case.reporting_currency for fact in facts):
        raise ValueError("Staged normalized fact currency differs from case charter")
    if any(fact.provenance.first_public_at > case.analysis_cutoff for fact in facts):
        raise ValueError("Staged normalized fact was first public after case cutoff")

    groups: dict[tuple[object, ...], dict[str, NormalizedFact]] = defaultdict(dict)
    for fact in facts:
        key = (
            fact.case_id, fact.version_id, fact.scope, fact.period, fact.currency, fact.unit
        )
        if fact.metric_id in groups[key]:
            raise ValueError(f"Duplicate normalized metric at one grain: {fact.metric_id}")
        groups[key][fact.metric_id] = fact

    checks: list[dict[str, object]] = []
    incomplete: list[dict[str, object]] = []
    for key in sorted(groups, key=lambda value: (
        value[1], value[3].end.isoformat(), value[3].start.isoformat(), value[2].key()
    )):
        by_metric = groups[key]
        period = key[3]
        if period.period_type == "INSTANT":
            required = BS_ROLES
            kind = "BALANCE_SHEET"
            checker = evaluate_reported_balance_sheet_identity
        elif period.period_type in ("YEAR", "QUARTER"):
            required = tuple(f"{role}_{period.period_type.lower()}" for role in PL_ROLES)
            kind = "OPERATING_INCOME"
            checker = evaluate_reported_operating_income_identity
        else:
            continue
        present = set(required) & by_metric.keys()
        if not present:
            continue
        missing = sorted(set(required) - by_metric.keys())
        if missing:
            incomplete.append({
                "identity_kind": kind,
                "version_id": key[1],
                "period_start": period.start.isoformat(),
                "period_end": period.end.isoformat(),
                "period_type": period.period_type,
                "missing_metric_ids": missing,
                "knowledge_state": "NOT_TESTABLE_FROM_PUBLIC_DATA",
            })
            continue
        result = checker(
            *(by_metric[metric] for metric in required), analysis_cutoff=case.analysis_cutoff
        )
        checks.append(result.as_dict())

    trend_rows: list[dict[str, str]] = []
    trend_missing: list[dict[str, str]] = []
    annual_groups = sorted(
        ((key, values) for key, values in groups.items()
         if key[1] == FY26_10K_VERSION and key[3].period_type == "YEAR"
         and key[2].economic_scope_id == case.economic_scope_id),
        key=lambda item: item[0][3].end,
    )
    for key, by_metric in annual_groups:
        for metric in YEAR_METRICS:
            fact = by_metric.get(metric)
            if fact is None:
                trend_missing.append({
                    "version_id": key[1],
                    "period_end": key[3].end.isoformat(),
                    "metric_id": metric,
                })
                continue
            trend_rows.append({
                "version_id": fact.version_id,
                "period_start": fact.period.start.isoformat(),
                "period_end": fact.period.end.isoformat(),
                "metric_id": fact.metric_id,
                "value": str(fact.value),
                "currency": fact.currency,
                "unit": fact.unit,
                "normalized_fact_id": fact.fact_id,
                "source_fact_id": fact.source_fact_id,
                "source_id": fact.provenance.source_id,
                "source_content_sha256": fact.provenance.content_sha256,
            })
    return {
        "case_id": case.case_id,
        "analysis_cutoff": case.analysis_cutoff.isoformat(),
        "normalized_actuals_sha256": normalized_sha256,
        "normalized_fact_count": len(facts),
        "check_count": len(checks),
        "reconciled_count": sum(check["reconciled"] is True for check in checks),
        "checks": checks,
        "incomplete_checks": incomplete,
        "annual_reported_trend_facts": trend_rows,
        "annual_reported_trend_missing": trend_missing,
        "limitations": [
            ("Balance-sheet check compares reported assets with reported liabilities-and-equity "
             "total; it does not derive a standalone liabilities total."),
            ("P&L check covers reported revenue, cost of sales, operating SG&A, and operating "
             "income only; it is not a linked forecast or valuation model."),
            ("Reported source identity checks do not constitute independent evidence review "
             "or release approval."),
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--normalized-actuals", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    case = CaseContract.from_mapping(json.loads((CASE / "00_charter" / "case.json").read_text(
        encoding="utf-8"
    )))
    facts, source_hash = _read_normalized(args.normalized_actuals)
    report = build_report(facts, source_hash, case)
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    with args.output.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
    print(json.dumps({
        "output": str(args.output),
        "check_count": report["check_count"],
        "reconciled_count": report["reconciled_count"],
        "trend_fact_count": len(report["annual_reported_trend_facts"]),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
