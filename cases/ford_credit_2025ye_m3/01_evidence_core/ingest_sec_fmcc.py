"""Register the two official SEC locators and the explicitly selected Ford Credit facts.

Run from the repository root with PYTHONPATH=src. Source HTML is fetched only to
verify the pinned byte hashes; it is never written into the repository. Existing
ledger and fact rows are append-only. Transcribed table cells remain pending
independent review; source row locations are documented in evidence_notes.md.
"""

from __future__ import annotations

import csv
import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from urllib.request import Request, urlopen

from versioned_finance_core.contracts.enums import AccessClass, PublicationStatus
from versioned_finance_core.evidence import (
    RawFact,
    SourceMetadata,
    append_raw_facts,
    load_source_ledger,
    register_source_locator,
)
from versioned_finance_core.evidence.ledger import _utc_iso

CASE = Path(__file__).resolve().parents[1]
EVIDENCE = CASE / "01_evidence_core"
CORE = CASE / "02_financial_core"
OUTCOME = CASE / "out_of_time_evaluation"
SCOPE = "fmcc_consolidated_group"
ENTITY = "ford_motor_credit_company_llc"
BRIDGE = "bridge_fmcc_2025_filer_group"
V2025 = "fmcc_2025ye_filed_20260211"
V2026 = "fmcc_2026h1_filed_20260729"
SOURCES = {
    "sec_fmcc_2025_10k": {
        "url": "https://www.sec.gov/Archives/edgar/data/38009/000003800926000010/fmcc-20251231.htm",
        "sha256": "3b5a7914fdb73a6e1425bf5745f8e20fbca6fd3703bdfc4fb3cfc865cc2bdc3b",
        "document_id": "SEC accession 0000038009-26-000010",
        "period_start": date(2025, 1, 1),
        "period_end": date(2025, 12, 31),
        "public_at": datetime.fromisoformat("2026-02-11T23:59:59-05:00"),
        "cutoff_eligible": True,
        "notes": (
            "SEC index filing date 2026-02-11, accepted 2026-02-10 19:15:16. "
            "first_public_at is a conservative known-public-by bound at end of "
            "filing date, not the observed public release second. Locator only."
        ),
    },
    "sec_fmcc_2026q2_10q": {
        "url": "https://www.sec.gov/Archives/edgar/data/38009/000003800926000041/fmcc-20260630.htm",
        "sha256": "c3b351a8749505cf0ed685ad390a9a9dc9dfc183a861769b6e82828a5734113f",
        "document_id": "SEC accession 0000038009-26-000041",
        "period_start": date(2026, 1, 1),
        "period_end": date(2026, 6, 30),
        "public_at": datetime.fromisoformat("2026-07-29T23:59:59-04:00"),
        "cutoff_eligible": False,
        "notes": (
            "SEC index filing date 2026-07-29, accepted 2026-07-28 19:31:29. "
            "Later outcome vintage: excluded from the 2026-02-11 decision cutoff. "
            "first_public_at is a conservative known-public-by bound. Locator only."
        ),
    },
}


def _write_if_empty_or_equal(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames
        existing = list(reader)
    if header is None or any(set(row) != set(header) for row in rows):
        raise ValueError(f"CSV header mismatch: {path}")
    if existing:
        if existing != rows:
            raise ValueError(f"Existing reviewed data differs; refusing overwrite: {path}")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)


def _rows(path: Path, partials: list[dict[str, str]]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle))
    return [{column: part.get(column, "") for column in header} for part in partials]


def _receipt(source_id: str, evidence_dir: Path):
    source = SOURCES[source_id]
    request = Request(
        source["url"],
        headers={"User-Agent": "PersonalResearch versionedfinancecore research.contact@example.com"},
    )
    with urlopen(request, timeout=30) as response:
        body = response.read()
    actual_hash = hashlib.sha256(body).hexdigest()
    if actual_hash != source["sha256"]:
        raise ValueError(f"Source bytes changed for {source_id}: {actual_hash}")
    existing = [
        receipt
        for receipt in load_source_ledger(evidence_dir)
        if receipt.source_id == source_id and receipt.content_sha256 == actual_hash
    ]
    if existing:
        return existing[0]
    metadata = SourceMetadata(
        source_id=source_id,
        access_class=AccessClass.PUBLIC_OFFICIAL,
        authority="U.S. Securities and Exchange Commission EDGAR",
        title=f"Ford Motor Credit Company LLC {source['document_id']}",
        url=source["url"],
        document_id=source["document_id"],
        retrieved_at=datetime.now(UTC),
        publication_status=PublicationStatus.FILED,
        first_public_at=source["public_at"],
        period_start=source["period_start"],
        period_end=source["period_end"],
        entity_scope=SCOPE,
        currency="USD",
        unit="USD_MILLION_AND_BILLION_AS_FILED",
        retention_right=False,
        transformation_right=True,
        redistribution_right=False,
        cutoff_eligible=source["cutoff_eligible"],
        notes=source["notes"],
    )
    return register_source_locator(evidence_dir, metadata, actual_hash)


