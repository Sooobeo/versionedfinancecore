"""Offline source-vintage and three-statement evidence checks for Walmart P1."""

from __future__ import annotations

import csv
import hashlib
import json
import runpy
from datetime import datetime
from decimal import Decimal
from html import escape
from pathlib import Path

from versioned_finance_core.evidence import (
    load_provenanced_facts,
    load_source_ledger,
    select_known_facts,
)
from versioned_finance_core.orchestration.core_build import build_core

ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "cases" / "walmart_20260521_p1_valuation"
EVIDENCE = CASE / "01_evidence_core"
SCRIPT = EVIDENCE / "ingest_sec_financials.py"
SUPPLEMENT = EVIDENCE / "ingest_sec_q1_balance_supplement.py"


def _load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _fact(
    rows: list[dict[str, str]], metric: str, period_end: str, version: str,
) -> dict[str, str]:
    matches = [row for row in rows if row["metric_id"] == metric
               and row["period_end"] == period_end and row["version_id"] == version]
    assert len(matches) == 1, (metric, period_end, version, len(matches))
    return matches[0]


def test_walmart_p1_source_receipts_are_cutoff_pinned_and_locator_only() -> None:
    receipts = load_source_ledger(EVIDENCE)
    assert len(receipts) == 4
    expected = {
        "wmt_fy25_10k_xbrl_20250314": {"5fcf3e216138d1e38cd8365f789f7f76a083295f5424fa0b4e1794c43f2a40ff"},
        "wmt_fy26_10k_xbrl_20260313": {"07c72faa90cf8515eb1ff1ca264361ca8741c2663202d2f5a25ff9c694f4ef67"},
        "wmt_fy27q1_8k_ex991_20260521": {
            "0107dd5fe2d6677d96f95b409c9a59d420da337eba515e4204fc34ea0e66b93d",
            "1da651ebab33b75f8057857ddc7c75d01ef3bf20642d169ac94321a311e49a1a",
        },
    }
    cutoff = datetime.fromisoformat("2026-05-21T23:59:59-04:00")
    for receipt in receipts:
        assert receipt.content_sha256 in expected[receipt.source_id]
        assert receipt.first_public_at is not None and receipt.first_public_at <= cutoff
        assert receipt.metadata.cutoff_eligible
        assert receipt.metadata.transformation_right
        assert not receipt.metadata.retention_right
        assert not receipt.metadata.redistribution_right
    assert not list((EVIDENCE / "raw_snapshots").glob("*/*"))
    assert len(load_provenanced_facts(EVIDENCE)) == 205
    before_q1 = datetime.fromisoformat("2026-05-20T23:59:59-04:00")
    known = select_known_facts(load_provenanced_facts(EVIDENCE), before_q1)
    assert len(known) == 83
    assert all(entry.fact.source_id != "wmt_fy27q1_8k_ex991_20260521" for entry in known)


