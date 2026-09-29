"""Append-only provenance for public or synthetic source receipts.

This module performs local I/O only. It never fetches a source, decides whether
its licence is valid, or treats a later retrieval time as its publication time.
"""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path

from versioned_finance_core.contracts.enums import AccessClass, PublicationStatus
from versioned_finance_core.evidence.hashing import sha256_file

SOURCE_FIELDS = (
    "source_id",
    "snapshot_id",
    "access_class",
    "authority",
    "title",
    "url",
    "document_id",
    "event_at",
    "first_public_at",
    "retrieved_at",
    "publication_status",
    "period_start",
    "period_end",
    "entity_scope",
    "currency",
    "unit",
    "retention_right",
    "transformation_right",
    "redistribution_right",
    "content_sha256",
    "cutoff_eligible",
    "notes",
)

_SOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@contextmanager
def _exclusive_writer(evidence_dir: Path):
    """Fail closed when another process is appending to this evidence directory."""

    evidence_dir.mkdir(parents=True, exist_ok=True)
    lock_path = evidence_dir / ".evidence_write.lock"
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError(f"evidence writer lock already exists: {lock_path}") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="ascii") as handle:
            handle.write(str(os.getpid()))
            handle.flush()
            os.fsync(handle.fileno())
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must include a UTC offset")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _optional_datetime(value: str) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    _utc_iso(parsed)
    return parsed


def _optional_date(value: str) -> date | None:
    return date.fromisoformat(value) if value else None


def _right(value: str) -> bool:
    if value not in {"YES", "NO"}:
        raise ValueError(f"right/eligibility must be YES or NO, got {value!r}")
    return value == "YES"


@dataclass(frozen=True)
class SourceMetadata:
    source_id: str
    access_class: AccessClass
    authority: str
    title: str
    url: str
    document_id: str
    retrieved_at: datetime
    publication_status: PublicationStatus
    first_public_at: datetime | None = None
    event_at: datetime | None = None
    period_start: date | None = None
    period_end: date | None = None
    entity_scope: str = ""
    currency: str = ""
    unit: str = ""
    retention_right: bool = False
    transformation_right: bool = False
    redistribution_right: bool = False
    cutoff_eligible: bool = False
    notes: str = ""

    def validate(self) -> None:
        if not _SOURCE_ID.fullmatch(self.source_id):
            raise ValueError("source_id must be a safe, nonempty file identifier")
        if not self.authority or not self.title or not (self.url or self.document_id):
            raise ValueError("authority, title and URL or document_id are required")
        _utc_iso(self.retrieved_at)
        if self.first_public_at is not None:
            _utc_iso(self.first_public_at)
            if self.first_public_at > self.retrieved_at:
                raise ValueError("first_public_at cannot be later than retrieved_at")
        elif self.cutoff_eligible:
            raise ValueError("cutoff_eligible requires a known first_public_at")
        if self.event_at is not None:
            _utc_iso(self.event_at)
        if (self.period_start is None) != (self.period_end is None):
            raise ValueError("period_start and period_end must be supplied together")
        if self.period_start and self.period_end and self.period_start > self.period_end:
            raise ValueError("period_start must not follow period_end")
        if self.access_class == AccessClass.INTERNAL_OR_CONFIDENTIAL:
            raise ValueError("internal or confidential material is prohibited")


@dataclass(frozen=True)
class SnapshotReceipt:
    """One immutable retrieval, distinct from the deduplicated content object."""

    metadata: SourceMetadata
    snapshot_id: str
    content_sha256: str

    @property
    def source_id(self) -> str:
        return self.metadata.source_id

    @property
    def first_public_at(self) -> datetime | None:
        return self.metadata.first_public_at

    @property
    def retrieved_at(self) -> datetime:
        return self.metadata.retrieved_at


def receipt_id(source_id: str, retrieved_at: datetime, content_sha256: str) -> str:
    """Hash the receipt identity with canonical UTC timestamp formatting."""

    if not _SOURCE_ID.fullmatch(source_id) or not _SHA256.fullmatch(content_sha256):
        raise ValueError("invalid source_id or content_sha256")
    identity = {
        "source_id": source_id,
        "retrieved_at": _utc_iso(retrieved_at),
        "content_sha256": content_sha256,
    }
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "snap_" + sha256(payload.encode("ascii")).hexdigest()


def content_path(evidence_dir: Path, receipt: SnapshotReceipt) -> Path:
    """Return the per-source content-addressed location (which may not exist)."""

    return evidence_dir / "raw_snapshots" / receipt.source_id / receipt.content_sha256


def _as_row(receipt: SnapshotReceipt) -> dict[str, str]:
    meta = receipt.metadata
    return {
        "source_id": meta.source_id,
        "snapshot_id": receipt.snapshot_id,
        "access_class": meta.access_class.value,
        "authority": meta.authority,
        "title": meta.title,
        "url": meta.url,
        "document_id": meta.document_id,
        "event_at": _utc_iso(meta.event_at) if meta.event_at else "",
        "first_public_at": _utc_iso(meta.first_public_at) if meta.first_public_at else "",
        "retrieved_at": _utc_iso(meta.retrieved_at),
        "publication_status": meta.publication_status.value,
        "period_start": meta.period_start.isoformat() if meta.period_start else "",
        "period_end": meta.period_end.isoformat() if meta.period_end else "",
        "entity_scope": meta.entity_scope,
        "currency": meta.currency,
        "unit": meta.unit,
        "retention_right": "YES" if meta.retention_right else "NO",
        "transformation_right": "YES" if meta.transformation_right else "NO",
        "redistribution_right": "YES" if meta.redistribution_right else "NO",
        "content_sha256": receipt.content_sha256,
        "cutoff_eligible": "YES" if meta.cutoff_eligible else "NO",
        "notes": meta.notes,
    }