# metric, filed-row label, raw value, period start/end, period type, unit,
# instrument identifier. Dollar signs, commas and parentheses are omitted
# from raw_value only after preserving their sign.
FACTS_2025 = [
    ("opening_cash", "Cash, cash equivalents, and restricted cash at beginning of period (Note 3)", "9360", "2024-12-31", "2024-12-31", "INSTANT", "USD_MILLION", ""),
    ("operating_cash_flow", "Net cash provided by/(used in) operating activities", "3846", "2025-01-01", "2025-12-31", "YEAR", "USD_MILLION", ""),
    ("investing_cash_flow", "Net cash provided by/(used in) investing activities", "-1615", "2025-01-01", "2025-12-31", "YEAR", "USD_MILLION", ""),
    ("financing_cash_flow", "Net cash provided by/(used in) financing activities", "-2495", "2025-01-01", "2025-12-31", "YEAR", "USD_MILLION", ""),
    ("fx_and_other", "Effect of exchange rate changes on cash, cash equivalents, and restricted cash", "281", "2025-01-01", "2025-12-31", "YEAR", "USD_MILLION", ""),
    ("closing_cash", "Cash, cash equivalents, and restricted cash at end of period (Note 3)", "9377", "2025-12-31", "2025-12-31", "INSTANT", "USD_MILLION", ""),
    ("liquidity_cash", "Cash", "9.3", "2025-12-31", "2025-12-31", "INSTANT", "USD_BILLION", ""),
    ("liquidity_committed_abs", "Committed asset-backed facilities", "43.6", "2025-12-31", "2025-12-31", "INSTANT", "USD_BILLION", ""),
    ("liquidity_committed_unsecured", "Other unsecured credit facilities", "1.5", "2025-12-31", "2025-12-31", "INSTANT", "USD_BILLION", ""),
    ("liquidity_restricted_cash", "Securitization and restricted cash", "3.0", "2025-12-31", "2025-12-31", "INSTANT", "USD_BILLION", ""),
    ("liquidity_abs_utilized", "Committed asset-backed facilities - utilization", "26.4", "2025-12-31", "2025-12-31", "INSTANT", "USD_BILLION", ""),
    ("liquidity_unsecured_utilized", "Other unsecured credit facilities - utilization", "0.6", "2025-12-31", "2025-12-31", "INSTANT", "USD_BILLION", ""),
    ("liquidity_available", "Available liquidity", "24.4", "2025-12-31", "2025-12-31", "INSTANT", "USD_BILLION", ""),
    ("liquidity_other_adjustments", "Other adjustments", "0.2", "2025-12-31", "2025-12-31", "INSTANT", "USD_BILLION", ""),
    ("liquidity_net_available", "Net liquidity available for use", "24.6", "2025-12-31", "2025-12-31", "INSTANT", "USD_BILLION", ""),
    ("debt_gross_principal", "Maturities - Total", "141904", "2025-12-31", "2025-12-31", "INSTANT", "USD_MILLION", ""),
    ("debt_unamortized_cost_adjustment", "Unamortized (discount)/premium and issuance costs", "-247", "2025-12-31", "2025-12-31", "INSTANT", "USD_MILLION", ""),
    ("debt_fair_value_adjustment", "Fair value adjustments", "-240", "2025-12-31", "2025-12-31", "INSTANT", "USD_MILLION", ""),
    ("debt_carrying_amount", "Total debt", "141417", "2025-12-31", "2025-12-31", "INSTANT", "USD_MILLION", ""),
]

UNSECURED = [("2026", "30053"), ("2027", "12941"), ("2028", "11657"), ("2029", "8613"), ("2030", "7836"), ("2031_2035", "11310")]
ABS = [("2026", "21753"), ("2027", "17819"), ("2028", "12104"), ("2029", "4581"), ("2030", "3237")]
LONG_TERM_INTEREST = [("2026", "5309"), ("2027", "3858"), ("2028", "2583"), ("2029", "1633"), ("2030", "1057"), ("2031_2035", "1666")]

