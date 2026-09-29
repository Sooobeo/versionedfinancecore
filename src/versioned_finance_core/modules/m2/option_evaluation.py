"""M2 enterprise option valuation from immutable financial-core cash outputs.

This is an incremental decision layer. It never builds a baseline, estimates
cash taxes, or chooses a discount rate. The case must supply already-computed
after-tax FCFF for both worlds and explicit, sourced discount factors.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from versioned_finance_core.contracts import (
    ClaimTag,
    GateStatus,
    KnowledgeState,
    Period,
    ScopeRef,
)
from versioned_finance_core.financial_core import CashInclusionResult, CashView
from versioned_finance_core.modules.m2.incremental_cashflow import (
    _exact_product,
    _exact_sum,
    incremental_cash_flow,
)


class CashWorld(StrEnum):
    STATUS_QUO = "STATUS_QUO"
    OPTION = "OPTION"


class EffectCategory(StrEnum):
    OPERATING = "OPERATING"
    OPPORTUNITY_COST = "OPPORTUNITY_COST"
    CANNIBALIZATION = "CANNIBALIZATION"
    SYNERGY = "SYNERGY"
    WORKING_CAPITAL = "WORKING_CAPITAL"
    CAPEX = "CAPEX"
    CASH_TAX = "CASH_TAX"
    IMPLEMENTATION = "IMPLEMENTATION"
    DISPOSAL = "DISPOSAL"
    OTHER = "OTHER"
    SUNK_COST = "SUNK_COST"
    FINANCING = "FINANCING"


class ReviewTopic(StrEnum):
    AFTER_TAX_BASIS = "AFTER_TAX_BASIS"
    SUNK_COST = "SUNK_COST"
    OPPORTUNITY_COST = "OPPORTUNITY_COST"
    CANNIBALIZATION = "CANNIBALIZATION"
    WORKING_CAPITAL = "WORKING_CAPITAL"
    CAPEX = "CAPEX"
    FINANCING_DOUBLE_COUNT = "FINANCING_DOUBLE_COUNT"


class ReviewDisposition(StrEnum):
    COMPLETE = "COMPLETE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class OptionCashPeriod:
    """One aligned status-quo/option pair and its sourced discount factor."""

    status_quo: CashInclusionResult
    option: CashInclusionResult
    discount_factor: Decimal
    discount_factor_source_id: str


@dataclass(frozen=True, slots=True)
class EffectTrace:
    """Economic identity for an included FCFF component in one world/period."""

    world: CashWorld
    period: Period
    component_id: str
    economic_effect_id: str
    category: EffectCategory
    source_or_assumption_id: str


@dataclass(frozen=True, slots=True)
class DecisionReview:
    """Case review of a material inclusion/exclusion question."""

    topic: ReviewTopic
    disposition: ReviewDisposition
    evidence_or_assumption_id: str


@dataclass(frozen=True, slots=True)
class IncrementalPeriod:
    period: Period
    status_quo_output_id: str
    option_output_id: str
    status_quo_fcff: Decimal | KnowledgeState
    option_fcff: Decimal | KnowledgeState
    incremental_fcff: Decimal | KnowledgeState
    discount_factor: Decimal
    discount_factor_source_id: str
    present_value: Decimal | KnowledgeState

    def as_dict(self) -> dict[str, object]:
        return {
            "period": self.period.key(),
            "status_quo_output_id": self.status_quo_output_id,
            "option_output_id": self.option_output_id,
            "status_quo_fcff": _value_text(self.status_quo_fcff),
            "option_fcff": _value_text(self.option_fcff),
            "incremental_fcff": _value_text(self.incremental_fcff),
            "discount_factor": str(self.discount_factor),
            "discount_factor_source_id": self.discount_factor_source_id,
            "present_value": _value_text(self.present_value),
        }


@dataclass(frozen=True, slots=True)
class OptionValuation:
    output_id: str
    case_id: str
    option_id: str
    baseline_version_id: str
    option_version_id: str
    as_of_date: date
    scope: ScopeRef
    currency: str
    unit: str
    periods: tuple[IncrementalPeriod, ...]
    npv: Decimal | KnowledgeState
    upfront_cost_switching_value: Decimal | KnowledgeState
    status: GateStatus
    unresolved_reviews: tuple[ReviewTopic, ...]
    effect_source_ids: tuple[str, ...]
    review_source_ids: tuple[str, ...]
    claim_tag: ClaimTag = ClaimTag.DERIVED

    def as_dict(self) -> dict[str, object]:
        return {
            "output_id": self.output_id,
            "case_id": self.case_id,
            "option_id": self.option_id,
            "baseline_version_id": self.baseline_version_id,
            "option_version_id": self.option_version_id,
            "as_of_date": self.as_of_date.isoformat(),
            "scope": self.scope.key(),
            "currency": self.currency,
            "unit": self.unit,
            "claim_tag": self.claim_tag.value,
            "cash_basis": "after_tax_enterprise_FCFF",
            "periods": [period.as_dict() for period in self.periods],
            "npv": _value_text(self.npv),
            "upfront_cost_switching_value": _value_text(self.upfront_cost_switching_value),
            "status": self.status.value,
            "unresolved_reviews": [topic.value for topic in self.unresolved_reviews],
            "effect_source_ids": list(self.effect_source_ids),
            "review_source_ids": list(self.review_source_ids),
        }


def _required(value: str, field: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field} is required without surrounding whitespace")


def _finite(value: Decimal, field: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{field} must be a finite Decimal")


def _amount(value: Decimal | KnowledgeState, field: str) -> None:
    if isinstance(value, KnowledgeState):
        if value is KnowledgeState.KNOWN:
            raise ValueError(f"{field} KNOWN requires a Decimal amount")
    else:
        _finite(value, field)


def _value_text(value: Decimal | KnowledgeState) -> str:
    return value.value if isinstance(value, KnowledgeState) else str(value)


def _unresolved_amount(*values: Decimal | KnowledgeState) -> KnowledgeState:
    states = {value for value in values if isinstance(value, KnowledgeState)}
    if len(states) == 1:
        return next(iter(states))
    return KnowledgeState.UNKNOWN


def _validate_review(reviews: tuple[DecisionReview, ...]) -> dict[ReviewTopic, DecisionReview]:
    by_topic: dict[ReviewTopic, DecisionReview] = {}
    for review in reviews:
        if not isinstance(review.topic, ReviewTopic):
            raise TypeError("review topic is invalid")
        if not isinstance(review.disposition, ReviewDisposition):
            raise TypeError("review disposition is invalid")
        _required(review.evidence_or_assumption_id, "review evidence_or_assumption_id")
        if review.topic in by_topic:
            raise ValueError(f"duplicate decision review: {review.topic.value}")
        if (
            review.topic is ReviewTopic.AFTER_TAX_BASIS
            and review.disposition is ReviewDisposition.NOT_APPLICABLE
        ):
            raise ValueError("after-tax review cannot be NOT_APPLICABLE for FCFF")
        by_topic[review.topic] = review
    if set(by_topic) != set(ReviewTopic):
        missing = sorted(topic.value for topic in set(ReviewTopic) - set(by_topic))
        raise ValueError(f"missing decision reviews: {missing}")
    return by_topic


def _period_key(world: CashWorld, period: Period, component_id: str) -> tuple[object, ...]:
    return (world, *period.key(), component_id)


def _validate_effects(
    effects: tuple[EffectTrace, ...],
    expected: set[tuple[object, ...]],
    reviews: dict[ReviewTopic, DecisionReview],
) -> None:
    actual: set[tuple[object, ...]] = set()
    economic_ids: set[tuple[object, ...]] = set()
    for effect in effects:
        if not isinstance(effect.world, CashWorld) or not isinstance(effect.category, EffectCategory):
            raise TypeError("effect world and category must use their enums")
        if not isinstance(effect.period, Period):
            raise TypeError("effect period must be a Period")
        _required(effect.component_id, "effect component_id")
        _required(effect.economic_effect_id, "economic_effect_id")
        _required(effect.source_or_assumption_id, "effect source_or_assumption_id")
        if effect.category in {EffectCategory.SUNK_COST, EffectCategory.FINANCING}:
            raise ValueError(f"{effect.category.value} cannot enter enterprise FCFF")
        topic = {
            EffectCategory.OPPORTUNITY_COST: ReviewTopic.OPPORTUNITY_COST,
            EffectCategory.CANNIBALIZATION: ReviewTopic.CANNIBALIZATION,
            EffectCategory.WORKING_CAPITAL: ReviewTopic.WORKING_CAPITAL,
            EffectCategory.CAPEX: ReviewTopic.CAPEX,
        }.get(effect.category)
        if topic and reviews[topic].disposition is ReviewDisposition.NOT_APPLICABLE:
            raise ValueError(f"{topic.value} review contradicts an included cash effect")
        key = _period_key(effect.world, effect.period, effect.component_id)
        if key in actual:
            raise ValueError(f"duplicate effect trace: {key}")
        actual.add(key)
        identity = (effect.world, *effect.period.key(), effect.economic_effect_id)
        if identity in economic_ids:
            raise ValueError(f"economic effect counted twice: {identity}")
        economic_ids.add(identity)
    if actual != expected:
        raise ValueError(f"effect trace coverage mismatch: missing={expected - actual}, extra={actual - expected}")


def evaluate_incremental_option(
    *,
    case_id: str,
    option_id: str,
    baseline_version_id: str,
    as_of_date: date,
    periods: Iterable[OptionCashPeriod],
    effects: Iterable[EffectTrace],
    reviews: Iterable[DecisionReview],
) -> OptionValuation:
    """Value an option relative to a pinned status quo, with fail-closed review.

    ``upfront_cost_switching_value`` is the *additional* upfront cash outlay
    that would reduce the current NPV to zero, at DF=1 on ``as_of_date``.
    A negative value is the upfront cost reduction needed to reach zero.
    It is not an absolute acquisition price or an approval recommendation.
    """

    for field, value in (
        ("case_id", case_id), ("option_id", option_id),
        ("baseline_version_id", baseline_version_id),
    ):
        _required(value, field)
    if not isinstance(as_of_date, date) or isinstance(as_of_date, datetime):
        raise TypeError("as_of_date must be a date")
    selected = tuple(periods)
    if not selected:
        raise ValueError("at least one option cash period is required")
    review_entries = tuple(reviews)
    reviewed = _validate_review(review_entries)
    effect_entries = tuple(effects)
    if not isinstance(selected[0].status_quo, CashInclusionResult) or not isinstance(
        selected[0].option, CashInclusionResult
    ):
        raise TypeError("both worlds must be financial-core CashInclusionResult values")
    first = selected[0].status_quo
    option_version_id = selected[0].option.version_id
    _required(option_version_id, "option version_id")
    expected_effects: set[tuple[object, ...]] = set()
    seen_periods: set[tuple[str, str, str]] = set()
    results: list[IncrementalPeriod] = []

    for pair in selected:
        status_quo, option = pair.status_quo, pair.option
        if not isinstance(status_quo, CashInclusionResult) or not isinstance(option, CashInclusionResult):
            raise TypeError("both worlds must be financial-core CashInclusionResult values")
        for world, result in ((CashWorld.STATUS_QUO, status_quo), (CashWorld.OPTION, option)):
            if result.case_id != case_id:
                raise ValueError("core case_id mismatch")
            if result.scope != first.scope:
                raise ValueError("core scope mismatch")
            if result.currency != first.currency or result.unit != first.unit:
                raise ValueError("core currency/unit mismatch")
            expected_version = baseline_version_id if world is CashWorld.STATUS_QUO else option_version_id
            if result.version_id != expected_version:
                raise ValueError(f"{world.value} version mismatch")
        if status_quo.period != option.period:
            raise ValueError("option and status-quo periods must align")
        period = status_quo.period
        if period.start < as_of_date:
            raise ValueError("cash period precedes the valuation date")
        if period.key() in seen_periods:
            raise ValueError(f"duplicate option cash period: {period.key()}")
        seen_periods.add(period.key())
        _finite(pair.discount_factor, "discount_factor")
        if pair.discount_factor <= 0:
            raise ValueError("discount_factor must be positive")
        if period.end == as_of_date and pair.discount_factor != Decimal(1):
            raise ValueError("discount factor at as_of_date must be one")
        _required(pair.discount_factor_source_id, "discount_factor_source_id")

        status_quo_fcff = status_quo.total_for(CashView.FCFF)
        option_fcff = option.total_for(CashView.FCFF)
        _amount(status_quo_fcff.value, "status-quo FCFF")
        _amount(option_fcff.value, "option FCFF")
        for world, view in ((CashWorld.STATUS_QUO, status_quo_fcff), (CashWorld.OPTION, option_fcff)):
            if len(view.component_ids) != len(set(view.component_ids)):
                raise ValueError(f"duplicate FCFF component in {world.value} world")
            for component_id in view.component_ids:
                expected_effects.add(_period_key(world, period, component_id))
        if isinstance(status_quo_fcff.value, Decimal) and isinstance(option_fcff.value, Decimal):
            incremental: Decimal | KnowledgeState = incremental_cash_flow(
                option_fcff.value, status_quo_fcff.value
            )
            present_value: Decimal | KnowledgeState = _exact_product(
                incremental, pair.discount_factor
            )
        else:
            incremental = _unresolved_amount(status_quo_fcff.value, option_fcff.value)
            present_value = incremental
        results.append(IncrementalPeriod(
            period=period,
            status_quo_output_id=status_quo.output_id,
            option_output_id=option.output_id,
            status_quo_fcff=status_quo_fcff.value,
            option_fcff=option_fcff.value,
            incremental_fcff=incremental,
            discount_factor=pair.discount_factor,
            discount_factor_source_id=pair.discount_factor_source_id,
            present_value=present_value,
        ))

    _validate_effects(effect_entries, expected_effects, reviewed)
    ordered = tuple(sorted(results, key=lambda item: item.period.key()))
    unresolved_reviews = tuple(sorted(
        (topic for topic, review in reviewed.items()
         if review.disposition is ReviewDisposition.UNRESOLVED),
        key=lambda topic: topic.value,
    ))
    unresolved_cash = tuple(
        result.present_value for result in ordered
        if isinstance(result.present_value, KnowledgeState)
    )
    if unresolved_reviews:
        npv: Decimal | KnowledgeState = KnowledgeState.WITHHELD
    elif unresolved_cash:
        npv = _unresolved_amount(*unresolved_cash)
    else:
        npv = _exact_sum(result.present_value for result in ordered)
    switching = npv  # A DF=1 increase in upfront outlay subtracts exactly this NPV.
    status = GateStatus.PASS if isinstance(npv, Decimal) else GateStatus.WITHHELD
    source_ids = tuple(sorted({effect.source_or_assumption_id for effect in effect_entries}))
    review_ids = tuple(sorted({review.evidence_or_assumption_id for review in review_entries}))
    identity = {
        "formula": "m2_incremental_fcff_npv_v1",
        "case_id": case_id,
        "option_id": option_id,
        "baseline_version_id": baseline_version_id,
        "option_version_id": option_version_id,
        "as_of_date": as_of_date.isoformat(),
        "scope": first.scope.key(),
        "currency": first.currency,
        "unit": first.unit,
        "periods": [period.as_dict() for period in ordered],
        "effects": sorted(
            (effect.world.value, *effect.period.key(), effect.component_id,
             effect.economic_effect_id, effect.category.value, effect.source_or_assumption_id)
            for effect in effect_entries
        ),
        "reviews": sorted(
            (review.topic.value, review.disposition.value, review.evidence_or_assumption_id)
            for review in review_entries
        ),
        "npv": _value_text(npv),
    }
    digest = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return OptionValuation(
        output_id=f"m2_option_{digest}",
        case_id=case_id,
        option_id=option_id,
        baseline_version_id=baseline_version_id,
        option_version_id=option_version_id,
        as_of_date=as_of_date,
        scope=first.scope,
        currency=first.currency,
        unit=first.unit,
        periods=ordered,
        npv=npv,
        upfront_cost_switching_value=switching,
        status=status,
        unresolved_reviews=unresolved_reviews,
        effect_source_ids=source_ids,
        review_source_ids=review_ids,
    )
