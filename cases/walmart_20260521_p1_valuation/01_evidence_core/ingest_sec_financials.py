"""Pin minimal Walmart statement facts from three official SEC filing exhibits.

Run from the repository root with ``python -m`` unavailable for this case script::

    python cases/walmart_20260521_p1_valuation/01_evidence_core/ingest_sec_financials.py

SEC document bytes are read in memory and SHA-256 checked, then discarded. Only
minimal numeric facts and locator receipts are retained. Existing fact IDs are
immutable; reruns with the pinned documents are idempotent.
"""

from __future__ import annotations

import csv
import hashlib
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, date, datetime
from html.parser import HTMLParser
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

CASE = Path(__file__).resolve().parents[1]
EVIDENCE = CASE / "01_evidence_core"
CORE = CASE / "02_financial_core"
CUTOFF = "2026-05-21T23:59:59-04:00"


@dataclass(frozen=True)
class Filing:
    source_id: str
    version_id: str
    title: str
    url: str
    document_id: str
    public_at: str
    expected_sha256: str
    kind: str


FILINGS = (
    Filing(
        "wmt_fy25_10k_xbrl_20250314",
        "wmt_actual_fy25_10k_20250314",
        "FY25 Form 10-K extracted XBRL instance",
        "https://www.sec.gov/Archives/edgar/data/104169/000010416925000021/wmt-20250131_htm.xml",
        "0000104169-25-000021;EXTRACTED_XBRL_INSTANCE",
        "2025-03-14T16:40:52-04:00",
        "5fcf3e216138d1e38cd8365f789f7f76a083295f5424fa0b4e1794c43f2a40ff",
        "FY25_XBRL",
    ),
    Filing(
        "wmt_fy26_10k_xbrl_20260313",
        "wmt_actual_fy26_10k_20260313",
        "FY26 Form 10-K extracted XBRL instance",
        "https://www.sec.gov/Archives/edgar/data/104169/000010416926000055/wmt-20260131_htm.xml",
        "0000104169-26-000055;EXTRACTED_XBRL_INSTANCE",
        "2026-03-13T16:06:24-04:00",
        "07c72faa90cf8515eb1ff1ca264361ca8741c2663202d2f5a25ff9c694f4ef67",
        "FY26_XBRL",
    ),
    Filing(
        "wmt_fy27q1_8k_ex991_20260521",
        "wmt_actual_fy27q1_8k_20260521",
        "FY27 Q1 Form 8-K Exhibit 99.1 earnings release",
        "https://www.sec.gov/Archives/edgar/data/104169/000010416926000095/earningsreleasefy27q1.htm",
        "0000104169-26-000095;EX-99.1",
        "2026-05-21T07:00:00-04:00",
        "0107dd5fe2d6677d96f95b409c9a59d420da337eba515e4204fc34ea0e66b93d",
        "FY27Q1_HTML",
    ),
)

# Raw XBRL USD dollars, not the rendered 10-K's USD millions. All selected
# contexts must be consolidated, non-dimensional and have decimals="-6".
ANNUAL_FLOW = {
    "RevenueFromContractWithCustomerExcludingAssessedTax": "net_sales",
    "Revenues": "total_revenue",
    "CostOfRevenue": "cost_of_sales",
    "SellingGeneralAndAdministrativeExpense": "operating_sga",
    "OperatingIncomeLoss": "operating_income",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": "income_before_tax",
    "IncomeTaxExpenseBenefit": "income_tax_expense",
    "NetIncomeLoss": "consolidated_net_income",
    "DepreciationAmortizationAndAccretionNet": "depreciation_amortization",
    "NetCashProvidedByUsedInOperatingActivities": "operating_cash_flow",
    "PaymentsToAcquirePropertyPlantAndEquipment": "capital_expenditure_payments",
    "NetCashProvidedByUsedInInvestingActivities": "investing_cash_flow",
    "NetCashProvidedByUsedInFinancingActivities": "financing_cash_flow",
    "EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": "fx_effect_on_cash",
}
BALANCE = {
    "CashAndCashEquivalentsAtCarryingValue": "cash_and_equivalents",
    "ReceivablesNetCurrent": "receivables",
    "InventoryNet": "inventory",
    "AssetsCurrent": "current_assets",
    "PropertyPlantAndEquipmentNet": "ppe_net",
    "Assets": "total_assets",
    "AccountsPayableCurrent": "accounts_payable",
    "AccruedLiabilitiesCurrent": "accrued_liabilities",
    "LongTermDebtCurrent": "current_debt",
    "LiabilitiesCurrent": "current_liabilities",
    "LongTermDebtNoncurrent": "noncurrent_debt",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": "total_equity",
    "LiabilitiesAndStockholdersEquity": "total_liabilities_equity",
}
CASH_BALANCE_CONCEPT = "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"

