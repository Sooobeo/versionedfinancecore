"""Append independently checked Q1 balance-sheet lines from a new SEC delivery.

The original Q1 receipt and its 78 facts remain immutable. SEC currently serves
the same exhibit through an additional Akamai script, and its canonical body hash
differs from the original pinned retrieval. This script therefore records a new
locator receipt and adds only previously uncollected statement lines. It does not
retain or redistribute the filing body.
"""

from __future__ import annotations

import csv
import hashlib
import re
import runpy
import sys
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from versioned_finance_core.contracts.enums import AccessClass, PublicationStatus
from versioned_finance_core.evidence.facts import RawFact, append_raw_facts
from versioned_finance_core.evidence.ledger import (
    SourceMetadata,
    _utc_iso,
    load_source_ledger,
    register_source_locator,
)

EVIDENCE = Path(__file__).resolve().parent
ORIGINAL = runpy.run_path(str(EVIDENCE / "ingest_sec_financials.py"))
FILING = ORIGINAL["FILINGS"][2]
CANONICAL_SHA256 = "1da651ebab33b75f8057857ddc7c75d01ef3bf20642d169ac94321a311e49a1a"
BRIDGE_ID = "wmt_fy27q1_8k_ex991_20260521_supplement_consolidated_bridge"

# April 2026, January 2026, April 2025, respectively; all in USD millions.
# The source marks January dividends payable with an em dash. Preserve that
# missing/nil presentation as no fact rather than silently coercing it to zero.
BALANCE_LINES = {
    "Prepaid expenses and other": ("prepaid_other_current_assets", ("4433", "4124", "3789")),
    "Operating lease right-of-use assets": ("operating_lease_rou_assets", ("15220", "14750", "13567")),
    "Finance lease right-of-use assets, net": ("finance_lease_rou_assets", ("6033", "6123", "6056")),
    "Goodwill": ("goodwill", ("28152", "28735", "28866")),
    "Other long-term assets": ("other_long_term_assets", ("14019", "14103", "12369")),
    "Dividends payable": ("dividends_payable", ("5921", None, "5660")),
    "Accrued income taxes": ("accrued_income_taxes", ("1174", "596", "1465")),
    "Operating lease obligations due within one year": ("operating_lease_current", ("1662", "1631", "1539")),
    "Finance lease obligations due within one year": ("finance_lease_current", ("851", "856", "791")),
    "Long-term operating lease obligations": ("operating_lease_long_term", ("14388", "13941", "12797")),
    "Long-term finance lease obligations": ("finance_lease_long_term", ("5822", "5905", "5878")),
    "Deferred income taxes and other": ("deferred_taxes_other_liabilities", ("16952", "16549", "13609")),
    "Redeemable noncontrolling interest": ("redeemable_nci", ("293", "293", "307")),
    "Total Walmart shareholders’ equity": ("walmart_shareholders_equity", ("94330", "99617", "83793")),
    "Nonredeemable noncontrolling interest": ("nonredeemable_nci", ("6352", "6270", "6548")),
}
PERIODS = (date(2026, 4, 30), date(2026, 1, 31), date(2025, 4, 30))

# A second request-dependent transport script now precedes the original Akamai
# pixel. This narrowly matches its observed generated-path shape. A canonical
# digest check below still fails closed on any unreviewed filing-content change.
NEW_TRANSPORT_SCRIPT = re.compile(
    rb'<script type="text/javascript"  src="/[A-Za-z0-9]{20,}/[A-Za-z0-9]{15,}/'
    rb'[A-Za-z0-9]{5,}/[A-Za-z0-9]{5,}/[A-Za-z0-9]{4,}"></script>'
)


def canonical_document_bytes(raw: bytes) -> bytes:
    prior_canonical = ORIGINAL["canonical_document_bytes"](raw, "FY27Q1_HTML")
    return NEW_TRANSPORT_SCRIPT.sub(b"", prior_canonical)


