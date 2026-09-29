from __future__ import annotations

import csv
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from shutil import copyfile

import pytest

from versioned_finance_core.contracts.enums import AccessClass, PublicationStatus
from versioned_finance_core.contracts.records import RawFact as ContractRawFact
from versioned_finance_core.evidence import (
    RawFact,
    SourceMetadata,
    append_raw_facts,
    content_path,
    ingest_snapshot,
    load_provenanced_facts,
    load_source_ledger,
    receipt_id,
    register_source_locator,
    select_known_facts,
    select_latest_known_facts,
    sha256_file,
    verify_snapshot_content,
)

TEMPLATE = Path(__file__).parents[2] / "cases" / "_template" / "01_evidence_core"


def _at(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


def _metadata(
    *, first_public_at: datetime | None, retrieved_at: datetime, **changes: object
) -> SourceMetadata:
    base = SourceMetadata(
        source_id="synthetic_disclosure",
        access_class=AccessClass.SYNTHETIC_TEST,
        authority="Synthetic fixture",
        title="Synthetic statement",
        url="https://example.invalid/fixture",
        document_id="SYNTHETIC-001",
        event_at=_at(2025, 12, 31),
        first_public_at=first_public_at,
        retrieved_at=retrieved_at,
        publication_status=PublicationStatus.FILED,
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        entity_scope="synthetic_consolidated",
        currency="KRW",
        unit="KRW_million",
        retention_right=True,
        transformation_right=True,
        redistribution_right=True,
        cutoff_eligible=True,
        notes="SYNTHETIC_TEST_ONLY; not a real company or market fact",
    )
    return replace(base, **changes)


def _fact(snapshot_id: str, *, fact_id: str, raw_value: str, version_id: str) -> RawFact:
    return RawFact(
        fact_id=fact_id,
        source_id="synthetic_disclosure",
        snapshot_id=snapshot_id,
        version_id=version_id,
        economic_scope_id="synthetic_group",
        accounting_scope="CONSOLIDATED",
        raw_account_id="synthetic_revenue_account",
        metric_id="revenue",
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        period_type="FY",
        currency="KRW",
        unit="KRW_million",
        raw_value=raw_value,
        raw_label="Revenue (synthetic)",
        extraction_method="manual_fixture",
        mapping_version="synthetic_mapping_v1",
        review_status="REVIEWED_SYNTHETIC",
    )


def _template_evidence(tmp_path: Path) -> Path:
    evidence = tmp_path / "01_evidence_core"
    evidence.mkdir()
    for name in ("source_ledger.csv", "raw_facts.csv"):
        copyfile(TEMPLATE / name, evidence / name)
    return evidence


def test_receipts_append_without_replacing_source_bytes(tmp_path: Path) -> None:
    evidence = _template_evidence(tmp_path)
    source = tmp_path / "source.txt"
    source.write_bytes(b"synthetic original 100")
    first_meta = _metadata(first_public_at=_at(2026, 1, 2), retrieved_at=_at(2026, 1, 3))
    first = ingest_snapshot(evidence, source, first_meta)
    assert first.content_sha256 == sha256_file(source)
    assert first.snapshot_id == receipt_id(
        first.source_id, first.retrieved_at, first.content_sha256
    )
    assert content_path(evidence, first).read_bytes() == b"synthetic original 100"
    assert verify_snapshot_content(evidence, first)

    assert ingest_snapshot(evidence, source, first_meta) == first
    repeat = ingest_snapshot(
        evidence, source, replace(first_meta, retrieved_at=_at(2026, 1, 4))
    )
    assert repeat.snapshot_id != first.snapshot_id
    assert content_path(evidence, repeat) == content_path(evidence, first)
    assert len(tuple((evidence / "raw_snapshots").rglob(first.content_sha256))) == 1

    source.write_bytes(b"synthetic amendment 110")
    amended = ingest_snapshot(
        evidence,
        source,
        replace(
            first_meta,
            first_public_at=_at(2026, 1, 10),
            retrieved_at=_at(2026, 2, 1),
            publication_status=PublicationStatus.RESTATED,
        ),
    )
    assert amended.snapshot_id != first.snapshot_id
    assert content_path(evidence, amended).read_bytes() == b"synthetic amendment 110"
    assert content_path(evidence, first).read_bytes() == b"synthetic original 100"
    assert len(load_source_ledger(evidence)) == 3


def test_fact_provenance_and_cutoff_do_not_look_ahead(tmp_path: Path) -> None:
    evidence = _template_evidence(tmp_path)
    source = tmp_path / "source.txt"
    source.write_bytes(b"filed value 100")
    original = ingest_snapshot(
        evidence,
        source,
        _metadata(first_public_at=_at(2026, 1, 2), retrieved_at=_at(2026, 1, 3)),
    )
    source.write_bytes(b"restated value 110")
    restated = ingest_snapshot(
        evidence,
        source,
        _metadata(
            first_public_at=_at(2026, 1, 10),
            retrieved_at=_at(2026, 2, 1),
            publication_status=PublicationStatus.RESTATED,
        ),
    )
    first_fact = _fact(original.snapshot_id, fact_id="fact_filed", raw_value="100", version_id="v1")
    later_fact = _fact(
        restated.snapshot_id, fact_id="fact_restated", raw_value="110", version_id="v2"
    )
    assert append_raw_facts(evidence, [first_fact, later_fact]) == 2
    assert append_raw_facts(evidence, [first_fact]) == 0
    with pytest.raises(ValueError, match="immutable fact_id"):
        append_raw_facts(evidence, [replace(first_fact, raw_value="999")])

    with (evidence / "raw_facts.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["snapshot_id"] == original.snapshot_id
    assert rows[0]["content_sha256"] == original.content_sha256
    assert rows[0]["first_public_at"] == "2026-01-02T00:00:00.000000Z"
    assert rows[1]["retrieved_at"] == "2026-02-01T00:00:00.000000Z"

    facts = load_provenanced_facts(evidence)
    assert facts[0].as_csv_row()["snapshot_id"] == original.snapshot_id
    assert facts[1].as_csv_row()["content_sha256"] == restated.content_sha256
    assert ContractRawFact.from_mapping(facts[0].as_csv_row()).provenance.snapshot_id == (
        original.snapshot_id
    )
    assert [item.fact.raw_value for item in select_known_facts(facts, _at(2026, 1, 5))] == [
        "100"
    ]
    assert [
        item.fact.raw_value for item in select_latest_known_facts(facts, _at(2026, 1, 20))
    ] == ["110"]
    assert [item.fact.version_id for item in select_known_facts(facts, _at(2026, 1, 20))] == [
        "v1",
        "v2",
    ]


def test_locator_and_unknown_publication_time_never_create_false_cutoff_fact(
    tmp_path: Path,
) -> None:
    evidence = _template_evidence(tmp_path)
    metadata = _metadata(
        first_public_at=None,
        retrieved_at=_at(2026, 1, 3),
        retention_right=False,
        redistribution_right=False,
        cutoff_eligible=False,
    )
    source = tmp_path / "restricted.txt"
    source.write_bytes(b"synthetic locator-only payload")
    with pytest.raises(ValueError, match="retention and redistribution"):
        ingest_snapshot(evidence, source, metadata)
    receipt = register_source_locator(evidence, metadata, sha256_file(source))
    assert not content_path(evidence, receipt).exists()
    assert not verify_snapshot_content(evidence, receipt)
    assert append_raw_facts(
        evidence, [_fact(receipt.snapshot_id, fact_id="fact_unknown", raw_value="100", version_id="v1")]
    ) == 1
    assert select_known_facts(load_provenanced_facts(evidence), _at(2026, 12, 31)) == ()


def test_lineage_tampering_and_invalid_timestamps_fail(tmp_path: Path) -> None:
    evidence = _template_evidence(tmp_path)
    source = tmp_path / "source.txt"
    source.write_bytes(b"synthetic fact")
    metadata = _metadata(first_public_at=_at(2026, 1, 2), retrieved_at=_at(2026, 1, 3))
    receipt = ingest_snapshot(evidence, source, metadata)
    append_raw_facts(evidence, [_fact(receipt.snapshot_id, fact_id="fact_1", raw_value="1", version_id="v1")])

    path = evidence / "raw_facts.csv"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace(receipt.content_sha256, "0" * 64), encoding="utf-8")
    with pytest.raises(ValueError, match="conflicting content_sha256"):
        load_provenanced_facts(evidence)

    with pytest.raises(ValueError, match="UTC offset"):
        ingest_snapshot(
            evidence,
            source,
            replace(metadata, retrieved_at=datetime(2026, 1, 3)),  # noqa: DTZ001
        )
    with pytest.raises(ValueError, match="chunk_size"):
        sha256_file(source, chunk_size=0)

    content_path(evidence, receipt).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="snapshot content hash mismatch"):
        verify_snapshot_content(evidence, receipt)


