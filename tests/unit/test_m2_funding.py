"""Synthetic closing cash funding identity and fail-closed availability tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from versioned_finance_core.contracts import (
    AccountingScope,
    ClaimTag,
    GateStatus,
    KnowledgeState,
    NormalizedFact,
    Period,
    PublicationStatus,
    ScopeRef,
    SourceProvenance,
)
from versioned_finance_core.financial_core import (
    CashComponentInput,
    CashComponentRule,
    CashView,
    aggregate_cash_components,
)
from versioned_finance_core.modules.m2 import (
    ClosingCashKind,
    ClosingCashLine,
    ClosingCashSide,
    FundingAvailability,
    evaluate_funding_plan,
)

AT = date(2026, 1, 1)
PERIOD = Period(AT, AT, "INSTANT")
SCOPE = ScopeRef("synthetic_parent", AccountingScope.STANDALONE, None, "synthetic_co", None, None)


def _component(
    component_id: str,
    amount: Decimal | KnowledgeState,
    *,
    side: ClosingCashSide,
) -> CashComponentInput:
    row = {
        "cash_component_id": component_id,
        "metric_id": f"metric_{component_id}",
        "tax_basis": "CLOSING_CASH",
        "obligation_id": f"obligation_{component_id}" if side is ClosingCashSide.USE else "",
        "funding_source_id": f"funding_{component_id}" if side is ClosingCashSide.SOURCE else "",
        "included_in_fcff": "NO",
        "included_in_fcfe": "NO",
        "included_in_cfads": "NO",
        "included_in_debt_service": "NO",
        "included_in_liquidity": "NO",
        "included_in_sources_uses": "YES",
    }
    fact = NormalizedFact(
        fact_id=f"nf_{component_id}",
        source_fact_id=f"raw_{component_id}",
        provenance=SourceProvenance(
            source_id=f"source_{component_id}",
            snapshot_id=f"snapshot_{component_id}",
            content_sha256="a" * 64,
            first_public_at=datetime(2026, 1, 1, tzinfo=UTC),
            retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        case_id="synthetic_case",
        scope=SCOPE,
        metric_id=f"metric_{component_id}",
        period=PERIOD,
        currency="KRW",
        unit="KRW_million",
        value=amount,
        version_id="option_v1",
        publication_status=PublicationStatus.FILED,
        normalization_rule="synthetic fixture",
        mapping_version="mapping_v1",
        claim_tag=ClaimTag.DERIVED,
    )
    return CashComponentInput(CashComponentRule.from_mapping(row), fact)


def _line(
    component_id: str,
    amount: Decimal | KnowledgeState,
    side: ClosingCashSide,
    kind: ClosingCashKind,
    availability: FundingAvailability,
) -> ClosingCashLine:
    return ClosingCashLine(
        option_id="buy",
        event_date=AT,
        economic_event_id=f"event_{component_id}",
        side=side,
        kind=kind,
        availability=availability,
        component=_component(component_id, amount, side=side),
        classification_source_id=f"classification_{component_id}",
        availability_source_id=(f"availability_{component_id}"
                                if side is ClosingCashSide.SOURCE else ""),
    )


def _inputs() -> dict:
    lines = (
        _line("cash", Decimal(30), ClosingCashSide.SOURCE,
              ClosingCashKind.ACQUIRER_CASH, FundingAvailability.SETTLED_OR_ACCESSIBLE),
        _line("debt_committed", Decimal(50), ClosingCashSide.SOURCE,
              ClosingCashKind.DEBT_CASH_PROCEEDS, FundingAvailability.COMMITTED_DRAWABLE),
        _line("debt_uncommitted", Decimal(20), ClosingCashSide.SOURCE,
              ClosingCashKind.DEBT_CASH_PROCEEDS, FundingAvailability.UNCOMMITTED),
        _line("seller", Decimal(-90), ClosingCashSide.USE,
              ClosingCashKind.SELLER_CASH_PAYMENT, FundingAvailability.NOT_APPLICABLE),
        _line("fee", Decimal(-10), ClosingCashSide.USE,
              ClosingCashKind.TRANSACTION_CASH_FEE, FundingAvailability.NOT_APPLICABLE),
    )
    return {
        "option_id": "buy",
        "core_cash": aggregate_cash_components(
            (line.component for line in lines), case_id="synthetic_case", version_id="option_v1"
        ),
        "settlement_date": AT,
        "lines": lines,
    }


def test_nominal_sources_equal_uses_but_uncommitted_funding_leaves_gap() -> None:
    inputs = _inputs()
    result = evaluate_funding_plan(**inputs)
    assert result.planned_sources == Decimal(100)
    assert result.planned_uses == Decimal(100)
    assert result.sources_uses_residual == Decimal(0)
    assert result.core_reconciliation_residual == Decimal(0)
    assert result.settled_or_accessible_sources == Decimal(30)
    assert result.committed_drawable_sources == Decimal(50)
    assert result.uncommitted_sources == Decimal(20)
    assert result.confirmed_funding_gap == Decimal(20)
    assert result.status is GateStatus.WITHHELD
    assert result.core_output_id == inputs["core_cash"].output_id
    assert result.core_content_identity_status is GateStatus.PASS
    assert len(result.evidence_or_assumption_ids) == 13
    assert result.as_dict()["claim_tag"] == "D"

    reordered = evaluate_funding_plan(**{**inputs, "lines": reversed(inputs["lines"])})
    assert reordered.output_id == result.output_id


def test_drawable_committed_funding_closes_the_gap_but_not_m3_liquidity() -> None:
    inputs = _inputs()
    lines = tuple(
        replace(line, availability=FundingAvailability.COMMITTED_DRAWABLE)
        if line.component.rule.component_id == "debt_uncommitted" else line
        for line in inputs["lines"]
    )
    result = evaluate_funding_plan(**{**inputs, "lines": lines})
    assert result.committed_drawable_sources == Decimal(70)
    assert result.confirmed_funding_gap == Decimal(0)
    assert result.status is GateStatus.PASS


def test_conditional_funding_is_separate_and_unknown_amount_is_not_zero() -> None:
    inputs = _inputs()
    lines = tuple(
        replace(line, availability=FundingAvailability.COMMITTED_CONDITIONAL)
        if line.component.rule.component_id == "debt_uncommitted" else line
        for line in inputs["lines"]
    )
    conditional = evaluate_funding_plan(**{**inputs, "lines": lines})
    assert conditional.committed_conditional_sources == Decimal(20)
    assert conditional.confirmed_funding_gap == Decimal(20)
    assert conditional.status is GateStatus.WITHHELD

    missing = tuple(
        replace(line, component=replace(
            line.component,
            fact=replace(line.component.fact, value=KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA),
        )) if line.component.rule.component_id == "debt_committed" else line
        for line in inputs["lines"]
    )
    core = aggregate_cash_components(
        (line.component for line in missing), case_id="synthetic_case", version_id="option_v1"
    )
    unresolved = evaluate_funding_plan(**{**inputs, "core_cash": core, "lines": missing})
    assert unresolved.planned_sources is KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA
    assert unresolved.committed_drawable_sources is KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA
    assert unresolved.confirmed_funding_gap is KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA
    assert unresolved.status is GateStatus.WITHHELD


def test_unknown_availability_withholds_gap_even_when_nominal_cash_balances() -> None:
    inputs = _inputs()
    lines = tuple(
        replace(line, availability=FundingAvailability.UNKNOWN)
        if line.component.rule.component_id == "debt_uncommitted" else line
        for line in inputs["lines"]
    )
    result = evaluate_funding_plan(**{**inputs, "lines": lines})
    assert result.unknown_availability_sources == Decimal(20)
    assert result.confirmed_funding_gap is KnowledgeState.UNKNOWN
    assert result.status is GateStatus.WITHHELD


def test_core_signed_view_mismatch_is_reported_and_withheld() -> None:
    inputs = _inputs()
    core = inputs["core_cash"]
    views = tuple(
        replace(view, value=Decimal(1)) if view.view is CashView.SOURCES_USES else view
        for view in core.views
    )
    result = evaluate_funding_plan(**{**inputs, "core_cash": replace(core, views=views)})
    assert result.core_reconciliation_residual == Decimal(-1)
    assert result.status is GateStatus.WITHHELD


def test_canceling_component_tamper_cannot_pass_core_content_identity() -> None:
    inputs = _inputs()
    changed = []
    for line in inputs["lines"]:
        amount = line.component.fact.value
        if line.component.rule.component_id == "cash":
            amount = Decimal(31)
        if line.component.rule.component_id == "seller":
            amount = Decimal(-91)
        changed.append(replace(
            line, component=replace(line.component, fact=replace(line.component.fact, value=amount))
        ))
    result = evaluate_funding_plan(**{**inputs, "lines": changed})
    assert result.sources_uses_residual == 0
    assert result.core_reconciliation_residual == 0
    assert result.core_content_identity_status is GateStatus.WITHHELD
    assert result.recomputed_core_output_id != result.core_output_id
    assert result.status is GateStatus.WITHHELD


def test_complete_core_inputs_can_verify_identity_when_other_views_share_period() -> None:
    inputs = _inputs()
    extra = _component("other_cash", Decimal(7), side=ClosingCashSide.SOURCE)
    extra = replace(extra, rule=replace(
        extra.rule, included_in_sources_uses=False, included_in_liquidity=True
    ))
    all_components = tuple(line.component for line in inputs["lines"]) + (extra,)
    core = aggregate_cash_components(
        all_components, case_id="synthetic_case", version_id="option_v1"
    )
    unverified = evaluate_funding_plan(**{**inputs, "core_cash": core})
    assert unverified.core_content_identity_status is GateStatus.WITHHELD
    assert unverified.status is GateStatus.WITHHELD
    verified = evaluate_funding_plan(**{
        **inputs, "core_cash": core, "all_core_components": all_components,
    })
    assert verified.core_content_identity_status is GateStatus.PASS
    assert verified.recomputed_core_output_id == core.output_id
    assert verified.confirmed_funding_gap == Decimal(20)


def test_missing_nominal_source_is_numeric_gap_and_withheld_reconciliation() -> None:
    inputs = _inputs()
    lines = tuple(line for line in inputs["lines"]
                  if line.component.rule.component_id != "debt_uncommitted")
    core = aggregate_cash_components(
        (line.component for line in lines), case_id="synthetic_case", version_id="option_v1"
    )
    result = evaluate_funding_plan(**{**inputs, "core_cash": core, "lines": lines})
    assert result.sources_uses_residual == Decimal(-20)
    assert result.confirmed_funding_gap == Decimal(20)
    assert result.status is GateStatus.WITHHELD


def test_duplicate_component_or_economic_event_cannot_be_counted_twice() -> None:
    inputs = _inputs()
    with pytest.raises(ValueError, match="duplicate funding component"):
        evaluate_funding_plan(**{**inputs, "lines": (*inputs["lines"], inputs["lines"][0])})
    lines = list(inputs["lines"])
    lines[1] = replace(lines[1], economic_event_id=lines[0].economic_event_id)
    with pytest.raises(ValueError, match="economic event counted twice"):
        evaluate_funding_plan(**{**inputs, "lines": lines})


def test_option_version_scope_component_coverage_and_event_date_boundaries() -> None:
    inputs = _inputs()
    first = inputs["lines"][0]
    with pytest.raises(ValueError, match="option_id mismatch"):
        evaluate_funding_plan(**{**inputs, "lines": (replace(first, option_id="other"), *inputs["lines"][1:])})
    with pytest.raises(ValueError, match="event_date mismatch"):
        evaluate_funding_plan(**{**inputs, "lines": (replace(first, event_date=date(2026, 1, 2)), *inputs["lines"][1:])})
    with pytest.raises(ValueError, match="case/version mismatch"):
        changed = replace(first.component, fact=replace(first.component.fact, version_id="other"))
        evaluate_funding_plan(**{**inputs, "lines": (replace(first, component=changed), *inputs["lines"][1:])})
    with pytest.raises(ValueError, match="scope/period mismatch"):
        scope = replace(SCOPE, economic_scope_id="other")
        changed = replace(first.component, fact=replace(first.component.fact, scope=scope))
        evaluate_funding_plan(**{**inputs, "lines": (replace(first, component=changed), *inputs["lines"][1:])})
    with pytest.raises(ValueError, match="do not match pinned Core"):
        evaluate_funding_plan(**{**inputs, "lines": inputs["lines"][:-1]})
    with pytest.raises(ValueError, match="inside the pinned Core period"):
        evaluate_funding_plan(**{**inputs, "settlement_date": date(2026, 1, 2)})


def test_sign_kind_and_availability_validation() -> None:
    inputs = _inputs()
    first = inputs["lines"][0]
    with pytest.raises(ValueError, match="USE kind cannot"):
        evaluate_funding_plan(**{
            **inputs,
            "lines": (replace(first, kind=ClosingCashKind.SELLER_CASH_PAYMENT), *inputs["lines"][1:]),
        })
    with pytest.raises(ValueError, match="SOURCE requires"):
        evaluate_funding_plan(**{
            **inputs,
            "lines": (replace(first, availability=FundingAvailability.NOT_APPLICABLE), *inputs["lines"][1:]),
        })
    with pytest.raises(ValueError, match="nonnegative"):
        negative = replace(first.component, fact=replace(first.component.fact, value=Decimal(-30)))
        evaluate_funding_plan(**{
            **inputs,
            "lines": (replace(first, component=negative), *inputs["lines"][1:]),
        })
    with pytest.raises(ValueError, match="availability_source_id"):
        evaluate_funding_plan(**{
            **inputs,
            "lines": (replace(first, availability_source_id=""), *inputs["lines"][1:]),
        })
    with pytest.raises(ValueError, match="cannot enter enterprise FCFF"):
        component = replace(first.component, rule=replace(first.component.rule, included_in_fcff=True))
        evaluate_funding_plan(**{
            **inputs,
            "lines": (replace(first, component=component), *inputs["lines"][1:]),
        })
    with pytest.raises(ValueError, match="cannot be a new LIQUIDITY inflow"):
        component = replace(
            first.component, rule=replace(first.component.rule, included_in_liquidity=True)
        )
        evaluate_funding_plan(**{
            **inputs,
            "lines": (replace(first, component=component), *inputs["lines"][1:]),
        })


def test_large_and_small_cash_units_are_reconciled_exactly() -> None:
    amount = Decimal("1" + "0" * 39 + "1")
    lines = (
        _line("large_source", amount, ClosingCashSide.SOURCE,
              ClosingCashKind.ACQUIRER_CASH, FundingAvailability.SETTLED_OR_ACCESSIBLE),
        _line("large_use", amount.copy_negate(), ClosingCashSide.USE,
              ClosingCashKind.SELLER_CASH_PAYMENT, FundingAvailability.NOT_APPLICABLE),
    )
    core = aggregate_cash_components(
        (line.component for line in lines), case_id="synthetic_case", version_id="option_v1"
    )
    result = evaluate_funding_plan(option_id="buy", core_cash=core, settlement_date=AT, lines=lines)
    assert result.planned_sources == amount
    assert result.planned_uses == amount
    assert result.sources_uses_residual == 0
    assert result.confirmed_funding_gap == 0
