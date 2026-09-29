"""Compare a public guidance interval with a later same-definition actual.

A range is never replaced with its midpoint. The signed deviation is zero
inside the interval, positive above its upper bound, and negative below its
lower bound. It is an outcome measure, not an attribution or forecast claim.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum

from versioned_finance_core.contracts import ClaimTag, VersionType
from versioned_finance_core.financial_core.identities import _exact_sum
from versioned_finance_core.modules.m1.variance import ComparableMetric


def _required(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{field} is required without surrounding whitespace")


def _aware(value: datetime, field: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be an offset-aware datetime")


def _finite(value: Decimal, field: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{field} must be a finite Decimal")


class RangePosition(StrEnum):
    BELOW = "BELOW"
    WITHIN = "WITHIN"
    ABOVE = "ABOVE"


@dataclass(frozen=True, slots=True)
class PublicGuidanceRange:
    metric_id: str
    economic_scope_id: str
    legal_entity_id: str | None
    period_start: date
    period_end: date
    currency: str
    unit: str
    version_id: str
    available_at: datetime
    lower_bound: Decimal
    upper_bound: Decimal
    source_id: str

    def __post_init__(self) -> None:
        for field in ("metric_id", "economic_scope_id", "currency", "unit", "version_id", "source_id"):
            _required(getattr(self, field), field)
        if self.legal_entity_id is not None:
            _required(self.legal_entity_id, "legal_entity_id")
        if self.period_start > self.period_end:
            raise ValueError("period_start must not follow period_end")
        _aware(self.available_at, "available_at")
        _finite(self.lower_bound, "lower_bound")
        _finite(self.upper_bound, "upper_bound")
        if self.lower_bound > self.upper_bound:
            raise ValueError("guidance lower_bound must not exceed upper_bound")


@dataclass(frozen=True, slots=True)
class GuidanceRangeComparison:
    output_id: str
    metric_id: str
    economic_scope_id: str
    legal_entity_id: str | None
    period_start: date
    period_end: date
    currency: str
    unit: str
    guidance_version_id: str
    actual_version_id: str
    guidance_source_id: str
    actual_source_id: str
    comparison_basis_id: str
    information_cutoff: datetime
    guidance_lower: Decimal
    guidance_upper: Decimal
    actual: Decimal
    position: RangePosition
    actual_minus_lower: Decimal
    actual_minus_upper: Decimal
    signed_deviation_from_range: Decimal
    unexplained_residual: Decimal
    claim_tag: ClaimTag = ClaimTag.DERIVED

    def as_dict(self) -> dict[str, str | None]:
        return {
            "output_id": self.output_id,
            "metric_id": self.metric_id,
            "economic_scope_id": self.economic_scope_id,
            "legal_entity_id": self.legal_entity_id,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "currency": self.currency,
            "unit": self.unit,
            "guidance_version_id": self.guidance_version_id,
            "actual_version_id": self.actual_version_id,
            "guidance_source_id": self.guidance_source_id,
            "actual_source_id": self.actual_source_id,
            "comparison_basis_id": self.comparison_basis_id,
            "information_cutoff": self.information_cutoff.astimezone(UTC).isoformat(),
            "guidance_lower": str(self.guidance_lower),
            "guidance_upper": str(self.guidance_upper),
            "actual": str(self.actual),
            "position": self.position.value,
            "actual_minus_lower": str(self.actual_minus_lower),
            "actual_minus_upper": str(self.actual_minus_upper),
            "signed_deviation_from_range": str(self.signed_deviation_from_range),
            "unexplained_residual": str(self.unexplained_residual),
            "claim_tag": self.claim_tag.value,
        }


def compare_actual_to_public_guidance_range(
    guidance: PublicGuidanceRange,
    actual: ComparableMetric,
    *,
    actual_source_id: str,
    comparison_basis_id: str,
    information_cutoff: datetime,
) -> GuidanceRangeComparison:
    """Measure the outcome versus the published bounds with no midpoint proxy."""

    if not isinstance(guidance, PublicGuidanceRange):
        raise TypeError("guidance must be PublicGuidanceRange")
    if not isinstance(actual, ComparableMetric):
        raise TypeError("actual must be ComparableMetric")
    _required(actual_source_id, "actual_source_id")
    _required(comparison_basis_id, "comparison_basis_id")
    _aware(information_cutoff, "information_cutoff")
    if actual.version_type is not VersionType.PUBLIC_ACTUAL:
        raise ValueError("actual must have PUBLIC_ACTUAL version type")
    if guidance.version_id == actual.version_id:
        raise ValueError("guidance and actual must have different versions")
    for field in (
        "metric_id", "economic_scope_id", "legal_entity_id", "period_start",
        "period_end", "currency", "unit",
    ):
        if getattr(guidance, field) != getattr(actual, field):
            raise ValueError(f"guidance and actual {field} differ")
    if guidance.available_at >= actual.available_at:
        raise ValueError("guidance was not public before actual")
    if actual.available_at > information_cutoff:
        raise ValueError("actual was unavailable at information_cutoff")
    lower_gap = _exact_sum((actual.value, guidance.lower_bound.copy_negate()))
    upper_gap = _exact_sum((actual.value, guidance.upper_bound.copy_negate()))
    if actual.value < guidance.lower_bound:
        position = RangePosition.BELOW
        deviation = lower_gap
    elif actual.value > guidance.upper_bound:
        position = RangePosition.ABOVE
        deviation = upper_gap
    else:
        position = RangePosition.WITHIN
        deviation = Decimal(0)
    identity = {
        "formula": "m1_public_guidance_range_v1",
        "grain": [
            guidance.metric_id, guidance.economic_scope_id, guidance.legal_entity_id,
            guidance.period_start.isoformat(), guidance.period_end.isoformat(),
            guidance.currency, guidance.unit,
        ],
        "guidance": [
            guidance.version_id, guidance.source_id,
            guidance.available_at.astimezone(UTC).isoformat(),
            str(guidance.lower_bound), str(guidance.upper_bound),
        ],
        "actual": [
            actual.version_id, actual_source_id,
            actual.available_at.astimezone(UTC).isoformat(), str(actual.value),
        ],
        "comparison_basis_id": comparison_basis_id,
        "information_cutoff": information_cutoff.astimezone(UTC).isoformat(),
        "position": position.value,
        "signed_deviation_from_range": str(deviation),
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return GuidanceRangeComparison(
        output_id=f"m1_guidance_range_{digest}",
        metric_id=guidance.metric_id,
        economic_scope_id=guidance.economic_scope_id,
        legal_entity_id=guidance.legal_entity_id,
        period_start=guidance.period_start,
        period_end=guidance.period_end,
        currency=guidance.currency,
        unit=guidance.unit,
        guidance_version_id=guidance.version_id,
        actual_version_id=actual.version_id,
        guidance_source_id=guidance.source_id,
        actual_source_id=actual_source_id,
        comparison_basis_id=comparison_basis_id,
        information_cutoff=information_cutoff,
        guidance_lower=guidance.lower_bound,
        guidance_upper=guidance.upper_bound,
        actual=actual.value,
        position=position,
        actual_minus_lower=lower_gap,
        actual_minus_upper=upper_gap,
        signed_deviation_from_range=deviation,
        unexplained_residual=deviation,
    )