QUARTER_INCOME = {
    "Net sales": "net_sales",
    "Membership and other income": "membership_and_other_income",
    "Total revenues": "total_revenue",
    "Cost of sales": "cost_of_sales",
    "Operating, selling, general and administrative expenses": "operating_sga",
    "Operating income": "operating_income",
    "Income before income taxes": "income_before_tax",
    "Provision for income taxes": "income_tax_expense",
    "Consolidated net income": "consolidated_net_income",
    "Consolidated net income attributable to Walmart": "parent_net_income",
}
QUARTER_BALANCE = {
    "Cash and cash equivalents": "cash_and_equivalents",
    "Receivables, net": "receivables",
    "Inventories": "inventory",
    "Total current assets": "current_assets",
    "Property and equipment, net": "ppe_net",
    "Total assets": "total_assets",
    "Short-term borrowings": "short_term_borrowings",
    "Accounts payable": "accounts_payable",
    "Accrued liabilities": "accrued_liabilities",
    "Long-term debt due within one year": "current_debt",
    "Total current liabilities": "current_liabilities",
    "Long-term debt": "noncurrent_debt",
    "Total shareholders’ equity": "total_equity",
    "Total liabilities, redeemable noncontrolling interest, and shareholders’ equity": "total_liabilities_equity",
}
QUARTER_CASH = {
    "Depreciation and amortization": "depreciation_amortization",
    "Net cash provided by operating activities": "operating_cash_flow",
    "Payments for property and equipment": "capital_expenditure_payments",
    "Net cash used in investing activities": "investing_cash_flow",
    "Net cash provided by financing activities": "financing_cash_flow",
    "Effect of exchange rates on cash, cash equivalents and restricted cash": "fx_effect_on_cash",
    "Cash, cash equivalents and restricted cash at beginning of year": "cash_restricted_begin",
    "Cash, cash equivalents and restricted cash at end of period": "cash_restricted_end",
}


@dataclass(frozen=True)
class Extracted:
    account_id: str
    label: str
    metric_id: str
    period_start: date
    period_end: date
    period_type: str
    value: str
    sign_multiplier: int = 1


def canonical_document_bytes(payload: bytes, filing_kind: str) -> bytes:
    if filing_kind == "FY27Q1_HTML":
        # SEC's delivery layer can insert request-dependent Akamai JavaScript
        # and a tracking pixel into this HTML. Strip only these exact patterns
        # so the digest addresses the unchanged filing exhibit content.
        for pattern in (
            rb'<script >bazadebezolkohpepadr="[0-9]+"</script>',
            rb'<script type="text/javascript" src="https://www\.sec\.gov/akam/[^\"]+"  defer></script>',
            rb'<noscript><img src="https://www\.sec\.gov/akam/13/pixel_[^\"]+"[^>]+/></noscript>',
        ):
            payload = re.sub(pattern, b"", payload)
    return payload


