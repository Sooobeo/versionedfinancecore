"""Version-pinned, multi-period projection with input-vintage checks.

The model remains pure: it neither fetches evidence nor writes output files.
All material period drivers require a source or assumption identifier and a
time at which the input was available. The caller owns evidence review and
must not promote a synthetic path to a real-company conclusion.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import UTC, date, datetime, timedelta
from types import MappingProxyType

from versioned_finance_core.financial_core.linked_statements import (
    BalanceSheet,
    LinkedStatementResult,
    OperatingPeriodInputs,
    project_linked_statements,
)

MODEL_PATH_SCHEMA_VERSION = 1
DRIVER_FIELDS = frozenset(field.name for field in fields(OperatingPeriodInputs))


def _nonempty(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be an offset-aware datetime")
    return value


def _date(value: date, name: str) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TypeError(f"{name} must be a date")
    return value


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _decimal_record(record: object) -> dict[str, str]:
    return {field.name: str(getattr(record, field.name)) for field in fields(record)}


@dataclass(frozen=True, slots=True)
class ModelInputEvidence:
    source_or_assumption_id: str
    available_at: datetime

    def __post_init__(self) -> None:
        _nonempty(self.source_or_assumption_id, "source_or_assumption_id")
        _aware(self.available_at, "available_at")


@dataclass(frozen=True, slots=True)
class ModelPeriod:
    period_id: str
    period_start: date
    period_end: date
    inputs: OperatingPeriodInputs
    input_evidence: Mapping[str, ModelInputEvidence]

    def __post_init__(self) -> None:
        _nonempty(self.period_id, "period_id")
        _date(self.period_start, "period_start")
        _date(self.period_end, "period_end")
        if self.period_end < self.period_start:
            raise ValueError("period_end must not precede period_start")
        if not isinstance(self.inputs, OperatingPeriodInputs):
            raise TypeError("inputs must be OperatingPeriodInputs")
        if not isinstance(self.input_evidence, Mapping):
            raise TypeError("input_evidence must be a mapping")
        evidence = dict(self.input_evidence)
        missing = DRIVER_FIELDS - evidence.keys()
        extra = evidence.keys() - DRIVER_FIELDS
        if missing or extra:
            raise ValueError(
                f"input_evidence must match every driver field; "
                f"missing={sorted(missing)}, extra={sorted(extra)}"
            )
        for name, record in evidence.items():
            if not isinstance(record, ModelInputEvidence):
                raise TypeError(f"{name} evidence must be ModelInputEvidence")
        object.__setattr__(self, "input_evidence", MappingProxyType(evidence))


@dataclass(frozen=True, slots=True)
class ModelPathSpec:
    case_id: str
    version_id: str
    economic_scope_id: str
    legal_entity_id: str | None
    currency: str
    opening_balance_date: date
    opening: BalanceSheet
    opening_balance_evidence: ModelInputEvidence
    information_cutoff: datetime
    periods: tuple[ModelPeriod, ...]

    def __post_init__(self) -> None:
        for name in ("case_id", "version_id", "economic_scope_id", "currency"):
            _nonempty(getattr(self, name), name)
        if self.legal_entity_id is not None:
            _nonempty(self.legal_entity_id, "legal_entity_id")
        _date(self.opening_balance_date, "opening_balance_date")
        if not isinstance(self.opening, BalanceSheet):
            raise TypeError("opening must be BalanceSheet")
        if not isinstance(self.opening_balance_evidence, ModelInputEvidence):
            raise TypeError("opening_balance_evidence must be ModelInputEvidence")
        _aware(self.information_cutoff, "information_cutoff")
        if not isinstance(self.periods, tuple) or not self.periods:
            raise ValueError("periods must be a nonempty tuple")
        if any(not isinstance(period, ModelPeriod) for period in self.periods):
            raise ValueError("periods must contain only ModelPeriod")


@dataclass(frozen=True, slots=True)
class ModelPeriodResult:
    period_id: str
    period_start: date
    period_end: date
    result: LinkedStatementResult


@dataclass(frozen=True, slots=True)
class ModelPathResult:
    case_id: str
    version_id: str
    economic_scope_id: str
    legal_entity_id: str | None
    currency: str
    information_cutoff: datetime
    periods: tuple[ModelPeriodResult, ...]
    content_sha256: str

    @property
    def closing(self) -> BalanceSheet:
        return self.periods[-1].result.closing


def project_model_path(spec: ModelPathSpec) -> ModelPathResult:
    """Project contiguous periods and hash input lineage plus calculated output."""

    if spec.opening_balance_evidence.available_at > spec.information_cutoff:
        raise ValueError("opening balance evidence was unavailable at information_cutoff")
    opening = spec.opening
    expected_start = spec.opening_balance_date + timedelta(days=1)
    seen_period_ids: set[str] = set()
    projected: list[ModelPeriodResult] = []

    for period in spec.periods:
        if period.period_id in seen_period_ids:
            raise ValueError(f"duplicate period_id: {period.period_id}")
        seen_period_ids.add(period.period_id)
        if period.period_start != expected_start:
            raise ValueError(
                f"period {period.period_id} is not contiguous with opening or prior period"
            )
        late = sorted(
            name for name, evidence in period.input_evidence.items()
            if evidence.available_at > spec.information_cutoff
        )
        if late:
            raise ValueError(
                f"period {period.period_id} input unavailable at information_cutoff: {late}"
            )
        result = project_linked_statements(opening, period.inputs)
        if result.balance_residual or result.cash_residual or result.debt_residual:
            raise ValueError(f"period {period.period_id} financial identities do not reconcile")
        projected.append(
            ModelPeriodResult(period.period_id, period.period_start, period.period_end, result)
        )
        opening = result.closing
        expected_start = period.period_end + timedelta(days=1)

    payload = {
        "schema_version": MODEL_PATH_SCHEMA_VERSION,
        "case_id": spec.case_id,
        "version_id": spec.version_id,
        "economic_scope_id": spec.economic_scope_id,
        "legal_entity_id": spec.legal_entity_id,
        "currency": spec.currency,
        "opening_balance_date": spec.opening_balance_date.isoformat(),
        "opening": _decimal_record(spec.opening),
        "opening_balance_evidence": {
            "source_or_assumption_id": spec.opening_balance_evidence.source_or_assumption_id,
            "available_at": _utc(spec.opening_balance_evidence.available_at),
        },
        "information_cutoff": _utc(spec.information_cutoff),
        "periods": [
            {
                "period_id": period.period_id,
                "period_start": period.period_start.isoformat(),
                "period_end": period.period_end.isoformat(),
                "inputs": _decimal_record(period.inputs),
                "input_evidence": {
                    name: {
                        "source_or_assumption_id": period.input_evidence[name].source_or_assumption_id,
                        "available_at": _utc(period.input_evidence[name].available_at),
                    }
                    for name in sorted(DRIVER_FIELDS)
                },
                "income": _decimal_record(output.result.income),
                "cash_flow": _decimal_record(output.result.cash_flow),
                "closing": _decimal_record(output.result.closing),
                "balance_residual": str(output.result.balance_residual),
                "cash_residual": str(output.result.cash_residual),
                "debt_residual": str(output.result.debt_residual),
            }
            for period, output in zip(spec.periods, projected, strict=True)
        ],
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return ModelPathResult(
        case_id=spec.case_id,
        version_id=spec.version_id,
        economic_scope_id=spec.economic_scope_id,
        legal_entity_id=spec.legal_entity_id,
        currency=spec.currency,
        information_cutoff=spec.information_cutoff,
        periods=tuple(projected),
        content_sha256=hashlib.sha256(encoded).hexdigest(),
    )
