"""Small, strict records shared by evidence and the canonical financial core.

CSV is the exchange format. These records keep its temporal and scope meaning
explicit before a number enters a calculation.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from versioned_finance_core.contracts.enums import (
    AccountingScope,
    ClaimTag,
    KnowledgeState,
    PublicationStatus,
    VersionType,
)

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _required(row: Mapping[str, str], key: str) -> str:
    value = row.get(key, "").strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _optional(row: Mapping[str, str], key: str) -> str | None:
    return row.get(key, "").strip() or None


def _date(row: Mapping[str, str], key: str) -> date:
    return date.fromisoformat(_required(row, key))


def _optional_date(row: Mapping[str, str], key: str) -> date | None:
    value = _optional(row, key)
    return date.fromisoformat(value) if value else None


def _moment(row: Mapping[str, str], key: str) -> datetime:
    parsed = datetime.fromisoformat(_required(row, key))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{key} must include a UTC offset or Z")
    return parsed


def decimal_value(value: str | int | Decimal) -> Decimal | KnowledgeState:
    """Parse a measured decimal or an explicit missing-data state, never a float."""

    if isinstance(value, float):
        raise TypeError("binary float is not a canonical financial input")
    if isinstance(value, str):
        value = value.strip()
        if not value:
            raise ValueError("blank amount is not zero; use an explicit knowledge state")
        if value in KnowledgeState.__members__ and value != KnowledgeState.KNOWN:
            return KnowledgeState(value)
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid decimal value: {value}") from exc
    if not result.is_finite():
        raise ValueError("non-finite decimal values are not valid financial inputs")
    return result


@dataclass(frozen=True)
class ScopeRef:
    economic_scope_id: str
    accounting_scope: AccountingScope
    economic_legal_scope_bridge_id: str | None
    legal_entity_id: str | None
    instrument_id: str | None
    segment_id: str | None

    @classmethod
    def from_mapping(cls, row: Mapping[str, str]) -> ScopeRef:
        return cls(
            economic_scope_id=_required(row, "economic_scope_id"),
            accounting_scope=AccountingScope(_required(row, "accounting_scope")),
            economic_legal_scope_bridge_id=_optional(row, "economic_legal_scope_bridge_id"),
            legal_entity_id=_optional(row, "legal_entity_id"),
            instrument_id=_optional(row, "instrument_id"),
            segment_id=_optional(row, "segment_id"),
        )

    def key(self) -> tuple[str, ...]:
        return (
            self.economic_scope_id,
            self.accounting_scope.value,
            self.economic_legal_scope_bridge_id or "",
            self.legal_entity_id or "",
            self.instrument_id or "",
            self.segment_id or "",
        )


@dataclass(frozen=True)
class Period:
    start: date
    end: date
    period_type: str

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ValueError("period_start must not exceed period_end")
        if not self.period_type:
            raise ValueError("period_type is required")

    @classmethod
    def from_mapping(cls, row: Mapping[str, str]) -> Period:
        return cls(_date(row, "period_start"), _date(row, "period_end"),
                   _required(row, "period_type"))

    def key(self) -> tuple[str, str, str]:
        return (self.start.isoformat(), self.end.isoformat(), self.period_type)


@dataclass(frozen=True)
class SourceProvenance:
    source_id: str
    snapshot_id: str
    content_sha256: str
    first_public_at: datetime
    retrieved_at: datetime

    @classmethod
    def from_mapping(cls, row: Mapping[str, str]) -> SourceProvenance:
        content_hash = _required(row, "content_sha256")
        if not SHA256_PATTERN.fullmatch(content_hash):
            raise ValueError("content_sha256 must be a lowercase SHA-256 digest")
        result = cls(
            source_id=_required(row, "source_id"),
            snapshot_id=_required(row, "snapshot_id"),
            content_sha256=content_hash,
            first_public_at=_moment(row, "first_public_at"),
            retrieved_at=_moment(row, "retrieved_at"),
        )
        if result.first_public_at > result.retrieved_at:
            raise ValueError("retrieved_at precedes first_public_at")
        return result


@dataclass(frozen=True)
class ScopeBridge:
    bridge_id: str
    economic_scope_id: str
    legal_entity_id: str
    relation: str
    provenance: SourceProvenance
    review_status: str

    @classmethod
    def from_mapping(cls, row: Mapping[str, str]) -> ScopeBridge:
        return cls(
            bridge_id=_required(row, "bridge_id"),
            economic_scope_id=_required(row, "economic_scope_id"),
            legal_entity_id=_required(row, "legal_entity_id"),
            relation=_required(row, "relation"),
            provenance=SourceProvenance.from_mapping(row),
            review_status=_required(row, "review_status"),
        )


@dataclass(frozen=True)
class RawFact:
    fact_id: str
    provenance: SourceProvenance
    version_id: str
    scope: ScopeRef
    raw_account_id: str
    period: Period
    currency: str
    unit: str
    value: Decimal | KnowledgeState
    mapping_version: str
    claim_tag: ClaimTag

    @classmethod
    def from_mapping(cls, row: Mapping[str, str]) -> RawFact:
        tag = ClaimTag(_required(row, "claim_tag"))
        if tag is not ClaimTag.FACT:
            raise ValueError("raw facts must carry claim_tag F")
        return cls(
            fact_id=_required(row, "fact_id"),
            provenance=SourceProvenance.from_mapping(row),
            version_id=_required(row, "version_id"),
            scope=ScopeRef.from_mapping(row),
            raw_account_id=_required(row, "raw_account_id"),
            period=Period.from_mapping(row),
            currency=_required(row, "currency"),
            unit=_required(row, "unit"),
            value=decimal_value(_required(row, "raw_value")),
            mapping_version=_required(row, "mapping_version"),
            claim_tag=tag,
        )


@dataclass(frozen=True)
class MappingRule:
    mapping_id: str
    source_id: str
    raw_account_id: str
    normalized_metric_id: str
    effective_from: date | None
    effective_to: date | None
    sign_multiplier: Decimal
    review_status: str

    @classmethod
    def from_mapping(cls, row: Mapping[str, str]) -> MappingRule:
        multiplier = decimal_value(_required(row, "sign_multiplier"))
        if multiplier not in (Decimal(-1), Decimal(1)):
            raise ValueError("sign_multiplier must be +1 or -1")
        result = cls(
            mapping_id=_required(row, "mapping_id"),
            source_id=_required(row, "source_id"),
            raw_account_id=_required(row, "raw_account_id"),
            normalized_metric_id=_required(row, "normalized_metric_id"),
            effective_from=_optional_date(row, "effective_from"),
            effective_to=_optional_date(row, "effective_to"),
            sign_multiplier=multiplier,
            review_status=_required(row, "review_status"),
        )
        if result.effective_from and result.effective_to and result.effective_from > result.effective_to:
            raise ValueError("mapping effective_from exceeds effective_to")
        return result

    def applies_to(self, fact: RawFact) -> bool:
        end = fact.period.end
        return (
            self.mapping_id == fact.mapping_version
            and self.source_id == fact.provenance.source_id
            and self.raw_account_id == fact.raw_account_id
            and (self.effective_from is None or self.effective_from <= end)
            and (self.effective_to is None or end <= self.effective_to)
        )


@dataclass(frozen=True)
class MetricDefinition:
    metric_id: str
    grain: str
    period_type: str
    currency_policy: str
    unit: str
    sign_convention: str
    review_status: str

    @classmethod
    def from_mapping(cls, row: Mapping[str, str]) -> MetricDefinition:
        return cls(
            metric_id=_required(row, "metric_id"),
            grain=_required(row, "grain"),
            period_type=_required(row, "period_type"),
            currency_policy=_required(row, "currency_policy"),
            unit=_required(row, "unit"),
            sign_convention=_required(row, "sign_convention"),
            review_status=_required(row, "review_status"),
        )


@dataclass(frozen=True)
class FinancialVersion:
    version_id: str
    version_type: VersionType
    as_of_date: date
    publication_status: PublicationStatus
    supersedes_version_id: str | None
    information_cutoff: datetime
    immutable: bool

    @classmethod
    def from_mapping(cls, row: Mapping[str, str]) -> FinancialVersion:
        immutable = _required(row, "immutable").lower()
        if immutable not in {"true", "false"}:
            raise ValueError("immutable must be true or false")
        return cls(
            version_id=_required(row, "version_id"),
            version_type=VersionType(_required(row, "version_type")),
            as_of_date=_date(row, "as_of_date"),
            publication_status=PublicationStatus(_required(row, "publication_status")),
            supersedes_version_id=_optional(row, "supersedes_version_id"),
            information_cutoff=_moment(row, "information_cutoff"),
            immutable=immutable == "true",
        )


@dataclass(frozen=True)
class NormalizedFact:
    fact_id: str
    source_fact_id: str
    provenance: SourceProvenance
    case_id: str
    scope: ScopeRef
    metric_id: str
    period: Period
    currency: str
    unit: str
    value: Decimal | KnowledgeState
    version_id: str
    publication_status: PublicationStatus
    normalization_rule: str
    mapping_version: str
    claim_tag: ClaimTag

    def key(self) -> tuple[str, ...]:
        return (
            self.case_id,
            self.metric_id,
            *self.scope.key(),
            *self.period.key(),
            self.currency,
            self.unit,
            self.version_id,
        )

    def as_csv_row(self) -> dict[str, str]:
        return {
            "fact_id": self.fact_id,
            "source_fact_id": self.source_fact_id,
            "source_id": self.provenance.source_id,
            "snapshot_id": self.provenance.snapshot_id,
            "content_sha256": self.provenance.content_sha256,
            "first_public_at": self.provenance.first_public_at.isoformat(),
            "retrieved_at": self.provenance.retrieved_at.isoformat(),
            "case_id": self.case_id,
            "economic_scope_id": self.scope.economic_scope_id,
            "accounting_scope": self.scope.accounting_scope.value,
            "economic_legal_scope_bridge_id": self.scope.economic_legal_scope_bridge_id or "",
            "legal_entity_id": self.scope.legal_entity_id or "",
            "instrument_id": self.scope.instrument_id or "",
            "segment_id": self.scope.segment_id or "",
            "metric_id": self.metric_id,
            "period_start": self.period.start.isoformat(),
            "period_end": self.period.end.isoformat(),
            "period_type": self.period.period_type,
            "currency": self.currency,
            "unit": self.unit,
            "value": str(self.value.value if isinstance(self.value, KnowledgeState) else self.value),
            "version_id": self.version_id,
            "publication_status": self.publication_status.value,
            "normalization_rule": self.normalization_rule,
            "mapping_version": self.mapping_version,
            "claim_tag": self.claim_tag.value,
            "review_status": "PENDING_REVIEW",
        }
