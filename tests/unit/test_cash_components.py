from __future__ import annotations

import csv
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from versioned_finance_core.contracts import (
    AccountingScope,
    ClaimTag,
    KnowledgeState,
    NormalizedFact,
    Period,
    PublicationStatus,
    ScopeRef,
    SourceProvenance,
)
from versioned_finance_core.financial_core.cash_components import (
    CashComponentInput,
    CashComponentRule,
    CashView,
    aggregate_cash_components,
)

TEMPLATE = Path(__file__).parents[2] / "cases" / "_template" / "02_financial_core"
_FLAGS = (
    "included_in_fcff",
    "included_in_fcfe",
    "included_in_cfads",
    "included_in_debt_service",
    "included_in_liquidity",
    "included_in_sources_uses",
)


def _fact(
    fact_id: str,
    metric_id: str,
    value: Decimal | KnowledgeState,
) -> NormalizedFact:
    return NormalizedFact(
        fact_id=fact_id,
        source_fact_id=f"raw_{fact_id}",
        provenance=SourceProvenance(
            source_id="synthetic_source",
            snapshot_id="synthetic_snapshot",
            content_sha256="a" * 64,
            first_public_at=datetime(2026, 1, 2, tzinfo=UTC),
            retrieved_at=datetime(2026, 1, 3, tzinfo=UTC),
        ),
        case_id="synthetic_case",
        scope=ScopeRef("synthetic_group", AccountingScope.CONSOLIDATED, None, None, None, None),
        metric_id=metric_id,
        period=Period(date(2025, 1, 1), date(2025, 12, 31), "FY"),
        currency="KRW",
        unit="KRW_million",
        value=value,
        version_id="filed_v1",
        publication_status=PublicationStatus.FILED,
        normalization_rule="synthetic rule",
        mapping_version="synthetic_mapping_v1",
        claim_tag=ClaimTag.DERIVED,
    )


def _rule(component_id: str, metric_id: str, **flags: str) -> CashComponentRule:
    row = {
        "cash_component_id": component_id,
        "display_name": f"Synthetic {component_id}",
        "metric_id": metric_id,
        "tax_basis": "POST_TAX",
        "obligation_id": "",
        "funding_source_id": "",
        "double_count_check": "synthetic fixture only",
        **{name: "NO" for name in _FLAGS},
        **flags,
    }
    return CashComponentRule.from_mapping(row)


def _aggregate(inputs: list[CashComponentInput]):
    return aggregate_cash_components(inputs, case_id="synthetic_case", version_id="filed_v1")


def test_template_flags_and_known_answer_reuse_one_signed_amount() -> None:
    with (TEMPLATE / "cash_components.csv").open(encoding="utf-8", newline="") as handle:
        header = next(csv.reader(handle))
    assert {"cash_component_id", "metric_id", "tax_basis", *_FLAGS}.issubset(header)

    operating = CashComponentInput(
        _rule(
            "operating",
            "operating_cash",
            included_in_fcff="YES",
            included_in_fcfe="YES",
            included_in_cfads="YES",
            included_in_liquidity="YES",
            included_in_sources_uses="YES",
        ),
        _fact("nf_operating", "operating_cash", Decimal(100)),
    )
    capex = CashComponentInput(
        _rule(
            "capex",
            "capex_cash",
            included_in_fcff="YES",
            included_in_fcfe="YES",
            included_in_liquidity="YES",
            included_in_sources_uses="YES",
        ),
        _fact("nf_capex", "capex_cash", Decimal(-30)),
    )
    debt = CashComponentInput(
        replace(
            _rule(
                "debt_service",
                "debt_cash",
                included_in_debt_service="YES",
                included_in_liquidity="YES",
                included_in_sources_uses="YES",
            ),
            obligation_id="synthetic_debt",
        ),
        _fact("nf_debt", "debt_cash", Decimal(-20)),
    )
    result = _aggregate([operating, capex, debt])
    assert result.total_for(CashView.FCFF).value == Decimal(70)
    assert result.total_for(CashView.FCFE).value == Decimal(70)
    assert result.total_for(CashView.CFADS).value == Decimal(100)
    assert result.total_for(CashView.DEBT_SERVICE).value == Decimal(-20)
    assert result.total_for(CashView.LIQUIDITY).value == Decimal(50)
    assert result.total_for(CashView.SOURCES_USES).value == Decimal(50)
    assert result.total_for(CashView.FCFF).component_ids == ("capex", "operating")
    assert result.output_id == _aggregate([debt, operating, capex]).output_id


def test_decimal_precision_and_excluded_view_is_not_zero() -> None:
    first = CashComponentInput(
        _rule("a", "metric_a", included_in_liquidity="YES"),
        _fact("nf_a", "metric_a", Decimal("0.1")),
    )
    second = CashComponentInput(
        _rule("b", "metric_b", included_in_liquidity="YES"),
        _fact("nf_b", "metric_b", Decimal("0.2")),
    )
    result = _aggregate([first, second])
    assert result.total_for(CashView.LIQUIDITY).value == Decimal("0.3")
    assert result.total_for(CashView.FCFF).value is KnowledgeState.NOT_APPLICABLE
    assert result.total_for(CashView.FCFF).component_ids == ()


def test_cash_view_retains_minor_unit_alongside_very_large_balance() -> None:
    large = CashComponentInput(
        _rule("large", "large_metric", included_in_liquidity="YES"),
        _fact("nf_large", "large_metric", Decimal(10000000000000000000000000000000000000000)),
    )
    small = CashComponentInput(
        _rule("small", "small_metric", included_in_liquidity="YES"),
        _fact("nf_small", "small_metric", Decimal("0.01")),
    )
    result = _aggregate([large, small])
    assert result.total_for(CashView.LIQUIDITY).value == Decimal(
        "10000000000000000000000000000000000000000.01"
    )