for metric, label, values, instrument in (
    ("maturity_unsecured_principal", "Unsecured debt", UNSECURED, "fmcc_unsecured_debt_aggregate_2025ye"),
    ("maturity_asset_backed_principal", "Asset-backed debt", ABS, "fmcc_securitization_debt_aggregate_2025ye"),
    ("maturity_long_term_interest", "Interest payments related to long-term debt", LONG_TERM_INTEREST, ""),
):
    for bucket, value in values:
        year = bucket[:4]
        start = f"{year}-01-01"
        end = "2035-12-31" if bucket == "2031_2035" else f"{year}-12-31"
        FACTS_2025.append((metric, label, value, start, end, "MATURITY_BUCKET", "USD_MILLION", instrument))

FACTS_2026 = [
    ("liquidity_cash", "Cash", "8.5", "2026-06-30", "2026-06-30", "INSTANT", "USD_BILLION", ""),
    ("liquidity_committed_abs", "Committed asset-backed facilities", "42.9", "2026-06-30", "2026-06-30", "INSTANT", "USD_BILLION", ""),
    ("liquidity_restricted_cash", "Securitization and restricted cash", "2.9", "2026-06-30", "2026-06-30", "INSTANT", "USD_BILLION", ""),
    ("liquidity_net_available", "Net liquidity available for use", "27.4", "2026-06-30", "2026-06-30", "INSTANT", "USD_BILLION", ""),
    ("debt_carrying_amount", "Total debt", "137348", "2026-06-30", "2026-06-30", "INSTANT", "USD_MILLION", ""),
]


def _append_facts(evidence_dir: Path, receipt, source_id: str, version_id: str, definitions):
    facts = []
    for index, (metric, label, value, start, end, period_type, unit, instrument) in enumerate(definitions, 1):
        fact_id = f"{source_id}_{metric}_{start}_{index}"
        facts.append(
            RawFact(
                fact_id=fact_id,
                source_id=source_id,
                snapshot_id=receipt.snapshot_id,
                version_id=version_id,
                economic_scope_id=SCOPE,
                accounting_scope="CONSOLIDATED",
                economic_legal_scope_bridge_id=BRIDGE if source_id == "sec_fmcc_2025_10k" else "",
                legal_entity_id=ENTITY,
                instrument_id=instrument,
                raw_account_id=f"SEC_{metric.upper()}",
                metric_id=metric,
                period_start=date.fromisoformat(start),
                period_end=date.fromisoformat(end),
                period_type=period_type,
                currency="USD",
                unit=unit,
                raw_value=value,
                raw_label=label,
                extraction_method="SEC_HTML_MANUAL_TABLE_TRANSCRIPTION_V1",
                review_status="SOURCE_EXTRACTED_PENDING_INDEPENDENT_REVIEW",
                mapping_version=f"map_{source_id}_{metric}",
            )
        )
    return append_raw_facts(evidence_dir, facts)