def parse_balance_lines(payload: bytes) -> list[tuple[str, str, date, str]]:
    parser = ORIGINAL["_Tables"]()
    parser.feed(payload.decode("utf-8"))
    matches = [table for table in parser.tables if {
        "Cash and cash equivalents", "Total current assets", "Total assets"
    } <= {row[0] for row in table if row}]
    if len(matches) != 1:
        raise ValueError(f"expected one condensed consolidated balance sheet, found {len(matches)}")
    labels = {row[0]: row for row in matches[0] if row and row[0] in BALANCE_LINES}
    if labels.keys() != BALANCE_LINES.keys():
        raise ValueError(f"missing balance lines: {BALANCE_LINES.keys() - labels.keys()}")
    extracted: list[tuple[str, str, date, str]] = []
    for label, (metric_id, expected) in BALANCE_LINES.items():
        cells = [cell.strip().replace(",", "") for cell in labels[label][1:]
                 if cell.strip() not in {"", "$"}]
        if len(cells) != 3:
            raise ValueError(f"expected three comparative columns for {label}: {cells}")
        for period, actual, pinned in zip(PERIODS, cells, expected, strict=True):
            if pinned is None:
                if actual != "—":
                    raise ValueError(f"expected reported dash for {label} at {period}: {actual}")
                continue
            if actual != pinned:
                raise ValueError(f"changed SEC balance line {label} at {period}: {actual}")
            extracted.append((label, metric_id, period, pinned))
    return extracted


def check_original_q1_facts(payload: bytes) -> None:
    """Check all previously captured Q1 values before appending a new vintage."""
    old = {}
    with (EVIDENCE / "raw_facts.csv").open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["source_id"] == FILING.source_id and row["extraction_method"].endswith("_V1"):
                old[(row["metric_id"], row["period_start"], row["period_end"])] = row["raw_value"]
    if len(old) != 78:
        raise ValueError(f"expected 78 original Q1 facts, found {len(old)}")
    current = {}
    for item in ORIGINAL["parse_quarter_html"](payload):
        current[(item.metric_id, item.period_start.isoformat(), item.period_end.isoformat())] = (
            ORIGINAL["canonical_usd_value"](item, "FY27Q1_HTML")
        )
    if current != old:
        raise ValueError("new SEC delivery differs from original 78 Q1 statement facts")


