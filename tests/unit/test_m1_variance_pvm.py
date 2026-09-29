from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from versioned_finance_core.contracts.enums import VersionType
from versioned_finance_core.modules.m1.pvm import (
    ProductComparison,
    price_volume_mix_bridge,
)
from versioned_finance_core.modules.m1.variance import (
    ComparableMetric,
    compare_actual_to_baseline,
)


def d(value: str | int) -> Decimal:
    return Decimal(value)


def test_multi_product_pvm_exact_known_answer_with_mix() -> None:
    result = price_volume_mix_bridge(
        (
            ProductComparison("A", d(10), d(15), d(10), d(11)),
            ProductComparison("B", d(10), d(10), d(20), d(22)),
        )
    )
    assert result.plan_revenue == d(300)
    assert result.actual_revenue == d(385)
    assert result.price_effect == d(35)
    assert result.volume_effect == d(75)
    assert result.mix_effect == d(-25)
    assert result.total_variance == d(85)
    assert result.residual == d(0)


def test_pvm_rejects_undefined_mix_and_duplicate_or_inexact_products() -> None:
    with pytest.raises(ValueError, match="quantity must be positive"):
        price_volume_mix_bridge((ProductComparison("A", d(0), d(1), d(10), d(11)),))
    row = ProductComparison("A", d(10), d(12), d(10), d(11))
    with pytest.raises(ValueError, match="duplicate product_id"):
        price_volume_mix_bridge((row, row))
    with pytest.raises(ValueError, match="actual_price"):
        ProductComparison("A", d(10), d(12), d(10), 11.0)  # type: ignore[arg-type]


KST = timezone(timedelta(hours=9))


def metric(version_type: VersionType, version_id: str, available_day: int, value: int) -> ComparableMetric:
    return ComparableMetric(
        metric_id="revenue",
        economic_scope_id="synthetic_group",
        legal_entity_id=None,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 6, 30),
        currency="KRW",
        unit="KRW",
        version_id=version_id,
        version_type=version_type,
        available_at=datetime(2026, 8, available_day, 12, tzinfo=KST),
        value=d(value),
    )


def test_variance_preserves_driver_effect_and_unexplained_residual() -> None:
    baseline = metric(VersionType.ANALYST_FORECAST, "forecast_v1", 10, 300)
    actual = metric(VersionType.PUBLIC_ACTUAL, "actual_v1", 14, 385)
    result = compare_actual_to_baseline(
        baseline,
        actual,
        information_cutoff=datetime(2026, 8, 18, 23, tzinfo=KST),
        driver_effects={"price": d(35), "volume": d(75), "mix": d(-25), "other": d(4)},
    )
    assert result.total_variance == d(85)
    assert result.residual == d(-4)
    assert result.total_variance == sum((v for _, v in result.driver_effects), d(0)) + result.residual
    assert result.baseline_version_id == "forecast_v1"
    assert result.actual_version_id == "actual_v1"


def test_variance_blocks_lookahead_and_incompatible_grain() -> None:
    baseline = metric(VersionType.ANALYST_PLAN, "plan_v1", 10, 300)
    actual = metric(VersionType.PUBLIC_ACTUAL, "actual_v1", 14, 385)
    with pytest.raises(ValueError, match="not frozen before"):
        compare_actual_to_baseline(
            replace(baseline, available_at=actual.available_at),
            actual,
            information_cutoff=datetime(2026, 8, 18, tzinfo=KST),
            driver_effects={},
        )
    with pytest.raises(ValueError, match="not public by"):
        compare_actual_to_baseline(
            baseline,
            actual,
            information_cutoff=datetime(2026, 8, 13, tzinfo=KST),
            driver_effects={},
        )
    with pytest.raises(ValueError, match="currency differ"):
        compare_actual_to_baseline(
            baseline,
            replace(actual, currency="USD"),
            information_cutoff=datetime(2026, 8, 18, tzinfo=KST),
            driver_effects={},
        )