def test_missing_state_propagates_with_full_state_list() -> None:
    known = CashComponentInput(
        _rule("known", "known_metric", included_in_cfads="YES"),
        _fact("nf_known", "known_metric", Decimal(10)),
    )
    withheld = CashComponentInput(
        _rule("withheld", "withheld_metric", included_in_cfads="YES"),
        _fact("nf_withheld", "withheld_metric", KnowledgeState.WITHHELD),
    )
    one_state = _aggregate([known, withheld]).total_for(CashView.CFADS)
    assert one_state.value is KnowledgeState.WITHHELD
    assert one_state.unresolved_states == (KnowledgeState.WITHHELD,)

    unknown = CashComponentInput(
        _rule("unknown", "unknown_metric", included_in_cfads="YES"),
        _fact("nf_unknown", "unknown_metric", KnowledgeState.UNKNOWN),
    )
    mixed = _aggregate([known, withheld, unknown]).total_for(CashView.CFADS)
    assert mixed.value is KnowledgeState.UNKNOWN
    assert mixed.unresolved_states == (KnowledgeState.UNKNOWN, KnowledgeState.WITHHELD)


def test_duplicate_component_or_fact_is_rejected() -> None:
    first = CashComponentInput(
        _rule("shared", "metric_a", included_in_fcff="YES"),
        _fact("nf_a", "metric_a", Decimal(10)),
    )
    duplicate_id = CashComponentInput(
        _rule("shared", "metric_b", included_in_fcff="YES"),
        _fact("nf_b", "metric_b", Decimal(20)),
    )
    with pytest.raises(ValueError, match="duplicate cash component_id"):
        _aggregate([first, duplicate_id])

    reused_fact = CashComponentInput(
        _rule("other", "metric_a", included_in_fcfe="YES"), first.fact
    )
    with pytest.raises(ValueError, match="reused across cash components"):
        _aggregate([first, reused_fact])
    remapped_same_source = CashComponentInput(
        _rule("other", "metric_b", included_in_fcfe="YES"),
        replace(_fact("nf_b", "metric_b", Decimal(20)), source_fact_id=first.fact.source_fact_id),
    )
    with pytest.raises(ValueError, match="reused across cash components"):
        _aggregate([first, remapped_same_source])
    with pytest.raises(ValueError, match="at least one"):
        _aggregate([])


@pytest.mark.parametrize(
    ("changed", "message"),
    [
        ({"case_id": "other_case"}, "case mismatch"),
        ({"version_id": "restated_v2"}, "version mismatch"),
        (
            {"scope": ScopeRef("other_scope", AccountingScope.CONSOLIDATED, None, None, None, None)},
            "scope mismatch",
        ),
        ({"period": Period(date(2024, 1, 1), date(2024, 12, 31), "FY")}, "period mismatch"),
        ({"currency": "USD"}, "currency mismatch"),
        ({"unit": "USD_million"}, "unit mismatch"),
        ({"publication_status": PublicationStatus.RESTATED}, "publication status mismatch"),
    ],
)
def test_incompatible_component_facts_are_rejected(changed: dict, message: str) -> None:
    first = CashComponentInput(
        _rule("first", "metric_a", included_in_fcff="YES"),
        _fact("nf_a", "metric_a", Decimal(10)),
    )
    second = CashComponentInput(
        _rule("second", "metric_b", included_in_fcff="YES"),
        replace(_fact("nf_b", "metric_b", Decimal(20)), **changed),
    )
    with pytest.raises(ValueError, match=message):
        _aggregate([first, second])


def test_metric_float_nonfinite_and_unset_flags_are_rejected() -> None:
    with pytest.raises(ValueError, match="included_in_fcff must be YES or NO"):
        _rule("bad", "metric_bad", included_in_fcff="true")
    rule = _rule("component", "metric", included_in_fcff="YES")
    with pytest.raises(ValueError, match="metric mismatch"):
        _aggregate([CashComponentInput(rule, _fact("nf_bad", "different", Decimal(1)))])
    with pytest.raises(TypeError, match="Decimal or KnowledgeState"):
        _aggregate([CashComponentInput(rule, _fact("nf_float", "metric", 1.1))])
    with pytest.raises(ValueError, match="finite Decimal"):
        _aggregate([CashComponentInput(rule, _fact("nf_nan", "metric", Decimal("NaN")))])
    with pytest.raises(ValueError, match="KNOWN requires"):
        _aggregate([CashComponentInput(rule, _fact("nf_known", "metric", KnowledgeState.KNOWN))])


def test_cfads_and_debt_service_cannot_share_one_component() -> None:
    with pytest.raises(ValueError, match="both CFADS and debt_service"):
        _rule(
            "overlap",
            "metric_overlap",
            included_in_cfads="YES",
            included_in_debt_service="YES",
        )


def test_output_identity_tracks_source_hash() -> None:
    rule = _rule("cash", "cash_metric", included_in_liquidity="YES")
    fact = _fact("nf_cash", "cash_metric", Decimal(10))
    original = _aggregate([CashComponentInput(rule, fact)])
    amended_provenance = replace(fact.provenance, content_sha256="b" * 64)
    changed = _aggregate([CashComponentInput(rule, replace(fact, provenance=amended_provenance))])
    assert changed.output_id != original.output_id
    assert changed.total_for(CashView.LIQUIDITY).value == original.total_for(CashView.LIQUIDITY).value
