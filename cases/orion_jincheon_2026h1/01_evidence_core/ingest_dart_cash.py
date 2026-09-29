"""Ingest the four pinned Orion 2026 H1 DART cash-flow sections.

Run from the repository root with::

    $env:PYTHONPATH='src'
    python cases/orion_jincheon_2026h1/01_evidence_core/ingest_dart_cash.py

The official HTML is read into memory and never retained in the case. The
ledger records a locator and SHA-256, plus the six minimally transformed facts.
This one-time loader refuses populated target CSVs to preserve append-only
vintages and avoid manufacturing a second retrieval on a rerun.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from urllib.request import Request, urlopen

from versioned_finance_core.contracts.enums import (
    AccessClass,
    AccountingScope,
    PublicationStatus,
)
from versioned_finance_core.evidence import (
    RawFact,
    SourceMetadata,
    append_raw_facts,
    parse_dart_cash_statement,
    register_source_locator,
)

CASE_DIR = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = CASE_DIR / "01_evidence_core"
CORE_DIR = CASE_DIR / "02_financial_core"
FILED_VERSION = "orion_2026h1_filed_20260814"
REVISED_VERSION = "orion_2026h1_revised_20260818"
PERIOD_START = date(2026, 1, 1)
PERIOD_END = date(2026, 6, 30)
ROLES = (
    "opening_cash",
    "operating_cash_flow",
    "investing_cash_flow",
    "financing_cash_flow",
    "fx_and_other",
    "closing_cash",
)


@dataclass(frozen=True)
class SourceSpec:
    filing: str
    scope: AccountingScope
    rcp_no: str
    url: str
    digest: str
    first_public_at: str
    list_url: str
    publication_status: PublicationStatus
    version_id: str

    @property
    def source_id(self) -> str:
        return f"dart_orion_2026h1_{self.filing}_{self.scope.value.lower()}_cf"


SOURCES = (
    SourceSpec(
        "filed", AccountingScope.CONSOLIDATED, "20260814001054",
        "https://dart.fss.or.kr/report/viewer.do?rcpNo=20260814001054&dcmNo=11528937&eleId=23&offset=553268&length=52038&dtd=dart4.xsd",
        "af4bb8728de3f113fd3bc2192022733571e5b338369e1ccc6dbe599f6263f894",
        "2026-08-14T12:36:59+09:00",
        "https://dart.fss.or.kr/dsac001/mainAll.do?selectDate=20260814&textCrpCik=01238169",
        PublicationStatus.FILED, FILED_VERSION,
    ),
    SourceSpec(
        "filed", AccountingScope.STANDALONE, "20260814001054",
        "https://dart.fss.or.kr/report/viewer.do?rcpNo=20260814001054&dcmNo=11528937&eleId=65&offset=2229338&length=47323&dtd=dart4.xsd",
        "13250d7471cd31dca886c4a795358b15b672ba8f45c16c543230f10537c58151",
        "2026-08-14T12:36:59+09:00",
        "https://dart.fss.or.kr/dsac001/mainAll.do?selectDate=20260814&textCrpCik=01238169",
        PublicationStatus.FILED, FILED_VERSION,
    ),
    SourceSpec(
        "revised", AccountingScope.CONSOLIDATED, "20260818000305",
        "https://dart.fss.or.kr/report/viewer.do?rcpNo=20260818000305&dcmNo=11541739&eleId=25&offset=827453&length=52038&dtd=dart4.xsd",
        "af4bb8728de3f113fd3bc2192022733571e5b338369e1ccc6dbe599f6263f894",
        "2026-08-18T17:38:59+09:00",
        "https://dart.fss.or.kr/dsac001/mainAll.do?selectDate=20260818&textCrpCik=01238169",
        PublicationStatus.REVISED, REVISED_VERSION,
    ),
    SourceSpec(
        "revised", AccountingScope.STANDALONE, "20260818000305",
        "https://dart.fss.or.kr/report/viewer.do?rcpNo=20260818000305&dcmNo=11541739&eleId=67&offset=2503523&length=47323&dtd=dart4.xsd",
        "13250d7471cd31dca886c4a795358b15b672ba8f45c16c543230f10537c58151",
        "2026-08-18T17:38:59+09:00",
        "https://dart.fss.or.kr/dsac001/mainAll.do?selectDate=20260818&textCrpCik=01238169",
        PublicationStatus.REVISED, REVISED_VERSION,
    ),
)


def _download(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (research evidence check)"})
    with urlopen(request, timeout=30) as response:
        return response.read()


def _read_header_only(path: Path) -> tuple[str, ...]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.reader(handle) if row]
    if len(rows) != 1 or not rows[0] or len(rows[0]) != len(set(rows[0])):
        raise ValueError(f"Expected an unpopulated CSV contract: {path}")
    return tuple(rows[0])


def _append_rows(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    header = _read_header_only(path)
    if any(set(row) - set(header) for row in rows):
        raise ValueError(f"Rows contain unrecognized columns: {path}")
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writerows(rows)


def _period(role: str) -> tuple[date, date, str]:
    if role == "opening_cash":
        previous_day = PERIOD_START - timedelta(days=1)
        return previous_day, previous_day, "INSTANT"
    if role == "closing_cash":
        return PERIOD_END, PERIOD_END, "INSTANT"
    return PERIOD_START, PERIOD_END, "HALF_YEAR"


def _fact_id(spec: SourceSpec, role: str) -> str:
    return f"orion_2026h1_{spec.filing}_{spec.scope.value.lower()}_{role}"


def _mapping_id(spec: SourceSpec, role: str) -> str:
    return f"map_{spec.source_id}_{role}_v1"


def _bridge_id(spec: SourceSpec) -> str:
    return f"bridge_orion_parent_{spec.filing}_v1"


def main() -> None:
    contracts = (
        EVIDENCE_DIR / "source_ledger.csv",
        EVIDENCE_DIR / "raw_facts.csv",
        EVIDENCE_DIR / "mappings.csv",
        EVIDENCE_DIR / "metric_dictionary.csv",
        EVIDENCE_DIR / "scope_bridges.csv",
        CORE_DIR / "versions.csv",
        CORE_DIR / "cash_identity_checks.csv",
    )
    for path in contracts:
        _read_header_only(path)

    # Complete all downloads, checks and parsing before any case mutation.
    fetched = []
    for spec in SOURCES:
        body = _download(spec.url)
        retrieved_at = datetime.now(UTC)
        digest = sha256(body).hexdigest()
        if digest != spec.digest:
            raise ValueError(f"DART section changed; review before ingesting: {spec.source_id}")
        statement = parse_dart_cash_statement(body.decode("utf-8"))
        if (statement.accounting_scope, statement.period_start, statement.period_end) != (
            spec.scope, PERIOD_START, PERIOD_END
        ):
            raise ValueError(f"DART section scope or period changed: {spec.source_id}")
        fetched.append((spec, statement, retrieved_at))

    facts: list[RawFact] = []
    mappings: list[dict[str, str]] = []
    bridges: list[dict[str, str]] = []
    for spec, statement, retrieved_at in fetched:
        metadata = SourceMetadata(
            source_id=spec.source_id,
            access_class=AccessClass.PUBLIC_OFFICIAL,
            authority="Financial Supervisory Service DART",
            title=f"Orion 2026 H1 {spec.scope.value.lower()} cash-flow section ({spec.filing})",
            url=spec.url,
            document_id=f"rcpNo={spec.rcp_no};section={spec.scope.value}",
            first_public_at=datetime.fromisoformat(spec.first_public_at),
            retrieved_at=retrieved_at,
            publication_status=spec.publication_status,
            period_start=PERIOD_START,
            period_end=PERIOD_END,
            entity_scope=(
                "orion_parent_standalone" if spec.scope is AccountingScope.STANDALONE
                else "orion_consolidated_group"
            ),
            currency="KRW",
            unit="KRW",
            transformation_right=True,
            cutoff_eligible=True,
            notes=(
                "DART official filing list " + spec.list_url + "; display precision is one minute. "
                "first_public_at uses the final second of that minute as a conservative "
                "known-public-by bound, not an observed publication second. "
                "OpenDART public data use: https://opendart.fss.or.kr/disclosureinfo/fnltt/singl/main.do. "
                "Locator and minimal transformed facts only; raw redistribution right unconfirmed."
            ),
        )
        receipt = register_source_locator(EVIDENCE_DIR, metadata, spec.digest)
        if spec.scope is AccountingScope.STANDALONE:
            bridges.append({
                "bridge_id": _bridge_id(spec),
                "economic_scope_id": "orion_parent_standalone",
                "legal_entity_id": "orion_co_ltd_kr",
                "relation": "STANDALONE_FINANCIAL_STATEMENTS_OF_FILER",
                "source_id": spec.source_id,
                "snapshot_id": receipt.snapshot_id,
                "content_sha256": receipt.content_sha256,
                "first_public_at": receipt.first_public_at.isoformat(),
                "retrieved_at": receipt.retrieved_at.isoformat(),
                "review_status": "APPROVED",
            })
        for row in statement.rows:
            start, end, period_type = _period(row.role)
            facts.append(RawFact(
                fact_id=_fact_id(spec, row.role),
                source_id=spec.source_id,
                snapshot_id=receipt.snapshot_id,
                version_id=spec.version_id,
                economic_scope_id=metadata.entity_scope,
                accounting_scope=spec.scope.value,
                metric_id=row.role,
                period_start=start,
                period_end=end,
                period_type=period_type,
                currency="KRW",
                unit="KRW",
                raw_value=str(row.value),
                raw_label=row.raw_label,
                extraction_method="DART_HTML_CURRENT_COLUMN_V1",
                review_status="SOURCE_EXTRACTED",
                legal_entity_id=(
                    "orion_co_ltd_kr" if spec.scope is AccountingScope.STANDALONE else ""
                ),
                economic_legal_scope_bridge_id=(
                    _bridge_id(spec) if spec.scope is AccountingScope.STANDALONE else ""
                ),
                raw_account_id=row.raw_label,
                mapping_version=_mapping_id(spec, row.role),
            ))
            mappings.append({
                "mapping_id": _mapping_id(spec, row.role),
                "source_id": spec.source_id,
                "raw_account_id": row.raw_label,
                "raw_label": row.raw_label,
                "normalized_metric_id": row.role,
                "mapping_reason": "Exact DART cash-flow row; filed sign retained",
                "confidence": "EXACT_LABEL",
                "reviewer": "case_evidence_review",
                "review_status": "APPROVED",
                "sign_multiplier": "+1",
            })

    # Append-only APIs validate receipt linkage and refuse changed facts.
    append_raw_facts(EVIDENCE_DIR, facts)
    _append_rows(EVIDENCE_DIR / "mappings.csv", mappings)
    _append_rows(EVIDENCE_DIR / "scope_bridges.csv", bridges)
    _append_rows(EVIDENCE_DIR / "metric_dictionary.csv", [
        {
            "metric_id": role,
            "display_name": role.replace("_", " "),
            "definition": "DART 2026 H1 cash-flow statement row, by accounting scope",
            "formula": "SOURCE_VALUE",
            "grain": "FINANCIAL_STATEMENT_SCOPE",
            "period_type": "INSTANT" if role in {"opening_cash", "closing_cash"} else "HALF_YEAR",
            "currency_policy": "KRW",
            "unit": "KRW",
            "sign_convention": "FILED_SIGN",
            "source_priority": "DART_OFFICIAL",
            "publication_lag": "SOURCE_RECEIPT",
            "controllability": "REPORTED_FACT",
            "limitations": "Entity-wide financial statement; not Jincheon-project-specific",
            "review_status": "APPROVED",
        }
        for role in ROLES
    ])
    _append_rows(CORE_DIR / "versions.csv", [
        {
            "version_id": version_id,
            "version_type": "PUBLIC_ACTUAL",
            "as_of_date": PERIOD_END.isoformat(),
            "publication_status": status,
            "supersedes_version_id": supersedes,
            "information_cutoff": cutoff,
            "created_by": "official_DART_filing",
            "immutable": "true",
            "notes": "Corrected filing changed executive compensation disclosure; cash section bytes match original",
        }
        for version_id, status, supersedes, cutoff in (
            (FILED_VERSION, "FILED", "", SOURCES[0].first_public_at),
            (REVISED_VERSION, "REVISED", FILED_VERSION, SOURCES[2].first_public_at),
        )
    ])
    _append_rows(CORE_DIR / "cash_identity_checks.csv", [{
        "identity_id": "orion_parent_2026h1_revised_cash_rollforward",
        "version_id": REVISED_VERSION,
        **{
            f"{role}_fact_id": _fact_id(SOURCES[3], role)
            for role in ROLES
        },
    }])
    print(f"Registered {len(fetched)} DART receipts and {len(facts)} facts; raw HTML not retained")


if __name__ == "__main__":
    main()