def ingest() -> int:
    request = urllib.request.Request(FILING.url, headers={
        "User-Agent": "VersionedFinanceCore/0.1 personal-public-data-research",
        "Accept-Encoding": "identity",
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
    raw_sha256 = hashlib.sha256(raw).hexdigest()
    payload = canonical_document_bytes(raw)
    digest = hashlib.sha256(payload).hexdigest()
    if digest != CANONICAL_SHA256:
        raise ValueError(f"unreviewed SEC exhibit delivery/content digest: {digest}")
    extracted = parse_balance_lines(payload)
    check_original_q1_facts(payload)

    prior = [receipt for receipt in load_source_ledger(EVIDENCE)
             if receipt.source_id == FILING.source_id and receipt.content_sha256 == digest]
    if len(prior) > 1:
        raise ValueError("multiple matching Q1 supplement receipts")
    receipt = prior[0] if prior else register_source_locator(EVIDENCE, SourceMetadata(
        source_id=FILING.source_id,
        access_class=AccessClass.PUBLIC_REGULATORY,
        authority="Walmart Inc.; U.S. SEC EDGAR",
        title="FY27 Q1 Form 8-K Exhibit 99.1 earnings release; balance sheet supplement",
        url=FILING.url,
        document_id=FILING.document_id,
        first_public_at=datetime.fromisoformat(FILING.public_at),
        retrieved_at=datetime.now(UTC),
        publication_status=PublicationStatus.FILED,
        period_start=min(PERIODS),
        period_end=max(PERIODS),
        entity_scope="walmart_consolidated_group",
        currency="USD",
        unit="USD_MILLION",
        retention_right=False,
        transformation_right=True,
        redistribution_right=False,
        cutoff_eligible=True,
        notes=(
            "New append-only SEC delivery vintage. Canonical body removes the original and "
            "one newly observed Akamai transport script/pixel; raw_response_sha256="
            + raw_sha256 + ". New body digest differs from original pinned receipt; all "
            "78 previously extracted Q1 statement facts were independently equal. "
            "Only additional balance-sheet lines are recorded here. Comparative Jan 2026 "
            "and Apr 2025 lines were disclosed with the May 21 exhibit and inherit that "
            "first_public_at, not their period end. Original bytes are not retained."
        ),
    ), digest)

    ORIGINAL["_append_unique"](EVIDENCE / "scope_bridges.csv", [{
        "bridge_id": BRIDGE_ID,
        "economic_scope_id": "walmart_consolidated_group",
        "legal_entity_id": "walmart_inc_us_de",
        "relation": "CONSOLIDATED_GROUP_REPORTED_BY_WALMART_INC_NOT_PARENT_ONLY_CASH",
        "source_id": receipt.source_id,
        "first_public_at": _utc_iso(receipt.first_public_at),
        "review_status": "APPROVED",
        "snapshot_id": receipt.snapshot_id,
        "content_sha256": receipt.content_sha256,
        "retrieved_at": _utc_iso(receipt.retrieved_at),
    }], "bridge_id")

    mappings = []
    metrics = []
    facts = []
    for label, metric_id, period, value_millions in extracted:
        account_id = f"html:balance:{label}"
        mapping_id = f"map_{FILING.source_id}_supp_{hashlib.sha256(account_id.encode()).hexdigest()[:12]}"
        facts.append(RawFact(
            fact_id=f"raw_{FILING.source_id}_supp_{hashlib.sha256((account_id + period.isoformat()).encode()).hexdigest()[:16]}",
            source_id=FILING.source_id,
            snapshot_id=receipt.snapshot_id,
            version_id=FILING.version_id,
            economic_scope_id="walmart_consolidated_group",
            accounting_scope="CONSOLIDATED",
            economic_legal_scope_bridge_id=BRIDGE_ID,
            legal_entity_id="walmart_inc_us_de",
            raw_account_id=account_id,
            metric_id=metric_id,
            period_start=period,
            period_end=period,
            period_type="INSTANT",
            currency="USD",
            unit="USD",
            raw_value=str(int(value_millions) * 1_000_000),
            raw_label=label,
            extraction_method="SEC_8K_HTML_EX991_BALANCE_USDM_TO_USD_X1000000_V2",
            mapping_version=mapping_id,
            review_status="SOURCE_EXTRACTED",
        ))
        mappings.append({
            "mapping_id": mapping_id,
            "source_id": FILING.source_id,
            "raw_account_id": account_id,
            "raw_label": label,
            "normalized_metric_id": metric_id,
            "effective_from": min(PERIODS).isoformat(),
            "effective_to": max(PERIODS).isoformat(),
            "mapping_reason": "8-K balance-sheet line in USD millions; exact transform x1000000 to USD; published sign preserved; no Jan-2026 dividend fact for em dash",
            "confidence": "HIGH",
            "review_status": "APPROVED",
            "sign_multiplier": "+1",
        })
        metrics.append({
            "metric_id": metric_id,
            "display_name": metric_id.replace("_", " ").title(),
            "definition": f"Walmart consolidated {metric_id.replace('_', ' ')}; signed SEC statement line in USD.",
            "formula": "SOURCE_VALUE",
            "grain": "WALMART_CONSOLIDATED_GROUP",
            "period_type": "INSTANT",
            "currency_policy": "USD",
            "unit": "USD",
            "sign_convention": "PUBLISHED_SIGN",
            "source_priority": "SEC_FILING",
            "publication_lag": "SOURCE_RECEIPT",
            "controllability": "PUBLIC_ACTUAL",
            "limitations": "Consolidated public statement line; April 2025 and January 2026 comparative values first disclosed in the May 2026 exhibit vintage.",
            "review_status": "APPROVED",
        })
    ORIGINAL["_append_unique"](EVIDENCE / "mappings.csv", list({r["mapping_id"]: r for r in mappings}.values()), "mapping_id")
    ORIGINAL["_append_unique"](EVIDENCE / "metric_dictionary.csv", list({r["metric_id"]: r for r in metrics}.values()), "metric_id")
    return append_raw_facts(EVIDENCE, facts)


if __name__ == "__main__":
    print("new Q1 balance facts", ingest(), "canonical_sha256", CANONICAL_SHA256)