def test_walmart_p1_offline_core_build_reconciles_annual_and_q1_cash(tmp_path: Path) -> None:
    build = build_core(CASE, tmp_path / "build")
    repeated = build_core(CASE, tmp_path / "repeat")
    assert build.name == repeated.name
    for name in ("normalized_actuals.csv", "core_outputs.json", "build_metadata.json"):
        assert (build / name).read_bytes() == (repeated / name).read_bytes()
    rows = _load_rows(build / "normalized_actuals.csv")
    assert len(rows) == 205
    assert {row["claim_tag"] for row in rows} == {"D"}
    output = json.loads((build / "core_outputs.json").read_text(encoding="utf-8"))
    metadata = json.loads((build / "build_metadata.json").read_text(encoding="utf-8"))
    source_summary = json.loads(
        (CASE / "02_financial_core" / "historical_source_summary.json").read_text(encoding="utf-8")
    )
    assert source_summary["sec_parser_sha256"] == hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    assert source_summary["input_hash"] == metadata["input_hash"]
    assert source_summary["core_output_hash"] == metadata["output_hash"]
    assert source_summary["all_normalized_fact_count"] == len(rows)
    annual_cash = output["cash_identity"]
    assert source_summary["cash_identity"]["output_id"] == annual_cash["output_id"]
    assert annual_cash["version_id"] == "wmt_actual_fy26_10k_20260313"
    assert annual_cash["reported_closing_cash"] == "11321000000"
    assert annual_cash["residual"] == "0"
    assert annual_cash["output_id"].startswith("cash_")

    annual = "wmt_actual_fy26_10k_20260313"
    quarter = "wmt_actual_fy27q1_8k_20260521"
    value = lambda metric, end, version: Decimal(_fact(rows, metric, end, version)["value"])
    assert value("net_sales_year", "2026-01-31", annual) == Decimal(706413000000)
    assert value("operating_income_year", "2026-01-31", annual) == Decimal(29825000000)
    assert value("operating_cash_flow_year", "2026-01-31", annual) == Decimal(41565000000)
    assert value("capital_expenditure_payments_year", "2026-01-31", annual) == Decimal(26642000000)
    assert value("net_sales_quarter", "2026-04-30", quarter) == Decimal(175684000000)
    assert value("operating_cash_flow_quarter", "2026-04-30", quarter) == Decimal(4738000000)
    assert value("capital_expenditure_payments_quarter", "2026-04-30", quarter) == Decimal(6684000000)
    assert (
        value("cash_restricted_begin", "2026-01-31", quarter)
        + value("operating_cash_flow_quarter", "2026-04-30", quarter)
        + value("investing_cash_flow_quarter", "2026-04-30", quarter)
        + value("financing_cash_flow_quarter", "2026-04-30", quarter)
        + value("fx_effect_on_cash_quarter", "2026-04-30", quarter)
        == value("cash_restricted_end", "2026-04-30", quarter)
        == Decimal(11319000000)
    )
    # CF includes restricted cash; BS cash and equivalents does not.
    assert value("cash_restricted_end", "2026-01-31", annual) - value("cash_and_equivalents", "2026-01-31", annual) == Decimal(594000000)
    assert value("cash_restricted_end", "2026-04-30", quarter) - value("cash_and_equivalents", "2026-04-30", quarter) == Decimal(590000000)
    assert value("prepaid_other_current_assets", "2026-04-30", quarter) == Decimal(4433000000)
    assert value("prepaid_other_current_assets", "2026-01-31", quarter) == Decimal(4124000000)
    assert value("accrued_income_taxes", "2026-04-30", quarter) == Decimal(1174000000)
    assert value("accrued_income_taxes", "2026-01-31", quarter) == Decimal(596000000)
    assert value("finance_lease_current", "2026-04-30", quarter) == Decimal(851000000)
    assert value("finance_lease_long_term", "2026-04-30", quarter) == Decimal(5822000000)
    assert value("operating_lease_current", "2026-04-30", quarter) == Decimal(1662000000)
    assert value("operating_lease_long_term", "2026-04-30", quarter) == Decimal(14388000000)
    assert value("redeemable_nci", "2026-04-30", quarter) == Decimal(293000000)
    assert value("nonredeemable_nci", "2026-04-30", quarter) == Decimal(6352000000)
    assert value("walmart_shareholders_equity", "2026-04-30", quarter) == Decimal(94330000000)
    assert not [row for row in rows if row["metric_id"] == "dividends_payable"
                and row["period_end"] == "2026-01-31" and row["version_id"] == quarter]
    opening = lambda metric: value(metric, "2026-04-30", quarter)
    assert sum((opening(metric) for metric in (
        "current_assets", "ppe_net", "operating_lease_rou_assets", "finance_lease_rou_assets",
        "goodwill", "other_long_term_assets",
    )), Decimal(0)) == opening("total_assets")
    assert sum((opening(metric) for metric in (
        "short_term_borrowings", "accounts_payable", "dividends_payable", "accrued_liabilities",
        "accrued_income_taxes", "current_debt", "operating_lease_current", "finance_lease_current",
    )), Decimal(0)) == opening("current_liabilities")
    assert sum((opening(metric) for metric in (
        "current_liabilities", "noncurrent_debt", "operating_lease_long_term",
        "finance_lease_long_term", "deferred_taxes_other_liabilities", "redeemable_nci",
        "total_equity",
    )), Decimal(0)) == opening("total_liabilities_equity")


def test_walmart_p1_q1_supplement_transport_and_dash_are_offline() -> None:
    module = runpy.run_path(str(SUPPLEMENT))
    original = runpy.run_path(str(SCRIPT))
    body = b"<title>Filing</title><body>content</body>"
    delivered = (
        b'<title>Filing</title><script >bazadebezolkohpepadr="12345"</script>'
        b'<script type="text/javascript"  src="/jGPwwufxbVNjftpB5QEsfCYc/'
        b'NODizkrbDhJ6LQYuEm/Bwg0WSMB/SGRsCE5/bOyE"></script>'
        b"<body>content</body>"
    )
    assert module["canonical_document_bytes"](delivered) == body
    labels = {"Cash and cash equivalents", "Total current assets", "Total assets"}
    make_row = lambda label, values: "<tr><td>" + escape(label) + "</td>" + "".join(
        "<td></td><td>" + value + "</td><td></td>" for value in values
    ) + "</tr>"
    table = "<table>" + "".join(make_row(label, ("1", "2", "3")) for label in labels)
    for label, (_, expected) in module["BALANCE_LINES"].items():
        table += make_row(label, tuple(value or "—" for value in expected))
    table += "</table>"
    extracted = module["parse_balance_lines"](table.encode())
    assert len(extracted) == 44
    assert not [item for item in extracted if item[1] == "dividends_payable"
                and item[2].isoformat() == "2026-01-31"]
    assert original["canonical_document_bytes"](delivered, "FY27Q1_HTML") != body


