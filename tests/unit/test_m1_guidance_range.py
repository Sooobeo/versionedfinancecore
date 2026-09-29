"""Synthetic interval comparison; no issuer forecast is implied by this fixture."""

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from versioned_finance_core.contracts import ClaimTag, VersionType
from versioned_finance_core.modules.m1 import (
    ComparableMetric,
    PublicGuidanceRange,
    RangePosition,
    compare_actual_to_public_guidance_range,
)


def _guidance() -> PublicGuidanceRange:
    return PublicGuidanceRange(
        metric_id="synthetic_same_definition_growth",
        economic_scope_id="synthetic_consolidated",
        legal_entity_id=None,
        period_start=date(2026, 2, 1),
        period_end=date(2026, 4, 30),
        currency="USD",
        unit="percentage_points",
        version_id="public_guidance_v1",
        available_at=datetime(2026, 1, 20, tzinfo=UTC),
        lower_bound=Decimal("4.0"),
        upper_bound=Decimal("6.0"),
        source_id="synthetic_guidance_source",
    )


def _actual(value: str = "7.5") -> ComparableMetric:
    guidance = _guidance()
    return ComparableMetric(
        metric_id=guidance.metric_id,
        economic_scope_id=guidance.economic_scope_id,
        legal_entity_id=guidance.legal_entity_id,
        period_start=guidance.period_start,
        period_end=guidance.period_end,
        currency=guidance.currency,
        unit=guidance.unit,
        version_id="public_actual_v1",
        version_type=VersionType.PUBLIC_ACTUAL,
        available_at=datetime(2026, 5, 20, tzinfo=UTC),
        value=Decimal(value),
    )


def _compare(guidance: PublicGuidanceRange, actual: ComparableMetric):
    return compare_actual_to_public_guidance_range(
        guidance,
        actual,
        actual_source_id="synthetic_actual_source",
        comparison_basis_id="synthetic_exact_metric_definition_review",
        information_cutoff=datetime(2026, 5, 21, tzinfo=UTC),
    )


def test_above_within_and_below_keep_published_range() -> None:
    above = _compare(_guidance(), _actual("7.5"))
    assert above.position is RangePosition.ABOVE
    assert above.actual_minus_lower == Decimal("3.5")
    assert above.actual_minus_upper == Decimal("1.5")
    assert above.signed_deviation_from_range == above.unexplained_residual == Decimal("1.5")
    assert above.claim_tag is ClaimTag.DERIVED
    assert above.output_id.startswith("m1_guidance_range_")
    assert {key: above.as_dict()[key] for key in (
        "economic_scope_id", "legal_entity_id", "period_start", "period_end", "currency", "unit"
    )} == {
        "economic_scope_id": "synthetic_consolidated",
        "legal_entity_id": None,
        "period_start": "2026-02-01",
        "period_end": "2026-04-30",
        "currency": "USD",
        "unit": "percentage_points",
    }

    within = _compare(_guidance(), _actual("5.0"))
    assert within.position is RangePosition.WITHIN
    assert within.signed_deviation_from_range == 0
    assert within.actual_minus_lower == Decimal("1.0")
    assert within.actual_minus_upper == Decimal("-1.0")

    below = _compare(_guidance(), _actual("3.5"))
    assert below.position is RangePosition.BELOW
    assert below.signed_deviation_from_range == Decimal("-0.5")


def test_version_source_and_publication_cutoff_are_part_of_result_identity() -> None:
    original = _compare(_guidance(), _actual())
    assert original.output_id == _compare(_guidance(), _actual()).output_id
    assert original.output_id != _compare(
        replace(_guidance(), source_id="revised_guidance_source"), _actual()
    ).output_id
    with pytest.raises(ValueError, match="actual was unavailable"):
        compare_actual_to_public_guidance_range(
            _guidance(), _actual(),
            actual_source_id="actual_source", comparison_basis_id="exact_definition",
            information_cutoff=datetime(2026, 5, 19, tzinfo=UTC),
        )
    with pytest.raises(ValueError, match="before actual"):
        _compare(
            replace(_guidance(), available_at=datetime(2026, 5, 21, tzinfo=UTC)),
            _actual(),
        )


def test_mismatched_definition_and_invalid_bounds_fail_closed() -> None:
    with pytest.raises(ValueError, match="metric_id differ"):
        _compare(_guidance(), replace(_actual(), metric_id="adjusted_different_definition"))
    with pytest.raises(ValueError, match="unit differ"):
        _compare(_guidance(), replace(_actual(), unit="basis_points"))
    with pytest.raises(ValueError, match="lower_bound"):
        replace(_guidance(), lower_bound=Decimal(8))
    with pytest.raises(ValueError, match="PUBLIC_ACTUAL"):
        _compare(_guidance(), replace(_actual(), version_type=VersionType.ANALYST_FORECAST))
    with pytest.raises(ValueError, match="comparison_basis_id"):
        compare_actual_to_public_guidance_range(
            _guidance(), _actual(), actual_source_id="actual_source",
            comparison_basis_id="", information_cutoff=datetime(2026, 5, 21, tzinfo=UTC),
        )
