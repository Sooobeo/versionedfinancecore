"""Raw fact lineage and publication-cutoff selection.

Every raw fact points at one immutable receipt. Normalization, source precedence
across publishers, and financial version interpretation belong to the core.
"""

from __future__ import annotations

import csv
import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from versioned_finance_core.evidence.cutoff import known_at_cutoff
from versioned_finance_core.evidence.ledger import (
    SnapshotReceipt,
    _exclusive_writer,
    _utc_iso,
    load_source_ledger,
)

FACT_FIELDS = (
    "fact_id",
    "source_id",
    "snapshot_id",
    "content_sha256",
    "first_public_at",
    "retrieved_at",
    "version_id",
    "economic_scope_id",
    "accounting_scope",
    "economic_legal_scope_bridge_id",
    "legal_entity_id",
    "instrument_id",
    "segment_id",
    "raw_account_id",
    "metric_id",
    "period_start",
    "period_end",
    "period_type",
    "currency",
    "unit",
    "raw_value",
    "raw_label",
    "claim_tag",
    "extraction_method",
    "mapping_version",
    "review_status",
)


@dataclass(frozen=True)
class RawFact:
    fact_id: str
    source_id: str
    snapshot_id: str
    version_id: str
    economic_scope_id: str
    accounting_scope: str
    metric_id: str
    period_start: date
    period_end: date
    period_type: str
    currency: str
    unit: str
    raw_value: str
    raw_label: str
    extraction_method: str
    review_status: str
    legal_entity_id: str = ""
    instrument_id: str = ""
    segment_id: str = ""
    economic_legal_scope_bridge_id: str = ""
    raw_account_id: str = ""
    claim_tag: str = "F"
    mapping_version: str = ""

    def validate(self) -> None:
        required = (
            "fact_id",
            "source_id",
            "snapshot_id",
            "version_id",
            "economic_scope_id",
            "accounting_scope",
            "raw_account_id",
            "period_type",
            "currency",
            "unit",
            "raw_value",
            "extraction_method",
            "review_status",
        )
        missing = [name for name in required if not getattr(self, name)]
        if missing:
            raise ValueError(f"raw fact is missing required fields: {', '.join(missing)}")
        if self.claim_tag != "F":
            raise ValueError("raw facts must carry F claim tag; derived claims belong downstream")
        if self.period_start > self.period_end:
            raise ValueError("period_start must not follow period_end")


@dataclass(frozen=True)
class ProvenancedFact:
    fact: RawFact
    receipt: SnapshotReceipt

    @property
    def first_public_at(self) -> datetime | None:
        return self.receipt.first_public_at

    def as_csv_row(self) -> dict[str, str]:
        """Return the validated raw-fact contract row with receipt lineage."""

        return _as_row(self.fact, self.receipt)


def _as_row(fact: RawFact, receipt: SnapshotReceipt) -> dict[str, str]:
    return {
        "fact_id": fact.fact_id,
        "source_id": fact.source_id,
        "snapshot_id": fact.snapshot_id,
        "content_sha256": receipt.content_sha256,
        "first_public_at": _utc_iso(receipt.first_public_at) if receipt.first_public_at else "",
        "retrieved_at": _utc_iso(receipt.retrieved_at),
        "version_id": fact.version_id,
        "economic_scope_id": fact.economic_scope_id,
        "accounting_scope": fact.accounting_scope,
        "economic_legal_scope_bridge_id": fact.economic_legal_scope_bridge_id,
        "legal_entity_id": fact.legal_entity_id,
        "instrument_id": fact.instrument_id,
        "segment_id": fact.segment_id,
        "raw_account_id": fact.raw_account_id,
        "metric_id": fact.metric_id,
        "period_start": fact.period_start.isoformat(),
        "period_end": fact.period_end.isoformat(),
        "period_type": fact.period_type,
        "currency": fact.currency,
        "unit": fact.unit,
        "raw_value": fact.raw_value,
        "raw_label": fact.raw_label,
        "claim_tag": fact.claim_tag,
        "extraction_method": fact.extraction_method,
        "mapping_version": fact.mapping_version,
        "review_status": fact.review_status,
    }


def _from_row(row: dict[str, str], receipts: dict[str, SnapshotReceipt]) -> ProvenancedFact:
    fact = RawFact(
        fact_id=row["fact_id"],
        source_id=row["source_id"],
        snapshot_id=row["snapshot_id"],
        version_id=row["version_id"],
        economic_scope_id=row["economic_scope_id"],
        accounting_scope=row["accounting_scope"],
        economic_legal_scope_bridge_id=row["economic_legal_scope_bridge_id"],
        legal_entity_id=row["legal_entity_id"],
        instrument_id=row["instrument_id"],
        segment_id=row["segment_id"],
        raw_account_id=row["raw_account_id"],
        metric_id=row["metric_id"],
        period_start=date.fromisoformat(row["period_start"]),
        period_end=date.fromisoformat(row["period_end"]),
        period_type=row["period_type"],
        currency=row["currency"],
        unit=row["unit"],
        raw_value=row["raw_value"],
        raw_label=row["raw_label"],
        claim_tag=row["claim_tag"],
        extraction_method=row["extraction_method"],
        mapping_version=row["mapping_version"],
        review_status=row["review_status"],
    )
    fact.validate()
    receipt = receipts.get(fact.snapshot_id)
    if receipt is None:
        raise ValueError(f"raw fact {fact.fact_id} references unknown snapshot_id")
    if fact.source_id != receipt.source_id:
        raise ValueError(f"raw fact {fact.fact_id} source_id does not match snapshot")
    expected = _as_row(fact, receipt)
    for name in ("content_sha256", "first_public_at", "retrieved_at"):
        if row[name] != expected[name]:
            raise ValueError(f"raw fact {fact.fact_id} has conflicting {name} lineage")
    return ProvenancedFact(fact, receipt)