def test_walmart_p1_assumption_locators_keep_publication_and_rights_limits() -> None:
    rows = _load_rows(EVIDENCE / "assumption_evidence.csv")
    assert len(rows) == 20
    assert len({row["evidence_id"] for row in rows}) == len(rows)
    cutoff = datetime.fromisoformat("2026-05-21T23:59:59-04:00")
    for row in rows:
        assert row["source_id"] and row["url"] and row["locator"]
        assert row["period"] and row["unit"] and row["observed_value"]
        assert row["retrieved_at"] and len(row["observation_sha256"]) == 64
        selection = {key: row[key] for key in (
            "evidence_id", "url", "locator", "period", "unit", "observed_value"
        )}
        encoded = json.dumps(selection, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        assert hashlib.sha256(encoded.encode()).hexdigest() == row["observation_sha256"]
        if row["first_public_at"]:
            assert datetime.fromisoformat(row["first_public_at"]) <= cutoff
        else:
            assert row["temporal_state"] == "RETROSPECTIVE_OBSERVATION" or "UNVERIFIED" in row["temporal_state"]
    by_id = {row["evidence_id"]: row for row in rows}
    assert by_id["wmt_close_20260521"]["observed_value"] == "121.34"
    assert by_id["wmt_close_20260521"]["first_public_at"] == ""
    assert by_id["usd_ust10y_20260521"]["observed_value"] == "4.57"
    assert by_id["wmt_2036_bond_spread_20260427"]["observed_value"] == "43"
    assert by_id["us_implied_erp_20260501"]["observed_value"] == "4.24"
    assert by_id["us_retail_general_beta_202601"]["observed_value"] == "0.81"
    assert by_id["us_retail_grocery_beta_202601"]["observed_value"] == "1.12"
    assert by_id["wmt_fy27_sales_growth_guidance_cc_20260521"]["observed_value"] == "3.5-4.5"
    assert by_id["wmt_fy27_adj_oi_growth_guidance_cc_20260521"]["observed_value"] == "6.0-8.0"
    assert by_id["wmt_fy27_capex_sales_guidance_20260521"]["observed_value"] == "3.5"
    assert by_id["wmt_fy27_etr_guidance_20260521"]["observed_value"] == "23.5-24.5"
    assert all("LOCATOR_ONLY" in row["rights_state"] for row in rows)


def test_walmart_p1_q1_table_parser_and_unit_sign_transform_are_offline() -> None:
    module = runpy.run_path(str(SCRIPT))
    delivered = (
        b'<title>Document</title><script >bazadebezolkohpepadr="12345"</script>'
        b'<script type="text/javascript" src="https://www.sec.gov/akam/13/example"  defer></script>'
        b'<body>filing</body><noscript><img src="https://www.sec.gov/akam/13/pixel_example"'
        b' style="visibility: hidden;" /></noscript>'
    )
    assert module["canonical_document_bytes"](delivered, "FY27Q1_HTML") == b"<title>Document</title><body>filing</body>"
    make_table = lambda labels, count: "<table>" + "".join(
        "<tr><td>" + escape(label) + "</td>" + "".join(
            "<td>" + ("(6,684)" if label == "Payments for property and equipment" and n == 0
                       else "(4,986)" if label == "Payments for property and equipment"
                       else str(n + 1)) + "</td>" for n in range(count)
        ) + "</tr>" for label in labels
    ) + "</table>"
    payload = (
        make_table(module["QUARTER_INCOME"], 2)
        + make_table(module["QUARTER_BALANCE"], 3)
        + make_table(module["QUARTER_CASH"], 2)
    ).encode("utf-8")
    extracted = module["parse_quarter_html"](payload)
    capex = [item for item in extracted if item.metric_id == "capital_expenditure_payments_quarter"
             and item.period_end.isoformat() == "2026-04-30"]
    assert len(capex) == 1
    assert capex[0].value == "-6684" and capex[0].sign_multiplier == -1
    assert module["canonical_usd_value"](capex[0], "FY27Q1_HTML") == "-6684000000"
    mapped = _load_rows(EVIDENCE / "mappings.csv")
    rule = next(row for row in mapped if row["source_id"] == "wmt_fy27q1_8k_ex991_20260521"
                and row["raw_account_id"] == capex[0].account_id)
    assert rule["sign_multiplier"] == "-1"
    assert "x1000000" in rule["mapping_reason"]
