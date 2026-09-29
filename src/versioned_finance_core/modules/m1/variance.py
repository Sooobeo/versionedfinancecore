from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from versioned_finance_core.contracts.enums import VersionType
from versioned_finance_core.financial_core.identities import Number, _decimal


def variance_residual(total_variance: Number, driver_effects: Iterable[Number]) -> Decimal:
    """Unexplained variance after the declared driver effects."""

    explained = sum((_decimal(value) for value in driver_effects), Decimal(0))
    return _decimal(total_variance) - explained


@dataclass(frozen=True, slots=True)
class ComparableMetric:
    metric_id: str
    economic_scope_id: str
    legal_entity_id: str | None
    period_start: date
    period_end: date
    currency: str
    unit: str
    version_id: str
    version_type: VersionType
    available_at: datetime
    value: Decimal

    def __post_init__(self) -> None:
        for name in ("metric_id", "economic_scope_id", "currency", "unit", "version_id"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        if self.period_start > self.period_end:
            raise ValueError("period_start must not follow period_end")
        if self.available_at.tzinfo is None or self.available_at.utcoffset() is None:
            raise ValueError("available_at must include a UTC offset")
        if not isinstance(self.value, Decimal) or not self.value.is_finite():
            raise ValueError("value must be a finite Decimal")


@dataclass(frozen=True, slots=True)
class MetricVariance:
    baseline_version_id: str
    actual_version_id: str
    total_variance: Decimal
    driver_effects: tuple[tuple[str, Decimal], ...]
    residual: Decimal


def compare_actual_to_baseline(
    baseline: ComparableMetric,
    actual: ComparableMetric,
    *,
    information_cutoff: datetime,
    driver_effects: Mapping[str, Decimal],
) -> MetricVariance:
    """Compare a frozen pre-actual reference with a same-grain public actual."""

    if information_cutoff.tzinfo is None or information_cutoff.utcoffset() is None:
        raise ValueError("information_cutoff must include a UTC offset")
    if baseline.version_type not in (
        VersionType.ANALYST_PLAN,
        VersionType.ANALYST_FORECAST,
        VersionType.PUBLIC_TARGET_OR_GUIDANCE,
    ):
        raise ValueError("baseline must be a plan, forecast or public target")
    if actual.version_type is not VersionType.PUBLIC_ACTUAL:
        raise ValueError("actual must be PUBLIC_ACTUAL")
    if baseline.version_id == actual.version_id:
        raise ValueError("baseline and actual versions must differ")
    grain = (
        "metric_id", "economic_scope_id", "legal_entity_id", "period_start",
        "period_end", "currency", "unit",
    )
    for name in grain:
        if getattr(baseline, name) != getattr(actual, name):
            raise ValueError(f"baseline and actual {name} differ")
    if baseline.available_at >= actual.available_at:
        raise ValueError("baseline was not frozen before actual became public")
    if actual.available_at > information_cutoff:
        raise ValueError("actual was not public by information_cutoff")

    checked: list[tuple[str, Decimal]] = []
    for driver_id, effect in driver_effects.items():
        if not driver_id.strip():
            raise ValueError("driver_id is required")
        if not isinstance(effect, Decimal) or not effect.is_finite():
            raise ValueError(f"{driver_id} effect must be a finite Decimal")
        checked.append((driver_id, effect))
    total = actual.value - baseline.value
    return MetricVariance(
        baseline_version_id=baseline.version_id,
        actual_version_id=actual.version_id,
        total_variance=total,
        driver_effects=tuple(checked),
        residual=variance_residual(total, (effect for _, effect in checked)),
    )