def test_raw_accounts_can_share_metric_before_normalization(tmp_path: Path) -> None:
    evidence = _template_evidence(tmp_path)
    source = tmp_path / "source.txt"
    source.write_bytes(b"synthetic account split")
    receipt = ingest_snapshot(
        evidence,
        source,
        _metadata(first_public_at=_at(2026, 1, 2), retrieved_at=_at(2026, 1, 3)),
    )
    first = replace(
        _fact(receipt.snapshot_id, fact_id="account_a", raw_value="40", version_id="v1"),
        raw_account_id="goods_revenue",
        metric_id="",
    )
    second = replace(
        first, fact_id="account_b", raw_account_id="services_revenue", raw_value="60"
    )
    assert append_raw_facts(evidence, [first, second]) == 2
    assert len(load_provenanced_facts(evidence)) == 2


def test_existing_writer_lock_prevents_partial_append(tmp_path: Path) -> None:
    evidence = _template_evidence(tmp_path)
    source = tmp_path / "source.txt"
    source.write_bytes(b"synthetic payload")
    (evidence / ".evidence_write.lock").write_text("other writer", encoding="utf-8")
    with pytest.raises(RuntimeError, match="writer lock"):
        ingest_snapshot(
            evidence,
            source,
            _metadata(first_public_at=_at(2026, 1, 2), retrieved_at=_at(2026, 1, 3)),
        )
    assert load_source_ledger(evidence) == ()
    assert not (evidence / "raw_snapshots").exists()