def _from_row(row: dict[str, str]) -> SnapshotReceipt:
    retrieved_at = _optional_datetime(row["retrieved_at"])
    if retrieved_at is None:
        raise ValueError("source receipt is missing retrieved_at")
    meta = SourceMetadata(
        source_id=row["source_id"],
        access_class=AccessClass(row["access_class"]),
        authority=row["authority"],
        title=row["title"],
        url=row["url"],
        document_id=row["document_id"],
        event_at=_optional_datetime(row["event_at"]),
        first_public_at=_optional_datetime(row["first_public_at"]),
        retrieved_at=retrieved_at,
        publication_status=PublicationStatus(row["publication_status"]),
        period_start=_optional_date(row["period_start"]),
        period_end=_optional_date(row["period_end"]),
        entity_scope=row["entity_scope"],
        currency=row["currency"],
        unit=row["unit"],
        retention_right=_right(row["retention_right"]),
        transformation_right=_right(row["transformation_right"]),
        redistribution_right=_right(row["redistribution_right"]),
        cutoff_eligible=_right(row["cutoff_eligible"]),
        notes=row["notes"],
    )
    meta.validate()
    digest = row["content_sha256"]
    expected = receipt_id(meta.source_id, meta.retrieved_at, digest)
    if row["snapshot_id"] != expected:
        raise ValueError(f"snapshot_id does not match receipt identity: {row['snapshot_id']}")
    return SnapshotReceipt(meta, expected, digest)


def load_source_ledger(evidence_dir: Path) -> tuple[SnapshotReceipt, ...]:
    path = evidence_dir / "source_ledger.csv"
    if not path.exists():
        return ()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not set(SOURCE_FIELDS).issubset(reader.fieldnames):
            raise ValueError("source_ledger.csv is missing required columns")
        rows = tuple(_from_row(row) for row in reader)
    ids = [row.snapshot_id for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("source_ledger.csv contains duplicate snapshot_id")
    return rows


def _append_receipt(evidence_dir: Path, receipt: SnapshotReceipt) -> SnapshotReceipt:
    with _exclusive_writer(evidence_dir):
        return _append_receipt_locked(evidence_dir, receipt)


def _append_receipt_locked(evidence_dir: Path, receipt: SnapshotReceipt) -> SnapshotReceipt:
    path = evidence_dir / "source_ledger.csv"
    existing = load_source_ledger(evidence_dir)
    for prior in existing:
        if prior.snapshot_id == receipt.snapshot_id:
            if _as_row(prior) != _as_row(receipt):
                raise ValueError("immutable snapshot_id already exists with different metadata")
            return prior
    evidence_dir.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("x", encoding="utf-8", newline="") as handle:
            csv.writer(handle).writerow(SOURCE_FIELDS)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle))
    if not set(SOURCE_FIELDS).issubset(header):
        raise ValueError("source_ledger.csv is missing required columns")
    with path.open("a", encoding="utf-8", newline="") as handle:
        csv.DictWriter(handle, fieldnames=header).writerow(_as_row(receipt))
        handle.flush()
        os.fsync(handle.fileno())
    return receipt


def register_source_locator(
    evidence_dir: Path, metadata: SourceMetadata, content_sha256: str
) -> SnapshotReceipt:
    """Record a source whose bytes cannot be stored in this repository.

    The caller must obtain and verify the digest under the source's terms.
    No snapshot bytes are copied, and downstream consumers can see that the
    content object is absent.
    """

    metadata.validate()
    snapshot = SnapshotReceipt(
        metadata, receipt_id(metadata.source_id, metadata.retrieved_at, content_sha256), content_sha256
    )
    return _append_receipt(evidence_dir, snapshot)


def verify_snapshot_content(evidence_dir: Path, receipt: SnapshotReceipt) -> bool:
    """Verify locally retained bytes; return False for a locator-only receipt."""

    path = content_path(evidence_dir, receipt)
    if not path.exists():
        return False
    if sha256_file(path) != receipt.content_sha256:
        raise ValueError(f"snapshot content hash mismatch: {receipt.snapshot_id}")
    return True


def ingest_snapshot(
    evidence_dir: Path, source_file: Path, metadata: SourceMetadata
) -> SnapshotReceipt:
    """Store source bytes once and append a receipt, without overwriting either."""

    metadata.validate()
    if not (metadata.retention_right and metadata.redistribution_right):
        raise ValueError("raw snapshot requires confirmed retention and redistribution rights")
    if not source_file.is_file() or source_file.is_symlink():
        raise ValueError("source_file must be an existing regular file, not a symlink")
    digest = sha256_file(source_file)
    receipt = SnapshotReceipt(
        metadata, receipt_id(metadata.source_id, metadata.retrieved_at, digest), digest
    )
    with _exclusive_writer(evidence_dir):
        return _ingest_snapshot_locked(evidence_dir, source_file, receipt)


def _ingest_snapshot_locked(
    evidence_dir: Path, source_file: Path, receipt: SnapshotReceipt
) -> SnapshotReceipt:
    digest = receipt.content_sha256
    destination = content_path(evidence_dir, receipt)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if sha256_file(destination) != digest:
            raise ValueError("existing content object hash does not match its name")
    else:
        created = False
        try:
            with destination.open("xb") as target:
                created = True
                with source_file.open("rb") as source:
                    shutil.copyfileobj(source, target)
                    target.flush()
                    os.fsync(target.fileno())
            if sha256_file(destination) != digest:
                raise ValueError("source file changed while copying")
        except Exception:
            if created:
                destination.unlink(missing_ok=True)
            raise
    return _append_receipt_locked(evidence_dir, receipt)
