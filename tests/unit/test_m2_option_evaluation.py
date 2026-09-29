"""Synthetic known answers and fail-closed boundaries for the M2 decision layer."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from versioned_finance_core.contracts import (
    AccountingScope,
    GateStatus,
    KnowledgeState,
    Period,
    ScopeRef,
)
from versioned_finance_core.financial_core import CashInclusionResult, CashView, CashViewTotal
from versioned_finance_core.modules.m2 import (
    CashWorld,
    DecisionReview,
    EffectCategory,
    EffectTrace,
    OptionCashPeriod,
    ReviewDisposition,
    ReviewTopic,
    evaluate_incremental_option,
)

AS_OF = date(2026, 1, 1)
UPFRONT = Period(AS_OF, AS_OF, "INSTANT")
FUTURE = Period(date(2026, 1, 2), date(2027, 1, 1), "YEAR")
SCOPE = ScopeRef("synthetic_parent", AccountingScope.STANDALONE, None, "synthetic_co", None, None)


def _core(
    world: CashWorld,
    period: Period,
    value: Decimal | KnowledgeState,
    *,
    component_id: str | None = None,
) -> CashInclusionResult:
    component = component_id or f"{world.value.lower()}_{period.end.isoformat()}"
    return CashInclusionResult(
        output_id=f"core_{component}_{value}",
        case_id="synthetic_case",
        scope=SCOPE,
        version_id="baseline_v1" if world is CashWorld.STATUS_QUO else "option_v1",
        period=period,
        currency="KRW",
        unit="KRW_million",
        views=(CashViewTotal(
            CashView.FCFF,
            value,
            (component,),
            (f"normalized_{component}",),
            (value,) if isinstance(value, KnowledgeState) else (),
        ),),
    )


def _pair(
    period: Period,
    status_quo: Decimal | KnowledgeState,
    option: Decimal | KnowledgeState,
    factor: str,
) -> OptionCashPeriod:
    return OptionCashPeriod(
        _core(CashWorld.STATUS_QUO, period, status_quo),
        _core(CashWorld.OPTION, period, option),
        Decimal(factor),
        f"assumption_discount_{period.end.isoformat()}",
    )


def _effects(periods: tuple[OptionCashPeriod, ...]) -> tuple[EffectTrace, ...]:
    return tuple(
        EffectTrace(
            world=world,
            period=pair.status_quo.period,
            component_id=core.total_for(CashView.FCFF).component_ids[0],
            economic_effect_id=f"{world.value}_{pair.status_quo.period.end}",
            category=EffectCategory.CAPEX if pair.status_quo.period == UPFRONT else EffectCategory.OPERATING,
            source_or_assumption_id=f"source_{world.value}_{pair.status_quo.period.end}",
        )
        for pair in periods
        for world, core in (
            (CashWorld.STATUS_QUO, pair.status_quo),
            (CashWorld.OPTION, pair.option),
        )
    )


def _reviews() -> tuple[DecisionReview, ...]:
    return tuple(
        DecisionReview(topic, ReviewDisposition.COMPLETE, f"review_evidence_{topic.value}")
        for topic in ReviewTopic
    )


def _inputs() -> dict:
    periods = (
        _pair(UPFRONT, Decimal(0), Decimal(-100), "1"),
        _pair(FUTURE, Decimal(0), Decimal(120), "0.9"),
    )
    return {
        "case_id": "synthetic_case",
        "option_id": "build",
        "baseline_version_id": "baseline_v1",
        "as_of_date": AS_OF,
        "periods": periods,
        "effects": _effects(periods),
        "reviews": _reviews(),
    }


def test_known_answer_option_minus_status_quo_npv_and_switching_cost() -> None:
    inputs = _inputs()
    result = evaluate_incremental_option(**inputs)
    assert result.status is GateStatus.PASS
    assert [period.incremental_fcff for period in result.periods] == [Decimal(-100), Decimal(120)]
    assert [period.present_value for period in result.periods] == [Decimal(-100), Decimal("108.0")]
    assert result.npv == Decimal("8.0")
    assert result.upfront_cost_switching_value == Decimal("8.0")
    assert result.npv - result.upfront_cost_switching_value == 0
    assert len(result.effect_source_ids) == 4
    assert len(result.review_source_ids) == len(ReviewTopic)
    assert result.as_dict()["cash_basis"] == "after_tax_enterprise_FCFF"

    reordered = evaluate_incremental_option(**{
        **inputs,
        "periods": tuple(reversed(inputs["periods"])),
        "effects": tuple(reversed(inputs["effects"])),
        "reviews": tuple(reversed(inputs["reviews"])),
    })
    assert reordered.output_id == result.output_id


def test_positive_baseline_is_subtracted_and_negative_npv_is_not_clipped() -> None:
    inputs = _inputs()
    changed = (
        _pair(UPFRONT, Decimal(20), Decimal(-100), "1"),
        _pair(FUTURE, Decimal(40), Decimal(120), "0.9"),
    )
    result = evaluate_incremental_option(**{
        **inputs, "periods": changed, "effects": _effects(changed),
    })
    assert result.npv == Decimal("-48.0")
    assert result.upfront_cost_switching_value == Decimal("-48.0")


def test_missing_cash_never_becomes_zero_and_unresolved_review_withholds_npv() -> None:
    inputs = _inputs()
    missing = (
        inputs["periods"][0],
        _pair(FUTURE, KnowledgeState.UNKNOWN, Decimal(120), "0.9"),
    )
    result = evaluate_incremental_option(**{
        **inputs, "periods": missing, "effects": _effects(missing),
    })
    assert result.periods[1].incremental_fcff is KnowledgeState.UNKNOWN
    assert result.npv is KnowledgeState.UNKNOWN
    assert result.upfront_cost_switching_value is KnowledgeState.UNKNOWN
    assert result.status is GateStatus.WITHHELD

    reviews = list(inputs["reviews"])
    reviews[0] = replace(reviews[0], disposition=ReviewDisposition.UNRESOLVED)
    withheld = evaluate_incremental_option(**{**inputs, "reviews": reviews})
    assert withheld.npv is KnowledgeState.WITHHELD
    assert withheld.status is GateStatus.WITHHELD
    assert withheld.unresolved_reviews == (reviews[0].topic,)


def test_sunk_cost_and_financing_cannot_enter_fcff() -> None:
    inputs = _inputs()
    effects = list(inputs["effects"])
    for category in (EffectCategory.SUNK_COST, EffectCategory.FINANCING):
        effects[1] = replace(effects[1], category=category)
        with pytest.raises(ValueError, match="cannot enter enterprise FCFF"):
            evaluate_incremental_option(**{**inputs, "effects": effects})


def test_effect_coverage_and_economic_identity_detect_double_count() -> None:
    inputs = _inputs()
    with pytest.raises(ValueError, match="coverage mismatch"):
        evaluate_incremental_option(**{**inputs, "effects": inputs["effects"][:-1]})

    pair = inputs["periods"][0]
    duplicated_option = replace(pair.option, views=(CashViewTotal(
        CashView.FCFF, Decimal(-100), ("option_first", "option_second"),
        ("nf_one", "nf_two"), (),
    ),))
    periods = (replace(pair, option=duplicated_option), inputs["periods"][1])
    effects = tuple(effect for effect in _effects(periods)
                    if not (effect.world is CashWorld.OPTION and effect.period == UPFRONT)) + (
        EffectTrace(CashWorld.OPTION, UPFRONT, "option_first", "same_effect", EffectCategory.CAPEX, "a"),
        EffectTrace(CashWorld.OPTION, UPFRONT, "option_second", "same_effect", EffectCategory.CAPEX, "b"),
    )
    with pytest.raises(ValueError, match="counted twice"):
        evaluate_incremental_option(**{**inputs, "periods": periods, "effects": effects})


@pytest.mark.parametrize(
    ("change", "error", "match"),
    [
        ({"case_id": "different"}, ValueError, "case_id mismatch"),
        ({"baseline_version_id": "restated"}, ValueError, "version mismatch"),
        ({"as_of_date": date(2027, 2, 1)}, ValueError, "precedes the valuation date"),
        ({"as_of_date": "2026-01-01"}, TypeError, "as_of_date must be a date"),
        ({"periods": ()}, ValueError, "at least one"),
    ],
)
def test_case_version_date_and_empty_boundaries(change: dict, error: type, match: str) -> None:
    with pytest.raises(error, match=match):
        evaluate_incremental_option(**{**_inputs(), **change})


def test_discount_factor_and_world_alignment_are_strict() -> None:
    inputs = _inputs()
    pair = inputs["periods"][0]
    for factor, match in (
        (0.9, "finite Decimal"),
        (Decimal("NaN"), "finite Decimal"),
        (Decimal(0), "positive"),
        (Decimal("0.9"), "must be one"),
    ):
        with pytest.raises(ValueError, match=match):
            evaluate_incremental_option(**{
                **inputs, "periods": (replace(pair, discount_factor=factor), inputs["periods"][1]),
            })
    with pytest.raises(ValueError, match="periods must align"):
        evaluate_incremental_option(**{
            **inputs,
            "periods": (replace(pair, option=replace(pair.option, period=FUTURE)), inputs["periods"][1]),
        })
    with pytest.raises(ValueError, match="currency/unit mismatch"):
        evaluate_incremental_option(**{
            **inputs,
            "periods": (replace(pair, option=replace(pair.option, currency="USD")), inputs["periods"][1]),
        })


def test_review_completeness_and_source_ids_are_required() -> None:
    inputs = _inputs()
    with pytest.raises(ValueError, match="missing decision reviews"):
        evaluate_incremental_option(**{**inputs, "reviews": inputs["reviews"][:-1]})
    with pytest.raises(ValueError, match="after-tax review cannot"):
        reviews = tuple(
            replace(review, disposition=ReviewDisposition.NOT_APPLICABLE)
            if review.topic is ReviewTopic.AFTER_TAX_BASIS else review
            for review in inputs["reviews"]
        )
        evaluate_incremental_option(**{**inputs, "reviews": reviews})
    with pytest.raises(ValueError, match="review evidence_or_assumption_id"):
        reviews = (replace(inputs["reviews"][0], evidence_or_assumption_id=""),) + inputs["reviews"][1:]
        evaluate_incremental_option(**{**inputs, "reviews": reviews})
    with pytest.raises(ValueError, match="effect source_or_assumption_id"):
        effects = (replace(inputs["effects"][0], source_or_assumption_id=""),) + inputs["effects"][1:]
        evaluate_incremental_option(**{**inputs, "effects": effects})


def test_output_identity_changes_with_core_or_review_provenance() -> None:
    inputs = _inputs()
    first = evaluate_incremental_option(**inputs)
    pair = inputs["periods"][1]
    changed_core = replace(pair.option, output_id="core_revised_source_hash")
    changed_periods = (inputs["periods"][0], replace(pair, option=changed_core))
    assert evaluate_incremental_option(**{**inputs, "periods": changed_periods}).output_id != first.output_id
    reviews = (replace(inputs["reviews"][0], evidence_or_assumption_id="revised_evidence"),) + inputs["reviews"][1:]
    assert evaluate_incremental_option(**{**inputs, "reviews": reviews}).output_id != first.output_id


def test_large_and_small_decimal_amounts_are_not_rounded_internally() -> None:
    inputs = _inputs()
    large = Decimal("1" + "0" * 39)
    one_more = Decimal("1" + "0" * 38 + "1")
    periods = (
        _pair(UPFRONT, large, one_more, "1"),
        _pair(FUTURE, Decimal(0), Decimal("0.0000000001"), "0.1"),
    )
    result = evaluate_incremental_option(**{
        **inputs, "periods": periods, "effects": _effects(periods),
    })
    assert result.periods[0].incremental_fcff == Decimal(1)
    assert result.periods[1].present_value == Decimal("0.00000000001")
    assert result.npv == Decimal("1.00000000001")


def test_not_applicable_review_cannot_contradict_an_included_effect() -> None:
    inputs = _inputs()
    reviews = tuple(
        replace(review, disposition=ReviewDisposition.NOT_APPLICABLE)
        if review.topic is ReviewTopic.CAPEX else review
        for review in inputs["reviews"]
    )
    with pytest.raises(ValueError, match="review contradicts"):
        evaluate_incremental_option(**{**inputs, "reviews": reviews})