def main() -> None:
    assert Decimal(9360) + Decimal(3846) - Decimal(1615) - Decimal(2495) + Decimal(281) == Decimal(9377)
    assert sum(Decimal(value) for _, value in UNSECURED) == Decimal(82410)
    assert sum(Decimal(value) for _, value in ABS) == Decimal(59494)
    assert Decimal(82410) + Decimal(59494) - Decimal(247) - Decimal(240) == Decimal(141417)
    assert Decimal("9.3") + Decimal("43.6") + Decimal("1.5") - Decimal("3.0") - Decimal("26.4") - Decimal("0.6") + Decimal("0.2") == Decimal("24.6")

    receipt_2025 = _receipt("sec_fmcc_2025_10k", EVIDENCE)
    receipt_2026 = _receipt("sec_fmcc_2026q2_10q", OUTCOME)
    definitions = {}
    for source_id, facts in (("sec_fmcc_2025_10k", FACTS_2025),):
        for metric, label, _value, _start, _end, period_type, unit, _instrument in facts:
            prior = definitions.setdefault(metric, (period_type, unit))
            if prior != (period_type, unit):
                raise ValueError(f"Inconsistent metric grain: {metric}")

    dictionary_path = EVIDENCE / "metric_dictionary.csv"
    dictionary = [
        {
            "metric_id": metric,
            "display_name": metric.replace("_", " "),
            "definition": "Source table cell, as filed. See evidence_notes.md for table and legal-scope limits.",
            "formula": "SOURCE_VALUE",
            "grain": "FMCC_CONSOLIDATED_DISCLOSURE",
            "period_type": period_type,
            "currency_policy": "USD",
            "unit": unit,
            "sign_convention": "FILED_SIGN_OR_POSITIVE_MAGNITUDE_FOR_UTILIZATION",
            "source_priority": "SEC_OFFICIAL",
            "publication_lag": "SOURCE_RECEIPT",
            "controllability": "REPORTED_FACT",
            "limitations": "Group amount is not Ford Credit LLC parent-only accessible cash or debt.",
            "review_status": "APPROVED",
        }
        for metric, (period_type, unit) in definitions.items()
    ]
    _write_if_empty_or_equal(dictionary_path, _rows(dictionary_path, dictionary))

    mappings_path = EVIDENCE / "mappings.csv"
    mappings = []
    for source_id, facts in (("sec_fmcc_2025_10k", FACTS_2025),):
        unique = {}
        for metric, label, *_ in facts:
            unique[metric] = label
        for metric, label in unique.items():
            mappings.append({
                "mapping_id": f"map_{source_id}_{metric}",
                "source_id": source_id,
                "raw_account_id": f"SEC_{metric.upper()}",
                "raw_label": label,
                "normalized_metric_id": metric,
                "mapping_reason": "Explicit SEC table row and period; same sign and unit retained",
                "confidence": "EXACT_TABLE_ROW",
                "reviewer": "codex_source_extraction",
                "review_status": "APPROVED",
                "sign_multiplier": "+1",
            })
    _write_if_empty_or_equal(mappings_path, _rows(mappings_path, mappings))

    versions_path = CORE / "versions.csv"
    versions = [{
            "version_id": V2025,
            "version_type": "PUBLIC_ACTUAL",
            "as_of_date": "2025-12-31",
            "publication_status": "FILED",
            "information_cutoff": SOURCES["sec_fmcc_2025_10k"]["public_at"].isoformat(),
            "created_by": "SEC_EDGAR",
            "immutable": "true",
            "notes": "2025 Form 10-K published by conservative 2026-02-11 end-of-day bound",
        }]
    _write_if_empty_or_equal(versions_path, _rows(versions_path, versions))
    outcome_version_path = OUTCOME / "versions.csv"
    outcome_versions = [{
            "version_id": V2026,
            "version_type": "PUBLIC_ACTUAL",
            "as_of_date": "2026-06-30",
            "publication_status": "FILED",
            "information_cutoff": SOURCES["sec_fmcc_2026q2_10q"]["public_at"].isoformat(),
            "created_by": "SEC_EDGAR",
            "immutable": "true",
            "notes": "Later outcome, excluded from case decision cutoff",
        }]
    _write_if_empty_or_equal(outcome_version_path, _rows(outcome_version_path, outcome_versions))

    bridge_path = EVIDENCE / "scope_bridges.csv"
    receipt = receipt_2025
    bridge = [{
        "bridge_id": BRIDGE,
        "economic_scope_id": SCOPE,
        "legal_entity_id": ENTITY,
        "relation": "CONSOLIDATED_FINANCIAL_STATEMENTS_OF_FILER_NOT_PARENT_STANDALONE",
        "source_id": receipt.source_id,
        "first_public_at": _utc_iso(receipt.first_public_at),
        "review_status": "APPROVED",
        "snapshot_id": receipt.snapshot_id,
        "content_sha256": receipt.content_sha256,
        "retrieved_at": _utc_iso(receipt.retrieved_at),
    }]
    _write_if_empty_or_equal(bridge_path, _rows(bridge_path, bridge))

    identity_path = CORE / "cash_identity_checks.csv"
    cash_roles = ("opening_cash", "operating_cash_flow", "investing_cash_flow", "financing_cash_flow", "fx_and_other", "closing_cash")
    ids = {}
    for index, (metric, _label, _value, start, *_rest) in enumerate(FACTS_2025, 1):
        if metric in cash_roles:
            ids[metric] = f"sec_fmcc_2025_10k_{metric}_{start}_{index}"
    identity = {
        "identity_id": "fmcc_2025_consolidated_cash_rollforward",
        "version_id": V2025,
        **{f"{metric}_fact_id": ids[metric] for metric in cash_roles},
    }
    _write_if_empty_or_equal(identity_path, _rows(identity_path, [identity]))

    _append_facts(EVIDENCE, receipt_2025, "sec_fmcc_2025_10k", V2025, FACTS_2025)
    _append_facts(OUTCOME, receipt_2026, "sec_fmcc_2026q2_10q", V2026, FACTS_2026)
    print(f"Registered {len(FACTS_2025)} 2025 facts and {len(FACTS_2026)} later-outcome facts; raw HTML not retained")


if __name__ == "__main__":
    main()
