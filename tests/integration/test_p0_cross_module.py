"""Offline P0 handoff from one canonical Core cash calculation to M2 and M3.

Every number here is synthetic. The scenario is a contract test, not an
estimate of an actual issuer, project, credit facility, or discount rate.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from versioned_finance_core.contracts import (
    AccountingScope,
    ClaimTag,
    GateStatus,
    NormalizedFact,
    Period,
    PublicationStatus,
    ScopeRef,
    SourceProvenance,
)
from versioned_finance_core.financial_core import (
    BalanceSheet,
    CashComponentInput,
    CashComponentRule,
    CashView,
    OperatingPeriodInputs,
    aggregate_cash_components,
    project_linked_statements,
)
from versioned_finance_core.modules.cross_lens import (
    CorporateValueState,
    CreditFeasibilityState,
    CrossLensState,
    classify_cross_lens,
)
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
from versioned_finance_core.modules.m3 import (
    CreditPeriodInput,
    ObligorCashPosition,
    evaluate_credit_path,
    evaluate_obligor_cash,
)

AS_OF = date(2026, 1, 1)
UPFRONT = Period(AS_OF, AS_OF, "INSTANT")
FUTURE = Period(date(2026, 1, 2), date(2027, 1, 1), "YEAR")
SCOPE = ScopeRef(
    "synthetic_parent", AccountingScope.STANDALONE, None, "synthetic_obligor", None, None
)
PROVENANCE = SourceProvenance(
    source_id="synthetic_p0_fixture",
    snapshot_id="synthetic_p0_fixture_v1",
    content_sha256="a" * 64,
    first_public_at=datetime(2026, 1, 1, tzinfo=UTC),
    retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
)


def _core_cash(
    world: CashWorld,
    period: Period,
    components: tuple[tuple[str, Decimal, frozenset[CashView]], ...],
):
    """Produce real Core outputs from distinct, signed normalized facts."""

    version_id = "synthetic_baseline_v1" if world is CashWorld.STATUS_QUO else "synthetic_option_v1"
    inputs = []
    for name, amount, views in components:
        component_id = f"{world.value.lower()}_{period.end.isoformat()}_{name}"
        metric_id = f"cash_{component_id}"
        fact = NormalizedFact(
            fact_id=f"normalized_{component_id}",
            source_fact_id=f"raw_{component_id}",
            provenance=PROVENANCE,
            case_id="synthetic_p0_case",
            scope=SCOPE,
            metric_id=metric_id,
            period=period,
            currency="KRW",
            unit="KRW_million",
            value=amount,
            version_id=version_id,
            publication_status=PublicationStatus.PRELIMINARY,
            normalization_rule="synthetic after-tax scenario component",
            mapping_version="synthetic_mapping_v1",
            claim_tag=ClaimTag.ASSUMPTION,
        )
        rule = CashComponentRule(
            component_id=component_id,
            metric_id=metric_id,
            tax_basis="POST_TAX",
            obligation_id="synthetic_scheduled_debt" if name == "debt_service" else None,
            funding_source_id=None,
            included_in_fcff=CashView.FCFF in views,
            included_in_fcfe=False,
            included_in_cfads=CashView.CFADS in views,
            included_in_debt_service=CashView.DEBT_SERVICE in views,
            included_in_liquidity=CashView.LIQUIDITY in views,
            included_in_sources_uses=False,
        )
        inputs.append(CashComponentInput(rule, fact))
    return aggregate_cash_components(inputs, case_id="synthetic_p0_case", version_id=version_id)


def test_core_cash_is_reused_by_value_and_credit_lenses() -> None:
    baseline_upfront = _core_cash(
        CashWorld.STATUS_QUO,
        UPFRONT,
        (("standstill", Decimal(0), frozenset({CashView.FCFF, CashView.LIQUIDITY})),),
    )
    option_upfront = _core_cash(
        CashWorld.OPTION,
        UPFRONT,
        (
            ("capex", Decimal(-100), frozenset({CashView.FCFF, CashView.LIQUIDITY})),
            ("operating", Decimal(0), frozenset({CashView.CFADS})),
            ("debt_service", Decimal(0), frozenset({CashView.DEBT_SERVICE})),
        ),
    )
    baseline_future = _core_cash(
        CashWorld.STATUS_QUO,
        FUTURE,
        (
            (
                "operating",
                Decimal(40),
                frozenset({CashView.FCFF, CashView.CFADS, CashView.LIQUIDITY}),
            ),
        ),
    )
    option_future = _core_cash(
        CashWorld.OPTION,
        FUTURE,
        (
            (
                "operating",
                Decimal(160),
                frozenset({CashView.FCFF, CashView.CFADS, CashView.LIQUIDITY}),
            ),
            ("debt_service", Decimal(-200), frozenset({CashView.DEBT_SERVICE, CashView.LIQUIDITY})),
        ),
    )

    assert option_future.total_for(CashView.FCFF).value == Decimal(160)
    assert option_future.total_for(CashView.CFADS).value == Decimal(160)
    assert option_future.total_for(CashView.DEBT_SERVICE).value == Decimal(-200)
    assert option_future.total_for(CashView.LIQUIDITY).value == Decimal(-40)
    debt_component = "option_2027-01-01_debt_service"
    assert debt_component not in option_future.total_for(CashView.FCFF).component_ids
    assert debt_component in option_future.total_for(CashView.LIQUIDITY).component_ids

    pairs = (
        OptionCashPeriod(baseline_upfront, option_upfront, Decimal(1), "synthetic_spot_factor"),
        OptionCashPeriod(
            baseline_future, option_future, Decimal("0.9"), "synthetic_discount_factor"
        ),
    )
    effects = (
        EffectTrace(
            CashWorld.STATUS_QUO,
            UPFRONT,
            "status_quo_2026-01-01_standstill",
            "synthetic_baseline_standstill",
            EffectCategory.OPERATING,
            "synthetic_assumption_baseline",
        ),
        EffectTrace(
            CashWorld.OPTION,
            UPFRONT,
            "option_2026-01-01_capex",
            "synthetic_option_capex",
            EffectCategory.CAPEX,
            "synthetic_assumption_capex",
        ),
        EffectTrace(
            CashWorld.STATUS_QUO,
            FUTURE,
            "status_quo_2027-01-01_operating",
            "synthetic_baseline_operating",
            EffectCategory.OPERATING,
            "synthetic_assumption_baseline",
        ),
        EffectTrace(
            CashWorld.OPTION,
            FUTURE,
            "option_2027-01-01_operating",
            "synthetic_option_operating",
            EffectCategory.OPERATING,
            "synthetic_assumption_option",
        ),
    )
    reviews = tuple(
        DecisionReview(topic, ReviewDisposition.COMPLETE, f"synthetic_review_{topic.value}")
        for topic in ReviewTopic
    )
    valuation = evaluate_incremental_option(
        case_id="synthetic_p0_case",
        option_id="synthetic_build_option",
        baseline_version_id="synthetic_baseline_v1",
        as_of_date=AS_OF,
        periods=pairs,
        effects=effects,
        reviews=reviews,
    )
    assert valuation.status is GateStatus.PASS
    assert tuple(row.incremental_fcff for row in valuation.periods) == (Decimal(-100), Decimal(120))
    assert valuation.npv == Decimal("8.0")
    assert tuple(row.status_quo_output_id for row in valuation.periods) == (
        baseline_upfront.output_id,
        baseline_future.output_id,
    )
    assert tuple(row.option_output_id for row in valuation.periods) == (
        option_upfront.output_id,
        option_future.output_id,
    )

    opening = evaluate_obligor_cash(
        ObligorCashPosition(
            legal_entity_id="synthetic_obligor",
            group_cash=Decimal(1000),
            obligor_cash=Decimal(200),
            unavailable_cash=Decimal(20),
            group_source_id="synthetic_group_disclosure",
            obligor_source_id="synthetic_standalone_disclosure",
            exclusion_source_id="synthetic_access_review",
        )
    )
    credit = evaluate_credit_path(
        opening,
        (
            CreditPeriodInput(
                option_upfront,
                Decimal(50),
                Decimal(0),
                "synthetic_floor",
                "synthetic_facility",
                "synthetic_access_review",
            ),
            CreditPeriodInput(
                option_future,
                Decimal(50),
                Decimal(5),
                "synthetic_floor",
                "synthetic_facility",
                "synthetic_access_review",
            ),
        ),
    )
    assert opening.accessible_cash == Decimal(180)
    assert credit.periods[0].closing_accessible_cash == Decimal(80)
    assert credit.periods[1].core_output_id == option_future.output_id
    assert credit.periods[1].closing_accessible_cash == Decimal(40)
    assert credit.periods[1].model_dscr == Decimal("0.8")
    assert credit.periods[1].pre_action_cash_gap == Decimal(10)
    assert credit.periods[1].gap_after_committed_capacity == Decimal(5)
    assert credit.first_cash_floor_failure_date == FUTURE.end

    value_state = (
        CorporateValueState.FAVOURABLE if valuation.npv > 0 else CorporateValueState.UNFAVOURABLE
    )
    credit_state = (
        CreditFeasibilityState.CONSTRAINED
        if credit.periods[-1].gap_after_committed_capacity > 0
        else CreditFeasibilityState.FEASIBLE
    )
    decision = classify_cross_lens(
        value_state,
        credit_state,
        value_reference_id=valuation.output_id,
        credit_reference_id=credit.output_id,
    )
    assert decision.state is CrossLensState.FUNDING_REDESIGN
    assert decision.value_reference_id == valuation.output_id
    assert decision.credit_reference_id == credit.output_id


def test_linked_statements_reconcile_as_independent_core_identity() -> None:
    """The three-statement identity is separate from the FCFF fixture above."""

    opening = BalanceSheet(
        cash=Decimal(100),
        receivables=Decimal(20),
        inventory=Decimal(30),
        ppe_net=Decimal(150),
        payables=Decimal(25),
        tax_payable=Decimal(5),
        debt_face=Decimal(100),
        equity=Decimal(170),
    )
    inputs = OperatingPeriodInputs(
        volume=Decimal(10),
        selling_price=Decimal(20),
        variable_cost_per_unit=Decimal(8),
        cash_opex=Decimal(40),
        depreciation=Decimal(10),
        interest_expense=Decimal(5),
        tax_expense=Decimal(13),
        cash_taxes_paid=Decimal(10),
        closing_receivables=Decimal(25),
        closing_inventory=Decimal(35),
        closing_payables=Decimal(30),
        capex=Decimal(20),
        debt_draw=Decimal(15),
        principal_repayment=Decimal(5),
        dividends=Decimal(10),
    )
    linked = project_linked_statements(opening, inputs)
    assert linked.income.net_income == Decimal(52)
    assert linked.cash_flow.operating == Decimal(60)
    assert linked.cash_flow.investing == Decimal(-20)
    assert linked.closing.cash == Decimal(140)
    assert linked.closing.assets == linked.closing.liabilities_and_equity == Decimal(360)
    assert linked.balance_residual == linked.cash_residual == linked.debt_residual == 0
