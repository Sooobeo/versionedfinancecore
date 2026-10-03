"""Project canonical normalized facts into a deterministic, ID-linked index.

This script performs no financial calculation. Values and output IDs are read
from ``build_core`` staging outputs; the resulting JSON is only a navigation
artifact for P1 research and does not replace the Core output.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

KEY_METRICS = {
    "net_sales_year", "total_revenue_year", "operating_income_year",
    "consolidated_net_income_year", "depreciation_amortization_year",
    "operating_cash_flow_year", "capital_expenditure_payments_year",
    "net_sales_quarter", "total_revenue_quarter", "operating_income_quarter",
    "consolidated_net_income_quarter", "depreciation_amortization_quarter",
    "operating_cash_flow_quarter", "capital_expenditure_payments_quarter",
    "cash_restricted_begin", "cash_restricted_end", "cash_and_equivalents",
    "total_assets", "total_liabilities_equity", "current_debt",
    "noncurrent_debt", "short_term_borrowings", "total_equity",
}


def write_summary(build_dir: Path, destination: Path) -> str:
    with (build_dir / "normalized_actuals.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    outputs = json.loads((build_dir / "core_outputs.json").read_text(encoding="utf-8"))
    metadata = json.loads((build_dir / "build_metadata.json").read_text(encoding="utf-8"))
    facts = [{
        "normalized_fact_id": row["fact_id"],
        "raw_fact_id": row["source_fact_id"],
        "source_id": row["source_id"],
        "snapshot_id": row["snapshot_id"],
        "content_sha256": row["content_sha256"],
        "first_public_at": row["first_public_at"],
        "metric_id": row["metric_id"],
        "period_start": row["period_start"],
        "period_end": row["period_end"],
        "period_type": row["period_type"],
        "accounting_scope": row["accounting_scope"],
        "economic_scope_id": row["economic_scope_id"],
        "version_id": row["version_id"],
        "value": row["value"],
        "currency": row["currency"],
        "unit": row["unit"],
        "claim_tag": row["claim_tag"],
    } for row in rows if row["metric_id"] in KEY_METRICS]
    facts.sort(key=lambda row: (
        row["metric_id"], row["period_end"], row["period_start"],
        row["version_id"], row["normalized_fact_id"],
    ))
    payload = {
        "case_id": "walmart_20260521_p1_valuation",
        "state": "SOURCE_FACT_INDEX_ONLY",
        "cutoff": "2026-05-21T23:59:59-04:00",
        "sec_parser_sha256": hashlib.sha256(
            (Path(__file__).with_name("ingest_sec_financials.py")).read_bytes()
        ).hexdigest(),
        "input_hash": metadata["input_hash"],
        "core_output_hash": metadata["output_hash"],
        "source_snapshot_ids": metadata["source_snapshot_ids"],
        "locator_only_snapshot_ids": metadata["locator_only_snapshot_ids"],
        "cash_identity": outputs["cash_identity"],
        "all_normalized_fact_count": len(rows),
        "facts": facts,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    payload["source_summary_id"] = "source_summary_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    destination.write_text(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload["source_summary_id"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("build_dir", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(write_summary(args.build_dir, args.destination))
