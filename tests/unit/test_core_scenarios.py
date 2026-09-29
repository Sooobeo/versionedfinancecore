import csv
from datetime import date
from decimal import Decimal
from io import StringIO

import pytest

from versioned_finance_core.contracts.enums import ScenarioPurpose
from versioned_finance_core.financial_core.scenarios import (
    DriverPeriodKey,
    apply_absolute_scenario_overrides,
    parse_scenario_rows,
)


def _row(**changes: object) -> dict[str, object]:
    row: dict[str, object] = {
        "scenario_id": "downside_1",
        "scenario_purpose": "EVIDENCE_DOWNSIDE",
        "version_id": "scenario_v1",
        "driver_id": "unit_price",
        "period_start": "2027-01-01",
        "period_end": "2027-12-31",
        "input_value": "12.50",
        "input_unit": "USD/unit",
        "evidence_or_assumption_id": "assumption_1",
        "mechanism": "Explicit absolute driver value",
        "dependency_group": "demand",
        "review_status": "SYNTHETIC_TEST",
    }
    row.update(changes)
    return row


def test_parse_csv_contract_and_apply_absolute_values_to_pinned_baseline() -> None:
    csv_text = StringIO(
        "scenario_id,scenario_purpose,version_id,driver_id,period_start,period_end,"
        "input_value,input_unit,evidence_or_assumption_id,mechanism,dependency_group,"
        "review_status\n"
        "downside_1,EVIDENCE_DOWNSIDE,scenario_v1,unit_price,2027-01-01,2027-12-31,"
        "12.50,USD/unit,assumption_1,Explicit absolute driver value,demand,SYNTHETIC_TEST\n"
    )
    overrides = parse_scenario_rows(csv.DictReader(csv_text))
    price = DriverPeriodKey("unit_price", date(2027, 1, 1), date(2027, 12, 31), "USD/unit")
    volume = DriverPeriodKey("volume", date(2027, 1, 1), date(2027, 12, 31), "units")
    baseline = {price: Decimal("15.00"), volume: Decimal(100)}

    result = apply_absolute_scenario_overrides(
        baseline, baseline_version_id="baseline_v3", overrides=overrides
    )

    assert overrides[0].input_value == Decimal("12.50")
    assert result.baseline_version_id == "baseline_v3"
    assert result.scenario_id == "downside_1"
    assert result.scenario_version_id == "scenario_v1"
    assert result.scenario_purpose == ScenarioPurpose.EVIDENCE_DOWNSIDE
    assert result.values == {price: Decimal("12.50"), volume: Decimal(100)}
    assert result.overridden_keys == (price,)
    assert baseline[price] == Decimal("15.00")
    with pytest.raises(TypeError):
        result.values[price] = Decimal(0)  # type: ignore[index]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"evidence_or_assumption_id": ""}, "evidence_or_assumption_id"),
        ({"input_value": 1.5}, "not a float"),
        ({"input_value": "NaN"}, "finite Decimal"),
        ({"period_end": "2026-12-31"}, "period_start must not"),
        ({"scenario_purpose": "UNKNOWN"}, "UNKNOWN"),
    ],
)
def test_parse_rejects_missing_evidence_inexact_value_and_invalid_period(
    change: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        parse_scenario_rows([_row(**change)])


def test_duplicate_scenario_version_driver_period_is_rejected_even_if_unit_differs() -> None:
    with pytest.raises(ValueError, match="Duplicate scenario driver period"):
        parse_scenario_rows([_row(), _row(input_unit="EUR/unit")])


def test_apply_rejects_unpinned_unit_or_period_and_mixed_scenario_versions() -> None:
    key = DriverPeriodKey("unit_price", date(2027, 1, 1), date(2027, 12, 31), "USD/unit")
    baseline = {key: Decimal("15.00")}
    wrong_unit = parse_scenario_rows([_row(input_unit="EUR/unit")])
    with pytest.raises(ValueError, match="No matching baseline driver-period-unit"):
        apply_absolute_scenario_overrides(
            baseline, baseline_version_id="baseline_v3", overrides=wrong_unit
        )

    other_version = parse_scenario_rows([_row(version_id="scenario_v2")])
    with pytest.raises(ValueError, match="one scenario ID, version and purpose"):
        apply_absolute_scenario_overrides(
            baseline,
            baseline_version_id="baseline_v3",
            overrides=(*parse_scenario_rows([_row()]), *other_version),
        )


def test_apply_rejects_float_baseline_and_empty_path() -> None:
    key = DriverPeriodKey("unit_price", date(2027, 1, 1), date(2027, 12, 31), "USD/unit")
    override = parse_scenario_rows([_row()])
    with pytest.raises(ValueError, match="finite Decimal"):
        apply_absolute_scenario_overrides(
            {key: 15.0},  # type: ignore[dict-item]
            baseline_version_id="baseline_v3",
            overrides=override,
        )
    with pytest.raises(ValueError, match="At least one scenario override"):
        apply_absolute_scenario_overrides(
            {key: Decimal(15)}, baseline_version_id="baseline_v3", overrides=[]
        )
