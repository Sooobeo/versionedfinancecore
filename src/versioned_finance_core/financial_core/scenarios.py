"""Pure, version-pinned scenario driver paths with explicit absolute overrides."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from types import MappingProxyType

from versioned_finance_core.contracts.enums import ScenarioPurpose

# Scenario contract validation consistently reports invalid inputs as ValueError.


@dataclass(frozen=True, order=True, slots=True)
class DriverPeriodKey:
    driver_id: str
    period_start: date
    period_end: date
    unit: str

    def __post_init__(self) -> None:
        _nonempty(self.driver_id, "driver_id")
        _nonempty(self.unit, "unit")
        if not isinstance(self.period_start, date) or isinstance(self.period_start, datetime):
            raise ValueError("period_start must be a date")  # noqa: TRY004
        if not isinstance(self.period_end, date) or isinstance(self.period_end, datetime):
            raise ValueError("period_end must be a date")  # noqa: TRY004
        if self.period_start > self.period_end:
            raise ValueError("period_start must not be after period_end")


@dataclass(frozen=True, slots=True)
class ScenarioDriverOverride:
    scenario_id: str
    scenario_purpose: ScenarioPurpose
    version_id: str
    driver_id: str
    period_start: date
    period_end: date
    input_value: Decimal
    input_unit: str
    evidence_or_assumption_id: str
    mechanism: str
    dependency_group: str | None = None
    review_status: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "scenario_id",
            "version_id",
            "driver_id",
            "input_unit",
            "evidence_or_assumption_id",
            "mechanism",
        ):
            _nonempty(getattr(self, name), name)
        if not isinstance(self.scenario_purpose, ScenarioPurpose):
            raise ValueError("scenario_purpose must be a ScenarioPurpose")  # noqa: TRY004
        DriverPeriodKey(self.driver_id, self.period_start, self.period_end, self.input_unit)
        _finite_decimal(self.input_value, "input_value")

    @property
    def driver_period(self) -> DriverPeriodKey:
        return DriverPeriodKey(
            self.driver_id, self.period_start, self.period_end, self.input_unit
        )

    @classmethod
    def from_mapping(cls, row: Mapping[str, object]) -> ScenarioDriverOverride:
        """Parse one row of the case template's ``scenarios.csv`` contract."""

        purpose = ScenarioPurpose(_nonempty(row.get("scenario_purpose"), "scenario_purpose"))
        return cls(
            scenario_id=_nonempty(row.get("scenario_id"), "scenario_id"),
            scenario_purpose=purpose,
            version_id=_nonempty(row.get("version_id"), "version_id"),
            driver_id=_nonempty(row.get("driver_id"), "driver_id"),
            period_start=_date(row.get("period_start"), "period_start"),
            period_end=_date(row.get("period_end"), "period_end"),
            input_value=_parse_decimal(row.get("input_value")),
            input_unit=_nonempty(row.get("input_unit"), "input_unit"),
            evidence_or_assumption_id=_nonempty(
                row.get("evidence_or_assumption_id"), "evidence_or_assumption_id"
            ),
            mechanism=_nonempty(row.get("mechanism"), "mechanism"),
            dependency_group=_optional_text(row.get("dependency_group")),
            review_status=_optional_text(row.get("review_status")),
        )


@dataclass(frozen=True, slots=True)
class AppliedScenarioPath:
    baseline_version_id: str
    scenario_id: str
    scenario_version_id: str
    scenario_purpose: ScenarioPurpose
    values: Mapping[DriverPeriodKey, Decimal]
    overridden_keys: tuple[DriverPeriodKey, ...]


def parse_scenario_rows(rows: Iterable[Mapping[str, object]]) -> tuple[ScenarioDriverOverride, ...]:
    """Parse scenario rows and reject duplicate scenario/version/driver/period keys."""

    parsed: list[ScenarioDriverOverride] = []
    seen: set[tuple[str, str, str, date, date]] = set()
    for row in rows:
        override = ScenarioDriverOverride.from_mapping(row)
        key = (
            override.scenario_id,
            override.version_id,
            override.driver_id,
            override.period_start,
            override.period_end,
        )
        if key in seen:
            raise ValueError(f"Duplicate scenario driver period: {key}")
        seen.add(key)
        parsed.append(override)
    return tuple(parsed)


def apply_absolute_scenario_overrides(
    baseline: Mapping[DriverPeriodKey, Decimal],
    *,
    baseline_version_id: str,
    overrides: Iterable[ScenarioDriverOverride],
) -> AppliedScenarioPath:
    """Replace named baseline values with explicit scenario values, without arithmetic shocks.

    The baseline's driver-period-unit keys are fixed. Missing keys and mixed
    scenario versions are errors; the input baseline is never changed.
    """

    pinned_version = _nonempty(baseline_version_id, "baseline_version_id")
    values: dict[DriverPeriodKey, Decimal] = {}
    for key, value in baseline.items():
        if not isinstance(key, DriverPeriodKey):
            raise ValueError("baseline keys must be DriverPeriodKey values")  # noqa: TRY004
        values[key] = _finite_decimal(value, "baseline value")

    selected = tuple(overrides)
    if not selected:
        raise ValueError("At least one scenario override is required")

    scenario_id = selected[0].scenario_id
    scenario_version_id = selected[0].version_id
    purpose = selected[0].scenario_purpose
    seen: set[tuple[str, date, date]] = set()
    overridden_keys: list[DriverPeriodKey] = []
    for override in selected:
        if (
            override.scenario_id != scenario_id
            or override.version_id != scenario_version_id
            or override.scenario_purpose != purpose
        ):
            raise ValueError("Overrides must belong to one scenario ID, version and purpose")
        period_key = (override.driver_id, override.period_start, override.period_end)
        if period_key in seen:
            raise ValueError(f"Duplicate driver period override: {period_key}")
        seen.add(period_key)
        key = override.driver_period
        if key not in values:
            raise ValueError(f"No matching baseline driver-period-unit key: {key}")
        values[key] = _finite_decimal(override.input_value, "input_value")
        overridden_keys.append(key)

    return AppliedScenarioPath(
        baseline_version_id=pinned_version,
        scenario_id=scenario_id,
        scenario_version_id=scenario_version_id,
        scenario_purpose=purpose,
        values=MappingProxyType(values),
        overridden_keys=tuple(overridden_keys),
    )


def _nonempty(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _date(value: object, name: str) -> date:
    if isinstance(value, datetime):
        raise ValueError(f"{name} must be a date")  # noqa: TRY004
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO date") from exc


def _parse_decimal(value: object) -> Decimal:
    if isinstance(value, (bool, float)):
        raise ValueError("input_value must be an exact decimal, not a float")  # noqa: TRY004
    if isinstance(value, Decimal):
        return _finite_decimal(value, "input_value")
    if isinstance(value, int):
        return Decimal(value)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("input_value is required")
    try:
        return _finite_decimal(Decimal(value.strip()), "input_value")
    except InvalidOperation as exc:
        raise ValueError("input_value must be a decimal") from exc


def _finite_decimal(value: object, name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal")
    return value
