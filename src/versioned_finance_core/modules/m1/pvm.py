"""Exact additive price, volume and mix bridges for comparable products."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ProductComparison:
    product_id: str
    plan_quantity: Decimal
    actual_quantity: Decimal
    plan_price: Decimal
    actual_price: Decimal

    def __post_init__(self) -> None:
        if not self.product_id.strip():
            raise ValueError("product_id is required")
        for name in ("plan_quantity", "actual_quantity", "plan_price", "actual_price"):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
                raise ValueError(f"{name} must be a nonnegative finite Decimal")


@dataclass(frozen=True, slots=True)
class PriceVolumeMixBridge:
    plan_revenue: Decimal
    actual_revenue: Decimal
    total_variance: Decimal
    price_effect: Decimal
    volume_effect: Decimal
    mix_effect: Decimal
    residual: Decimal


def price_volume_mix_bridge(rows: Iterable[ProductComparison]) -> PriceVolumeMixBridge:
    """Use P2's actual-volume price, prior-mix volume, and remaining mix convention.

    Every product must be present in both vintages with a comparable realized
    price and quantity. This pure calculation does not establish public-data
    eligibility; callers must verify source, scope, period and product definitions.
    """

    observations = tuple(rows)
    if not observations:
        raise ValueError("at least one comparable product is required")
    ids = [row.product_id for row in observations]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate product_id")
    plan_quantity = sum((row.plan_quantity for row in observations), Decimal(0))
    actual_quantity = sum((row.actual_quantity for row in observations), Decimal(0))
    if plan_quantity <= 0 or actual_quantity <= 0:
        raise ValueError("total plan and actual quantity must be positive")

    plan_revenue = sum(
        (row.plan_quantity * row.plan_price for row in observations), Decimal(0)
    )
    actual_revenue = sum(
        (row.actual_quantity * row.actual_price for row in observations), Decimal(0)
    )
    total_variance = actual_revenue - plan_revenue
    price_effect = sum(
        (
            row.actual_quantity * (row.actual_price - row.plan_price)
            for row in observations
        ),
        Decimal(0),
    )
    volume_effect = (actual_quantity - plan_quantity) * plan_revenue / plan_quantity
    # Algebraically this is Q1*sum((m1_i-m0_i)*p0_i). Subtraction from the
    # observed total avoids burying decimal division precision in a plug.
    mix_effect = total_variance - price_effect - volume_effect
    residual = total_variance - price_effect - volume_effect - mix_effect
    return PriceVolumeMixBridge(
        plan_revenue=plan_revenue,
        actual_revenue=actual_revenue,
        total_variance=total_variance,
        price_effect=price_effect,
        volume_effect=volume_effect,
        mix_effect=mix_effect,
        residual=residual,
    )