def _grain(fact: RawFact) -> tuple[str, ...]:
    return (
        fact.source_id,
        fact.economic_scope_id,
        fact.accounting_scope,
        fact.economic_legal_scope_bridge_id,
        fact.legal_entity_id,
        fact.instrument_id,
        fact.segment_id,
        fact.raw_account_id,
        fact.metric_id,
        fact.period_start.isoformat(),
        fact.period_end.isoformat(),
        fact.period_type,
        fact.currency,
        fact.unit,
    )


def load_provenanced_facts(evidence_dir: Path) -> tuple[ProvenancedFact, ...]:
    path = evidence_dir / "raw_facts.csv"
    if not path.exists():
        return ()
    receipts = {record.snapshot_id: record for record in load_source_ledger(evidence_dir)}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not set(FACT_FIELDS).issubset(reader.fieldnames):
            raise ValueError("raw_facts.csv is missing required columns")
        facts = tuple(_from_row(row, receipts) for row in reader)
    ids = [entry.fact.fact_id for entry in facts]
    if len(ids) != len(set(ids)):
        raise ValueError("raw_facts.csv contains duplicate fact_id")
    keys = [(entry.fact.snapshot_id, _grain(entry.fact)) for entry in facts]
    if len(keys) != len(set(keys)):
        raise ValueError("raw_facts.csv contains duplicate grain within one snapshot")
    return facts


def append_raw_facts(evidence_dir: Path, facts: Iterable[RawFact]) -> int:
    """Append validated source facts; identical fact IDs are idempotent."""

    with _exclusive_writer(evidence_dir):
        return _append_raw_facts_locked(evidence_dir, facts)


def _append_raw_facts_locked(evidence_dir: Path, facts: Iterable[RawFact]) -> int:
    candidates = tuple(facts)
    receipts = {record.snapshot_id: record for record in load_source_ledger(evidence_dir)}
    existing = load_provenanced_facts(evidence_dir)
    by_id = {entry.fact.fact_id: entry for entry in existing}
    grains = {(entry.fact.snapshot_id, _grain(entry.fact)) for entry in existing}
    additions: list[ProvenancedFact] = []
    for fact in candidates:
        fact.validate()
        receipt = receipts.get(fact.snapshot_id)
        if receipt is None:
            raise ValueError(f"raw fact {fact.fact_id} references unknown snapshot_id")
        if fact.source_id != receipt.source_id:
            raise ValueError(f"raw fact {fact.fact_id} source_id does not match snapshot")
        if not receipt.metadata.transformation_right:
            raise ValueError(f"raw fact {fact.fact_id} has no confirmed transformation right")
        prior = by_id.get(fact.fact_id)
        if prior is not None:
            if prior.fact != fact:
                raise ValueError(f"immutable fact_id {fact.fact_id} already exists with different content")
            continue
        key = (fact.snapshot_id, _grain(fact))
        if key in grains:
            raise ValueError(f"duplicate raw fact grain in snapshot: {fact.snapshot_id}")
        entry = ProvenancedFact(fact, receipt)
        additions.append(entry)
        by_id[fact.fact_id] = entry
        grains.add(key)
    if not additions:
        return 0
    path = evidence_dir / "raw_facts.csv"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("x", encoding="utf-8", newline="") as handle:
            csv.writer(handle).writerow(FACT_FIELDS)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle))
    if not set(FACT_FIELDS).issubset(header):
        raise ValueError("raw_facts.csv is missing required columns")
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        for entry in additions:
            writer.writerow(_as_row(entry.fact, entry.receipt))
        handle.flush()
        os.fsync(handle.fileno())
    return len(additions)


def select_known_facts(
    facts: Iterable[ProvenancedFact], analysis_cutoff: datetime
) -> tuple[ProvenancedFact, ...]:
    """Keep all known vintages, including superseded ones, for an ex-ante view."""

    if analysis_cutoff.tzinfo is None or analysis_cutoff.utcoffset() is None:
        raise ValueError("analysis_cutoff must be timezone-aware")
    selected = (
        entry
        for entry in facts
        if entry.receipt.metadata.cutoff_eligible
        and known_at_cutoff(entry.first_public_at, analysis_cutoff)
    )
    return tuple(sorted(selected, key=lambda item: (item.fact.source_id, item.fact.fact_id)))


def select_latest_known_facts(
    facts: Iterable[ProvenancedFact], analysis_cutoff: datetime
) -> tuple[ProvenancedFact, ...]:
    """Select latest public vintage per source and grain, with ambiguity failure.

    This deliberately does not choose between independent source IDs. Such
    precedence requires an explicit mapping or review in financial_core.
    """

    selected: dict[tuple[str, ...], ProvenancedFact] = {}
    for entry in select_known_facts(facts, analysis_cutoff):
        key = _grain(entry.fact)
        previous = selected.get(key)
        if previous is None or entry.first_public_at > previous.first_public_at:
            selected[key] = entry
        elif entry.first_public_at == previous.first_public_at:
            same_claim = (
                entry.fact.raw_value == previous.fact.raw_value
                and entry.fact.version_id == previous.fact.version_id
                and entry.receipt.content_sha256 == previous.receipt.content_sha256
            )
            if not same_claim:
                raise ValueError(f"ambiguous same-time fact vintage for {key}")
            if entry.fact.snapshot_id < previous.fact.snapshot_id:
                selected[key] = entry
    return tuple(selected[key] for key in sorted(selected))