def _fetch(filing: Filing) -> tuple[bytes, str]:
    request = urllib.request.Request(
        filing.url,
        headers={
            "User-Agent": "VersionedFinanceCore/0.1 personal-public-data-research",
            "Accept-Encoding": "identity",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        raw_response = response.read()
    raw_response_sha256 = hashlib.sha256(raw_response).hexdigest()
    payload = canonical_document_bytes(raw_response, filing.kind)
    digest = hashlib.sha256(payload).hexdigest()
    if digest != filing.expected_sha256:
        raise ValueError(f"source bytes changed for {filing.source_id}: {digest}")
    return payload, raw_response_sha256


def parse_xbrl(payload: bytes, filing_kind: str) -> list[Extracted]:
    """Select exact consolidated statement contexts; fail on ambiguity/missing."""

    root = ET.fromstring(payload)
    namespace = {"i": "http://www.xbrl.org/2003/instance"}
    contexts = {item.attrib["id"]: item for item in root.findall("i:context", namespace)}
    if filing_kind == "FY25_XBRL":
        periods = {(date(2024, 1, 31), date(2024, 1, 31)): "INSTANT"}
        specs = BALANCE
    elif filing_kind == "FY26_XBRL":
        periods = {
            (date(2023, 2, 1), date(2024, 1, 31)): "YEAR",
            (date(2024, 2, 1), date(2025, 1, 31)): "YEAR",
            (date(2025, 2, 1), date(2026, 1, 31)): "YEAR",
            (date(2025, 1, 31), date(2025, 1, 31)): "INSTANT",
            (date(2026, 1, 31), date(2026, 1, 31)): "INSTANT",
        }
        specs = {**ANNUAL_FLOW, **BALANCE, CASH_BALANCE_CONCEPT: "cash_restricted_end"}
    else:
        raise ValueError(f"unsupported XBRL filing kind: {filing_kind}")

    selected: dict[tuple[str, date, date], Extracted] = {}
    for element in root:
        if not element.tag.startswith("{http://fasb.org/us-gaap/"):
            continue
        concept = element.tag.split("}", 1)[1]
        metric = specs.get(concept)
        if metric is None or element.attrib.get("decimals") != "-6":
            continue
        context = contexts.get(element.attrib.get("contextRef", ""))
        if context is None or context.find("i:entity/i:segment", namespace) is not None:
            continue
        if context.find("i:scenario", namespace) is not None:
            continue
        period = context.find("i:period", namespace)
        if period is None:
            continue
        instant = period.find("i:instant", namespace)
        if instant is not None:
            start = end = date.fromisoformat(instant.text or "")
        else:
            start_element, end_element = period.find("i:startDate", namespace), period.find("i:endDate", namespace)
            if start_element is None or end_element is None:
                continue
            start, end = date.fromisoformat(start_element.text or ""), date.fromisoformat(end_element.text or "")
        period_type = periods.get((start, end))
        if period_type is None or (period_type == "YEAR") != (concept in ANNUAL_FLOW):
            continue
        if element.attrib.get("unitRef") != "usd" or element.text is None:
            raise ValueError(f"unexpected XBRL unit or missing value: {concept}")
        value = str(int(element.text))
        metric_id = f"{metric}_year" if period_type == "YEAR" else metric
        extracted = Extracted(f"us-gaap:{concept}", concept, metric_id, start, end, period_type, value)
        key = (concept, start, end)
        previous = selected.get(key)
        if previous is not None and previous != extracted:
            raise ValueError(f"conflicting XBRL fact: {key}")
        selected[key] = extracted

    expected = {(concept, start, end) for (start, end), kind in periods.items()
                for concept in (ANNUAL_FLOW if kind == "YEAR" else
                                ({**BALANCE, CASH_BALANCE_CONCEPT: "cash_restricted_end"}
                                 if filing_kind == "FY26_XBRL" else BALANCE))}
    missing = expected - selected.keys()
    if missing:
        raise ValueError(f"missing consolidated XBRL facts: {sorted(missing)}")
    return sorted(selected.values(), key=lambda row: (row.period_end, row.period_start, row.account_id))


class _Tables(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._table = []
        if self._table is None:
            return
        if tag == "tr":
            self._row = []
        if tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        if tag == "tr" and self._row is not None and self._table is not None:
            self._table.append(self._row)
            self._row = None
        if tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None


def _numeric_cells(row: list[str]) -> list[str]:
    result = []
    for cell in row[1:]:
        value = cell.replace(",", "").replace("−", "-").strip()
        if value in {"", "$", "%", "—", "–"}:
            continue
        if value.startswith("(") and value.endswith(")"):
            value = "-" + value[1:-1]
        if value.lstrip("-").isdigit():
            result.append(value)
    return result


def parse_quarter_html(payload: bytes) -> list[Extracted]:
    """Read three explicitly headed unaudited consolidated 8-K tables."""

    parser = _Tables()
    parser.feed(payload.decode("utf-8"))
    def find_table(required: set[str]) -> list[list[str]]:
        matches = [table for table in parser.tables if required <= {row[0] for row in table if row}]
        if len(matches) != 1:
            raise ValueError(f"expected one 8-K statement table for {required}, found {len(matches)}")
        return matches[0]

    income = find_table({"Net sales", "Operating income", "Consolidated net income"})
    balance = find_table({"Cash and cash equivalents", "Total current assets", "Total assets"})
    cash = find_table({"Net cash provided by operating activities", "Net cash used in investing activities", "Cash, cash equivalents and restricted cash at end of period"})
    output: list[Extracted] = []
    for table_name, table, specs, periods in (
        ("income", income, QUARTER_INCOME, ((date(2026, 2, 1), date(2026, 4, 30)), (date(2025, 2, 1), date(2025, 4, 30)))),
        ("balance", balance, QUARTER_BALANCE, ((date(2026, 4, 30), date(2026, 4, 30)), (date(2026, 1, 31), date(2026, 1, 31)), (date(2025, 4, 30), date(2025, 4, 30)))),
        ("cash", cash, QUARTER_CASH, ((date(2026, 2, 1), date(2026, 4, 30)), (date(2025, 2, 1), date(2025, 4, 30)))),
    ):
        matches: dict[str, list[str]] = {}
        for row in table:
            if row and row[0] in specs:
                if row[0] in matches:
                    raise ValueError(f"duplicate 8-K label {table_name}:{row[0]}")
                matches[row[0]] = _numeric_cells(row)
        if set(matches) != set(specs):
            raise ValueError(f"missing 8-K rows in {table_name}: {set(specs) - set(matches)}")
        for label, metric in specs.items():
            values = matches[label]
            if len(values) < len(periods):
                raise ValueError(f"missing 8-K value {table_name}:{label}")
            for index, (start, end) in enumerate(periods):
                value = values[index]
                if table_name == "cash" and label == "Cash, cash equivalents and restricted cash at beginning of year":
                    start = end = date(2026 if index == 0 else 2025, 1, 31)
                elif table_name == "cash" and label == "Cash, cash equivalents and restricted cash at end of period":
                    start = end = date(2026 if index == 0 else 2025, 4, 30)
                period_type = "INSTANT" if table_name == "balance" or label.startswith("Cash, cash equivalents") else "QUARTER"
                metric_id = f"{metric}_quarter" if period_type == "QUARTER" else metric
                output.append(Extracted(
                    f"html:{table_name}:{label}", label, metric_id, start, end,
                    period_type,
                    value,
                    -1 if metric == "capital_expenditure_payments" else 1,
                ))
    return output


def canonical_usd_value(item: Extracted, filing_kind: str) -> str:
    """Apply the documented exact SEC exhibit USD millions-to-USD transform."""

    if filing_kind not in {"FY25_XBRL", "FY26_XBRL", "FY27Q1_HTML"}:
        raise ValueError(f"unsupported filing kind: {filing_kind}")
    return str(int(item.value) * (1_000_000 if filing_kind == "FY27Q1_HTML" else 1))


def _append_unique(path: Path, rows: list[dict[str, str]], key_field: str) -> None:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames
        existing = {row[key_field]: row for row in reader}
    if not header:
        raise ValueError(f"missing CSV header: {path}")
    additions = []
    for row in rows:
        full = {name: row.get(name, "") for name in header}
        key = full[key_field]
        if key in existing:
            if existing[key] != full:
                raise ValueError(f"immutable {key_field} differs in {path}: {key}")
        else:
            existing[key] = full
            additions.append(full)
    if additions:
        with path.open("a", encoding="utf-8", newline="") as handle:
            csv.DictWriter(handle, fieldnames=header).writerows(additions)


def ingest() -> None:
    all_extracted: list[tuple[Filing, list[Extracted], str, str]] = []
    for filing in FILINGS:
        payload, raw_response_sha256 = _fetch(filing)
        extracted = (parse_quarter_html(payload) if filing.kind == "FY27Q1_HTML"
                     else parse_xbrl(payload, filing.kind))
        all_extracted.append((filing, extracted, hashlib.sha256(payload).hexdigest(), raw_response_sha256))

    for filing, extracted, digest, raw_response_sha256 in all_extracted:
        prior = [item for item in load_source_ledger(EVIDENCE) if item.source_id == filing.source_id]
        if prior:
            if len(prior) != 1 or prior[0].content_sha256 != digest:
                raise ValueError(f"source has an unreviewed retrieval vintage: {filing.source_id}")
            receipt = prior[0]
        else:
            receipt = register_source_locator(EVIDENCE, SourceMetadata(
                source_id=filing.source_id,
                access_class=AccessClass.PUBLIC_REGULATORY,
                authority="Walmart Inc.; U.S. SEC EDGAR",
                title=filing.title,
                url=filing.url,
                document_id=filing.document_id,
                first_public_at=datetime.fromisoformat(filing.public_at),
                retrieved_at=datetime.now(UTC),
                publication_status=PublicationStatus.FILED,
                period_start=min(item.period_start for item in extracted),
                period_end=max(item.period_end for item in extracted),
                entity_scope="walmart_consolidated_group",
                currency="USD",
                unit="USD_MILLION" if filing.kind == "FY27Q1_HTML" else "USD",
                retention_right=False,
                transformation_right=True,
                redistribution_right=False,
                cutoff_eligible=True,
                notes=(
                    "content_sha256 is canonical filing-body SHA-256 after optional SEC Akamai "
                    "transport script/pixel removal; raw_response_sha256=" + raw_response_sha256 + ". "
                    "SEC acceptance gives a conservative public-availability bound; Q1 uses "
                    "07:00 ET after 06:59:53 acceptance. Minimal numeric facts for personal "
                    "research only; source bytes not retained or redistributed. 8-K EX-99.1 "
                    "is furnished. XBRL raw values in USD; 8-K rendered tables in USD "
                    "millions are scaled by 1000000 before raw-fact storage."
                ),
            ), digest)

        bridge_id = f"{filing.source_id}_consolidated_bridge"
        _append_unique(EVIDENCE / "scope_bridges.csv", [{
            "bridge_id": bridge_id,
            "economic_scope_id": "walmart_consolidated_group",
            "legal_entity_id": "walmart_inc_us_de",
            "relation": "CONSOLIDATED_GROUP_REPORTED_BY_WALMART_INC_NOT_PARENT_ONLY_CASH",
            "source_id": receipt.source_id,
            "first_public_at": _utc_iso(receipt.first_public_at) if receipt.first_public_at else "",
            "review_status": "APPROVED",
            "snapshot_id": receipt.snapshot_id,
            "content_sha256": receipt.content_sha256,
            "retrieved_at": _utc_iso(receipt.retrieved_at),
        }], "bridge_id")

        mapping_rows = []
        metric_rows = []
        facts = []
        for item in extracted:
            mapping_id = f"map_{filing.source_id}_{hashlib.sha256(item.account_id.encode()).hexdigest()[:12]}"
            mapping_rows.append({
                "mapping_id": mapping_id,
                "source_id": filing.source_id,
                "raw_account_id": item.account_id,
                "raw_label": item.label,
                "normalized_metric_id": item.metric_id,
                "effective_from": item.period_start.isoformat(),
                "effective_to": item.period_end.isoformat(),
                "mapping_reason": (
                    "8-K presented USD millions; exact approved source extraction transform x1000000 to USD; "
                    + ("parenthesized capex payment sign reversed to positive spend" if item.sign_multiplier == -1 else "published sign preserved")
                    if filing.kind == "FY27Q1_HTML" else "Direct XBRL source line in USD; sign preserved"
                ),
                "confidence": "HIGH",
                "review_status": "APPROVED",
                "sign_multiplier": f"{item.sign_multiplier:+d}",
            })
            metric_rows.append({
                "metric_id": item.metric_id,
                "display_name": item.metric_id.replace("_", " ").title(),
                "definition": f"Walmart consolidated {item.metric_id.replace('_', ' ')}; signed source statement line in USD.",
                "formula": "SOURCE_VALUE",
                "grain": "WALMART_CONSOLIDATED_GROUP",
                "period_type": item.period_type,
                "currency_policy": "USD",
                "unit": "USD",
                "sign_convention": "POSITIVE_SPEND" if item.metric_id.startswith("capital_expenditure_payments") else "PUBLISHED_SIGN",
                "source_priority": "SEC_FILING",
                "publication_lag": "SOURCE_RECEIPT",
                "controllability": "PUBLIC_ACTUAL",
                "limitations": "Consolidated; not parent-obligor cash. Cash and cash equivalents exclude restricted cash." if item.metric_id == "cash_and_equivalents" else "Consolidated public statement line.",
                "review_status": "APPROVED",
            })
            value = canonical_usd_value(item, filing.kind)
            facts.append(RawFact(
                fact_id=f"raw_{filing.source_id}_{hashlib.sha256((item.account_id + item.period_start.isoformat() + item.period_end.isoformat()).encode()).hexdigest()[:16]}",
                source_id=filing.source_id,
                snapshot_id=receipt.snapshot_id,
                version_id=filing.version_id,
                economic_scope_id="walmart_consolidated_group",
                accounting_scope="CONSOLIDATED",
                economic_legal_scope_bridge_id=bridge_id,
                legal_entity_id="walmart_inc_us_de",
                raw_account_id=item.account_id,
                metric_id=item.metric_id,
                period_start=item.period_start,
                period_end=item.period_end,
                period_type=item.period_type,
                currency="USD",
                unit="USD",
                raw_value=value,
                raw_label=item.label,
                extraction_method="SEC_8K_HTML_EX991_TABLE_USDM_TO_USD_X1000000_V1" if filing.kind == "FY27Q1_HTML" else "SEC_XBRL_NON_DIMENSIONAL_DECIMALS_MINUS6_V1",
                mapping_version=mapping_id,
                review_status="SOURCE_EXTRACTED",
            ))

        # Mapping effective ranges cover all selected periods for a source line.
        by_mapping: dict[str, dict[str, str]] = {}
        for row in mapping_rows:
            old = by_mapping.get(row["mapping_id"])
            if old is None:
                by_mapping[row["mapping_id"]] = row
            else:
                old["effective_from"] = min(old["effective_from"], row["effective_from"])
                old["effective_to"] = max(old["effective_to"], row["effective_to"])
        _append_unique(EVIDENCE / "mappings.csv", list(by_mapping.values()), "mapping_id")
        # Metric definitions cannot combine duration and instant under one ID.
        by_metric: dict[str, dict[str, str]] = {}
        for row in metric_rows:
            old = by_metric.get(row["metric_id"])
            if old is not None and old["period_type"] != row["period_type"]:
                raise ValueError(f"metric has mixed period types: {row['metric_id']}")
            by_metric[row["metric_id"]] = row
        _append_unique(EVIDENCE / "metric_dictionary.csv", list(by_metric.values()), "metric_id")
        _append_unique(CORE / "versions.csv", [{
            "version_id": filing.version_id,
            "version_type": "PUBLIC_ACTUAL",
            "as_of_date": "2025-01-31" if filing.kind == "FY25_XBRL" else "2026-01-31" if filing.kind == "FY26_XBRL" else "2026-04-30",
            "publication_status": "FILED",
            "information_cutoff": CUTOFF,
            "created_by": "Walmart Inc.; SEC EDGAR",
            "immutable": "true",
            "notes": "Original SEC filing snapshot; as-of analysis cutoff does not imply filed at period end. EX-99.1 is furnished." if filing.kind == "FY27Q1_HTML" else "Original SEC 10-K XBRL filing snapshot.",
        }], "version_id")
        if filing.kind == "FY26_XBRL":
            by_key = {(fact.metric_id, fact.period_end, fact.period_type): fact.fact_id for fact in facts}
            end = date(2026, 1, 31)
            opening = date(2025, 1, 31)
            _append_unique(CORE / "cash_identity_checks.csv", [{
                "identity_id": "wmt_fy26_cash_including_restricted",
                "version_id": filing.version_id,
                "opening_cash_fact_id": by_key[("cash_restricted_end", opening, "INSTANT")],
                "operating_cash_flow_fact_id": by_key[("operating_cash_flow_year", end, "YEAR")],
                "investing_cash_flow_fact_id": by_key[("investing_cash_flow_year", end, "YEAR")],
                "financing_cash_flow_fact_id": by_key[("financing_cash_flow_year", end, "YEAR")],
                "fx_and_other_fact_id": by_key[("fx_effect_on_cash_year", end, "YEAR")],
                "closing_cash_fact_id": by_key[("cash_restricted_end", end, "INSTANT")],
            }], "identity_id")
        print(filing.source_id, "facts", len(facts), "new", append_raw_facts(EVIDENCE, facts), "sha256", digest)


if __name__ == "__main__":
    ingest()
