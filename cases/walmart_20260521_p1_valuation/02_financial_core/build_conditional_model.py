"""Rebuild the explicitly conditional Walmart linked forecast and M1 screen.

This case adapter selects pinned facts and declared assumptions, then delegates
all three-statement, cash-flow and valuation arithmetic to Core and M1. It
does not fetch live data or promote screening calculations to a release.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from dataclasses import fields
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from versioned_finance_core.contracts import (
    AccountingScope,
    KnowledgeState,
    ScenarioPurpose,
    VersionType,
)
from versioned_finance_core.financial_core import (
    ConsolidatedDriverInputs,
    ConsolidatedForecastSpec,
    aggregate_disclosed_opening_balance,
    audit_consolidated_cash_components,
    comparable_remaining_period_base,
    derive_consolidated_period,
    project_consolidated_free_cash_flow_path,
    project_consolidated_path,
    projected_fiscal_revenue_basis,
    reported_other_revenue,
    unlevered_cash_taxes_from_ebit,
)
from versioned_finance_core.financial_core.model_path import ModelInputEvidence
from versioned_finance_core.modules.m1.cost_of_capital import (
    BetaBasis,
    DebtValueBasis,
    SourcedValuationParameter,
    WaccInputs,
    calculate_wacc,
)
from versioned_finance_core.modules.m1.valuation import (
    CashFlowClaim,
    DatedClaimBalance,
    DiscountRateClaim,
    DiscountTiming,
    LeasePolicyEvidence,
    LeaseValuationTreatment,
    RateBasis,
    aggregate_dated_claim_balances,
    bridge_enterprise_to_equity_partial,
    dcf_inputs_from_core_cash_flows,
    terminal_operating_economics_from_forecast,
    value_perpetuity_dcf,
)

CASE = Path(__file__).resolve().parents[1]
CASE_ID = "walmart_20260521_p1_valuation"
Q1_VERSION = "wmt_actual_fy27q1_8k_20260521"
FY26_VERSION = "wmt_actual_fy26_10k_20260313"
Q1_SOURCE = "wmt_fy27q1_8k_ex991_20260521"
FY26_SOURCE = "wmt_fy26_10k_xbrl_20260313"


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record(obj: object) -> dict[str, str]:
    return {field.name: str(getattr(obj, field.name)) for field in fields(obj)}


def _fact(
    rows: list[dict[str, str]], *, metric: str, end: str, version: str,
    start: str | None = None,
) -> dict[str, str]:
    matches = [row for row in rows if row["metric_id"] == metric
               and row["period_end"] == end and row["version_id"] == version
               and (start is None or row["period_start"] == start)]
    if len(matches) != 1:
        raise ValueError(f"expected one pinned fact for {metric}/{end}/{version}, found {len(matches)}")
    row = matches[0]
    if row["currency"] != "USD" or row["unit"] != "USD":
        raise ValueError(f"non-USD fact: {metric}")
    if row["accounting_scope"] != "CONSOLIDATED" or row["economic_scope_id"] != "walmart_consolidated_group":
        raise ValueError(f"scope mismatch: {metric}")
    expected_source = Q1_SOURCE if version == Q1_VERSION else FY26_SOURCE
    if row["source_id"] != expected_source:
        raise ValueError(f"source/version mismatch: {metric}")
    if not row["first_public_at"]:
        raise ValueError(f"missing first_public_at: {metric}")
    return row


def _value(row: dict[str, str]) -> Decimal:
    return Decimal(row["value"])


def _evidence(row: dict[str, str]) -> ModelInputEvidence:
    return ModelInputEvidence(row["fact_id"], datetime.fromisoformat(row["first_public_at"]))


def _parameter(
    value: str, *, assumption_id: str, sources: tuple[str, ...],
    observation_date: str, available_at: datetime, rationale: str,
) -> SourcedValuationParameter:
    return SourcedValuationParameter(
        Decimal(value), assumption_id, sources, date.fromisoformat(observation_date),
        available_at, rationale,
    )


def _period_drivers(
    config: dict[str, object], period: dict[str, str], *,
    prior_sales: Decimal, prior_other: Decimal,
    prior_sales_evidence: ModelInputEvidence,
    prior_other_evidence: ModelInputEvidence,
    ytd_sales: Decimal, ytd_other: Decimal, ytd_capex: Decimal,
    ytd_evidence: dict[str, ModelInputEvidence],
    cutoff: datetime,
) -> tuple[ConsolidatedDriverInputs, dict[str, ModelInputEvidence]]:
    base = config["base_drivers"]
    assert isinstance(base, dict)
    values = {name: Decimal(entry["value"]) for name, entry in base.items()}
    evidence = {
        name: ModelInputEvidence(entry["id"], cutoff)
        for name, entry in base.items()
    }
    values.update({
        "comparable_prior_net_sales": prior_sales,
        "comparable_prior_other_revenue": prior_other,
        "net_sales_growth_rate": Decimal(period["net_sales_growth"]),
        "other_revenue_growth_rate": Decimal(period["other_revenue_growth"]),
        "fiscal_year_net_sales_to_date": ytd_sales,
        "fiscal_year_other_revenue_to_date": ytd_other,
        "fiscal_year_capex_to_date": ytd_capex,
        "capex_rate_of_fiscal_net_sales": Decimal(period["capex_rate"]),
        "interest_expense": Decimal(period["interest_usd"]),
        "debt_issuance": Decimal(period["debt_issuance_usd"]),
        "debt_repayment": Decimal(period["debt_repayment_usd"]),
        "dividends_declared": Decimal(period["dividends_declared_usd"]),
        "dividends_paid": Decimal(period["dividends_paid_usd"]),
    })
    period_id = period["period_id"]
    evidence.update({
        "comparable_prior_net_sales": prior_sales_evidence,
        "comparable_prior_other_revenue": prior_other_evidence,
        "net_sales_growth_rate": ModelInputEvidence(f"A_{period_id}_NET_SALES_GROWTH", cutoff),
        "other_revenue_growth_rate": ModelInputEvidence(f"A_{period_id}_OTHER_REVENUE_GROWTH", cutoff),
        "fiscal_year_net_sales_to_date": ytd_evidence["sales"],
        "fiscal_year_other_revenue_to_date": ytd_evidence["other"],
        "fiscal_year_capex_to_date": ytd_evidence["capex"],
        "capex_rate_of_fiscal_net_sales": ModelInputEvidence(f"A_{period_id}_CAPEX_RATE", cutoff),
        "interest_expense": ModelInputEvidence(f"A_{period_id}_NET_INTEREST_CASH_PROXY", cutoff),
        "debt_issuance": ModelInputEvidence(f"A_{period_id}_DEBT_ISSUE", cutoff),
        "debt_repayment": ModelInputEvidence(f"A_{period_id}_DEBT_REPAY", cutoff),
        "dividends_declared": ModelInputEvidence(f"A_{period_id}_DIVIDENDS_DECLARED", cutoff),
        "dividends_paid": ModelInputEvidence(f"A_{period_id}_DIVIDENDS_PAID", cutoff),
    })
    return ConsolidatedDriverInputs(**values), evidence


def build_review_artifacts(
    *, normalized_actuals: Path, config_path: Path = CASE / "02_financial_core" / "conditional_model_config.json",
) -> dict[str, object]:
    """Return deterministic, review-only data without writing or publishing."""
    config = json.loads(config_path.read_text(encoding="utf-8"))
    charter = json.loads((CASE / "00_charter" / "case.json").read_text(encoding="utf-8"))
    rows = _read_csv(normalized_actuals)
    locator_rows = {row["evidence_id"]: row for row in _read_csv(
        CASE / "01_evidence_core" / "assumption_evidence.csv"
    )}
    cutoff = datetime.fromisoformat(charter["analysis_cutoff"])
    if config["schema_version"] != 1 or config["source_availability_review"] != "WITHHELD":
        raise ValueError("conditional configuration must remain review-only")

    opening_groups = {name: tuple(metrics) for name, metrics in config["opening_groups"].items()}
    opening_metrics = set().union(*opening_groups.values()) | {
        "total_assets", "total_liabilities_equity",
    }
    opening_facts = {
        metric: _fact(rows, metric=metric, end="2026-04-30", version=Q1_VERSION)
        for metric in opening_metrics
    }
    opening = aggregate_disclosed_opening_balance(
        {metric: _value(row) for metric, row in opening_facts.items()},
        opening_groups,
        {metric: _evidence(row) for metric, row in opening_facts.items()},
        asset_total_metric_id="total_assets",
        liabilities_equity_total_metric_id="total_liabilities_equity",
        information_cutoff=cutoff,
    )

    def f(metric: str, end: str, version: str, start: str | None = None) -> dict[str, str]:
        return _fact(rows, metric=metric, end=end, version=version, start=start)

    fy26_sales = f("net_sales_year", "2026-01-31", FY26_VERSION, "2025-02-01")
    fy26_total = f("total_revenue_year", "2026-01-31", FY26_VERSION, "2025-02-01")
    q1_prior_sales = f("net_sales_quarter", "2025-04-30", Q1_VERSION, "2025-02-01")
    q1_prior_other = f("membership_and_other_income_quarter", "2025-04-30", Q1_VERSION, "2025-02-01")
    q1_sales = f("net_sales_quarter", "2026-04-30", Q1_VERSION, "2026-02-01")
    q1_other = f("membership_and_other_income_quarter", "2026-04-30", Q1_VERSION, "2026-02-01")
    q1_capex = f("capital_expenditure_payments_quarter", "2026-04-30", Q1_VERSION, "2026-02-01")
    prior_other = reported_other_revenue(_value(fy26_total), _value(fy26_sales))
    prior_sales = comparable_remaining_period_base(_value(fy26_sales), _value(q1_prior_sales))
    prior_other = comparable_remaining_period_base(prior_other, _value(q1_prior_other))
    if _value(q1_capex) <= 0:
        raise ValueError("normalized Q1 capex must be a positive outflow magnitude")
    original_source_ids = tuple(sorted({row["source_id"] for row in opening_facts.values()}))
    periods = []
    for index, period in enumerate(config["forecast_periods"]):
        if index == 0:
            prior_sales_ev = ModelInputEvidence(
                f"D_{fy26_sales['fact_id']}_{q1_prior_sales['fact_id']}", cutoff
            )
            prior_other_ev = ModelInputEvidence(
                f"D_{fy26_total['fact_id']}_{fy26_sales['fact_id']}_{q1_prior_other['fact_id']}", cutoff
            )
            ytd_sales, ytd_other, ytd_capex = _value(q1_sales), _value(q1_other), _value(q1_capex)
            ytd_ev = {"sales": _evidence(q1_sales), "other": _evidence(q1_other), "capex": _evidence(q1_capex)}
        else:
            prior_sales, prior_other = projected_fiscal_revenue_basis(periods[-1])
            prior_sales_ev = ModelInputEvidence(f"D_{periods[-1].period_id}_FISCAL_SALES", cutoff)
            prior_other_ev = ModelInputEvidence(f"D_{periods[-1].period_id}_FISCAL_OTHER_REVENUE", cutoff)
            ytd_sales = ytd_other = ytd_capex = Decimal(0)
            zero_ev = ModelInputEvidence(f"A_{period['period_id']}_FULL_YEAR_NO_PRIOR_YTD", cutoff)
            ytd_ev = {"sales": zero_ev, "other": zero_ev, "capex": zero_ev}
        drivers, driver_evidence = _period_drivers(
            config, period, prior_sales=prior_sales, prior_other=prior_other,
            prior_sales_evidence=prior_sales_ev, prior_other_evidence=prior_other_ev,
            ytd_sales=ytd_sales, ytd_other=ytd_other, ytd_capex=ytd_capex,
            ytd_evidence=ytd_ev, cutoff=cutoff,
        )
        periods.append(derive_consolidated_period(
            period_id=period["period_id"], period_start=date.fromisoformat(period["start"]),
            period_end=date.fromisoformat(period["end"]), drivers=drivers,
            driver_evidence=driver_evidence,
        ))

    spec = ConsolidatedForecastSpec(
        case_id=CASE_ID, version_id=config["version_id"],
        version_type=VersionType.SCENARIO, scenario_id=config["scenario_id"],
        scenario_purpose=ScenarioPurpose.ANALYST_BASE,
        accounting_scope=AccountingScope.CONSOLIDATED,
        economic_scope_id=charter["economic_scope_id"],
        legal_entity_id=charter["legal_entity_id"],
        currency="USD", unit="USD", opening_balance_date=date.fromisoformat(config["opening_date"]),
        opening=opening.opening, opening_evidence=opening.opening_evidence,
        information_cutoff=cutoff, periods=tuple(periods),
    )
    path = project_consolidated_path(spec)
    unlevered_taxes = unlevered_cash_taxes_from_ebit(
        path, tax_rate=Decimal(config["unlevered_cash_tax_rate"]),
        evidence=ModelInputEvidence("A_UNLEVERED_CASH_TAX_24_PERCENT_EBIT_PROXY", cutoff),
        method_id="EBIT_TIMES_24_PERCENT_SCREEN",
    )
    cash_flows = project_consolidated_free_cash_flow_path(path, unlevered_cash_taxes=unlevered_taxes)
    audits = audit_consolidated_cash_components(path, cash_flows)

    def leaf_claim(metric: str) -> DatedClaimBalance:
        row = f(metric, "2026-04-30", Q1_VERSION)
        return DatedClaimBalance(
            _value(row), row["fact_id"], date(2026, 4, 30),
            datetime.fromisoformat(row["first_public_at"]),
            AccountingScope.CONSOLIDATED, charter["economic_scope_id"],
            charter["legal_entity_id"], "USD", "USD",
        )

    debt_claim = aggregate_dated_claim_balances(
        tuple(leaf_claim(metric) for metric in (
            "short_term_borrowings", "current_debt", "noncurrent_debt",
            "finance_lease_current", "finance_lease_long_term",
        )),
        aggregate_name="APR30_DEBT_AND_FINANCE_LEASES",
        information_cutoff=cutoff,
    )
    minority_claim = aggregate_dated_claim_balances(
        tuple(leaf_claim(metric) for metric in ("redeemable_nci", "nonredeemable_nci")),
        aggregate_name="APR30_REDEEMABLE_AND_NONREDEEMABLE_NCI",
        information_cutoff=cutoff,
    )
    if debt_claim.amount != Decimal(config["wacc_screen"]["debt_value_usd"]):
        raise ValueError("WACC debt proxy does not match pinned April debt plus finance leases")

    lease_policy = LeasePolicyEvidence(
        LeaseValuationTreatment.UNRESOLVED, "A_LEASE_CLAIM_POLICY_UNRESOLVED",
        (Q1_SOURCE, FY26_SOURCE), cutoff, False, False, False,
    )
    wc = config["wacc_screen"]
    def wp(field: str, aid: str, ids: tuple[str, ...], observed: str, note: str) -> SourcedValuationParameter:
        missing = set(ids) - (locator_rows.keys() | {Q1_SOURCE, FY26_SOURCE, debt_claim.source_id})
        if missing:
            raise ValueError(f"missing assumption locators: {sorted(missing)}")
        return _parameter(wc[field], assumption_id=aid, sources=ids,
                          observation_date=observed, available_at=cutoff,
                          rationale=note)
    wacc = calculate_wacc(WaccInputs(
        case_id=CASE_ID, assumption_id="A_WMT_WACC_CONDITIONAL_SCREEN_V1",
        valuation_date=date.fromisoformat(charter["as_of_date"]),
        information_cutoff=cutoff, accounting_scope=AccountingScope.CONSOLIDATED,
        economic_scope_id=charter["economic_scope_id"], currency="USD",
        rate_basis=RateBasis.NOMINAL,
        risk_free_rate=wp("risk_free_rate", "A_UST10Y_PAR_YIELD_PROXY", ("usd_ust10y_20260521",), "2026-05-21", "Treasury par-yield proxy; exact first public time unverified."),
        levered_beta=wp("beta", "A_SECTOR_BETA_0_90", ("us_retail_general_beta_202601", "us_retail_grocery_beta_202601"), "2026-01-01", "Analyst selection between two sector betas, not Walmart measured beta."),
        equity_risk_premium=wp("erp", "A_NYU_ERP_SUSTAINABLE_4_24", ("us_implied_erp_20260501",), "2026-05-01", "NYU author estimate; first-public and rights unverified."),
        marginal_tax_rate=wp("marginal_tax_rate", "A_MARGINAL_TAX_RATE_24_PROXY", ("wmt_fy27_etr_guidance_20260521",), "2026-05-21", "24% within FY27 company guidance, not a durable marginal rate."),
        share_price=wp("share_price_usd", "A_NASDAQ_CLOSE_SCREEN", ("wmt_close_20260521",), "2026-05-21", "Retrospectively retrieved close; public timestamp unverified."),
        shares_outstanding=wp("shares_outstanding", "A_MARCH_SHARE_COUNT_PROXY", ("wmt_shares_20260311",), "2026-03-11", "Latest cover-date count, stale at valuation date."),
        debt_value=wp("debt_value_usd", "A_APRIL_BOOK_DEBT_PROXY", (debt_claim.source_id,), "2026-04-30", "April book short/long debt plus finance leases; market value and lease policy unresolved."),
        beta_basis=BetaBasis.SECTOR_PROXY,
        debt_value_basis=DebtValueBasis.CARRYING_PROXY,
        lease_policy=lease_policy,
        marginal_debt_spread=wp("debt_spread", "A_APRIL_2036_SPREAD_PROXY", ("wmt_2036_bond_spread_20260427",), "2026-04-27", "April issue spread added to May 21 UST par yield; not May 21 traded debt yield."),
    ))
    tc = config["terminal"]
    terminal = terminal_operating_economics_from_forecast(
        cash_flows, sustainable_ebit_growth=Decimal(tc["ebit_growth"]),
        terminal_growth_rate=Decimal(tc["growth"]),
        unlevered_cash_tax_rate=Decimal(tc["cash_tax_rate"]),
        sustainable_roic=Decimal(tc["sustainable_roic"]),
        assumption_id="A_TERMINAL_OPERATING_ECONOMICS_V1",
        ebit_growth_assumption_id="A_TERMINAL_EBIT_GROWTH_2_PERCENT",
        cash_tax_rate_assumption_id="A_TERMINAL_CASH_TAX_24_PERCENT",
        roic_assumption_id="A_TERMINAL_ROIC_12_PERCENT",
        growth_assumption_id="A_TERMINAL_GROWTH_2_PERCENT",
        basis_source_ids=("fed_longrun_real_gdp_20260318", "fed_longrun_pce_20260318", FY26_SOURCE),
        available_at=cutoff, rationale=tc["rationale"],
    )
    dcf = value_perpetuity_dcf(dcf_inputs_from_core_cash_flows(
        cash_flows, case_id=CASE_ID, forecast_version_id=config["version_id"],
        accounting_scope=AccountingScope.CONSOLIDATED,
        economic_scope_id=charter["economic_scope_id"], legal_entity_id=charter["legal_entity_id"],
        currency="USD", unit="USD", cash_flow_claim=CashFlowClaim.FCFF,
        discount_rate_claim=DiscountRateClaim.WACC, rate_basis=RateBasis.NOMINAL,
        annual_discount_rate=wacc.wacc, discount_rate_assumption_id=wacc.output_id,
        discount_rate_available_at=cutoff, terminal_next_cash_flow=terminal.next_year_fcff,
        terminal_growth_rate=terminal.growth_rate,
        terminal_state_assumption_id=terminal.assumption_id,
        terminal_state_available_at=cutoff, discount_timing=DiscountTiming.ACT_365_FIXED,
        discount_rate_basis_source_ids=(wacc.output_id,),
        terminal_state_basis_source_ids=terminal.basis_source_ids,
        valuation_date=date.fromisoformat(charter["as_of_date"]),
        discount_rate_rationale="Retrospective conditional WACC screen; source availability and lease fit unresolved.",
        terminal_cash_flow_rationale=tc["rationale"], terminal_economics=terminal,
    ))
    bridge = bridge_enterprise_to_equity_partial(
        dcf, excess_cash=KnowledgeState.UNKNOWN,
        nonoperating_assets=KnowledgeState.UNKNOWN,
        debt_like_claims=debt_claim,
        minority_interest=minority_claim,
        other_senior_claims=KnowledgeState.UNKNOWN,
        lease_policy=lease_policy,
    )
    forecast_periods = []
    for forecast, flow, audit in zip(path.periods, cash_flows.periods, audits, strict=True):
        forecast_periods.append({
            "period_id": forecast.period_id, "period_start": forecast.period_start.isoformat(),
            "period_end": forecast.period_end.isoformat(),
            "drivers": _record(spec.periods[len(forecast_periods)].driver_inputs),
            "driver_evidence": {
                name: item.source_or_assumption_id
                for name, item in spec.periods[len(forecast_periods)].driver_evidence.items()
            },
            "income_statement": _record(forecast.result.income),
            "balance_sheet": _record(forecast.result.closing),
            "total_assets": str(forecast.result.closing.assets),
            "total_liabilities_and_equity": str(forecast.result.closing.liabilities_and_equity),
            "cash_flow_statement": _record(forecast.result.cash_flow),
            "fcff": str(flow.fcff), "fcfe": str(flow.fcfe),
            "fcff_output_id": flow.fcff_output_id, "fcfe_output_id": flow.fcfe_output_id,
            "cash_component_audit_id": audit.output_id,
            "identity_residuals": {
                "balance": str(forecast.result.balance_residual),
                "cash": str(forecast.result.cash_residual),
                "debt": str(forecast.result.debt_residual),
                "tax": str(forecast.result.tax_residual),
                "ppe": str(forecast.result.ppe_residual),
                "dividends_payable": str(forecast.result.dividend_payable_residual),
            },
        })
    common = {
        "schema_version": 1, "case_id": CASE_ID,
        "forecast_version_id": config["version_id"], "scenario_id": config["scenario_id"],
        "model_origin": config["model_origin"], "information_cutoff": charter["analysis_cutoff"],
        "source_availability_review": config["source_availability_review"],
        "assumption_available_at_semantics": (
            "Hypothetical May 21 scenario effective time; retrospective market locator "
            "first-public availability is not established and cannot pass release review."
        ),
        "normalized_actuals_sha256": _digest(normalized_actuals),
        "config_sha256": _digest(config_path),
        "source_ids": [*original_source_ids, FY26_SOURCE],
        "limitations": config["limitations"],
    }
    forecast_artifact = {
        **common, "output_id": cash_flows.baseline.output_id,
        "opening_aggregation_id": opening.output_id,
        "opening_balance_sheet": _record(opening.opening),
        "opening_groups": config["opening_groups"],
        "core_path_sha256": path.content_sha256,
        "baseline_output_id": cash_flows.baseline.output_id,
        "cash_flow_path_output_id": cash_flows.output_id,
        "periods": forecast_periods,
        "cash_component_audits": [audit.as_dict() for audit in audits],
        "review_status": "WITHHELD",
    }
    valuation_artifact = {
        **common, "cash_flow_path_output_id": cash_flows.output_id,
        "wacc": {
            "output_id": wacc.output_id, "risk_free_rate": str(wacc.risk_free_rate),
            "cost_of_equity": str(wacc.cost_of_equity),
            "pre_tax_cost_of_debt": str(wacc.pre_tax_cost_of_debt),
            "after_tax_cost_of_debt": str(wacc.after_tax_cost_of_debt),
            "market_equity_proxy_usd": str(wacc.market_equity_value),
            "debt_book_proxy_usd": str(wacc.debt_value),
            "equity_weight": str(wacc.equity_weight), "debt_weight": str(wacc.debt_weight),
            "conditional_rate": str(wacc.wacc),
            "failed_structural_checks": wacc.failed_structural_checks,
            "eligibility_status": wacc.eligibility_status.value,
            "input_lineage": wacc.input_lineage,
        },
        "market_input_review": {
            evidence_id: {
                "source_id": item["source_id"],
                "observed_value": item["observed_value"],
                "event_at": item["event_at"] or None,
                "first_public_at": item["first_public_at"] or None,
                "temporal_state": item["temporal_state"],
                "rights_state": item["rights_state"],
            }
            for evidence_id, item in sorted(locator_rows.items())
            if evidence_id in {
                "wmt_close_20260521", "usd_ust10y_20260521",
                "wmt_2036_bond_spread_20260427", "us_implied_erp_20260501",
                "us_retail_general_beta_202601", "us_retail_grocery_beta_202601",
                "wmt_shares_20260311", "wmt_fy27_etr_guidance_20260521",
            }
        },
        "terminal": {
            "assumption_id": terminal.assumption_id,
            "final_core_fcff_output_id": terminal.final_core_fcff_output_id,
            "final_core_fcff": str(terminal.final_core_fcff),
            "next_year_ebit": str(terminal.next_year_ebit),
            "next_year_unlevered_nopat": str(terminal.next_year_unlevered_nopat),
            "growth_rate": str(terminal.growth_rate),
            "sustainable_roic": str(terminal.sustainable_roic),
            "reinvestment_rate": str(terminal.reinvestment_rate),
            "next_year_fcff": str(terminal.next_year_fcff),
            "transition_difference": str(terminal.transition_difference),
            "transition_ratio": str(terminal.transition_ratio),
            "rationale": terminal.rationale,
        },
        "dcf_screen": {
            "output_id": dcf.output_id,
            "value_claim": dcf.value_claim,
            "discount_timing": dcf.discount_timing.value,
            "valuation_date": dcf.valuation_date.isoformat(),
            "first_forecast_period_start": dcf.first_forecast_period_start.isoformat(),
            "period_year_fractions": [str(x) for x in dcf.period_year_fractions],
            "explicit_period_value_usd": str(dcf.explicit_period_value),
            "terminal_value_at_horizon_usd": str(dcf.terminal_value_at_horizon),
            "present_terminal_value_usd": str(dcf.present_terminal_value),
            "conditional_enterprise_value_usd": str(dcf.total_value),
            "eligibility_status": "WITHHELD",
        },
        "partial_equity_bridge": {
            "output_id": bridge.output_id,
            "known_subtotal_usd": str(bridge.known_subtotal),
            "unknown_components": bridge.unknown_components,
            "failed_structural_checks": bridge.failed_structural_checks,
            "equity_value": None,
            "known_claims": {
                "debt_and_finance_leases_usd": str(debt_claim.amount),
                "debt_claim_source_id": debt_claim.source_id,
                "debt_component_source_ids": debt_claim.component_source_ids,
                "redeemable_and_nonredeemable_nci_usd": str(minority_claim.amount),
                "minority_claim_source_id": minority_claim.source_id,
                "minority_component_source_ids": minority_claim.component_source_ids,
            },
            "eligibility_status": bridge.eligibility_status.value,
        },
        "release_status": "WITHHELD",
    }
    memo_fields = {
        "schema_version": 1,
        "case_id": CASE_ID,
        "fields": [
            {
                "name": "conditional_forecast_review_status",
                "value": "WITHHELD",
                "output_id": cash_flows.baseline.output_id,
            },
            {
                "name": "conditional_dcf_release_status",
                "value": "WITHHELD",
                "output_id": dcf.output_id,
            },
            {
                "name": "common_equity_value_state",
                "value": "UNKNOWN",
                "output_id": bridge.output_id,
            },
        ],
    }
    return {"forecast": forecast_artifact, "valuation": valuation_artifact,
            "memo_fields": memo_fields}


def _csv_text(columns: tuple[str, ...], rows: list[dict[str, str]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def review_csvs(
    artifacts: dict[str, object], config_path: Path = CASE / "02_financial_core" / "conditional_model_config.json",
) -> dict[str, str]:
    """Format existing case-contract tables from canonical Core/M1 outputs."""
    config = json.loads(config_path.read_text(encoding="utf-8"))
    forecast, valuation = artifacts["forecast"], artifacts["valuation"]
    scenario_id, version_id = config["scenario_id"], config["version_id"]
    scope = "walmart_consolidated_group"
    forecast_rows: list[dict[str, str]] = []
    for period in forecast["periods"]:
        metrics = {
            "net_sales": period["income_statement"]["net_sales"],
            "other_revenue": period["income_statement"]["other_revenue"],
            "operating_income": period["income_statement"]["operating_income"],
            "net_income": period["income_statement"]["net_income"],
            "cash_from_operations": period["cash_flow_statement"]["operating"],
            "cash_from_investing": period["cash_flow_statement"]["investing"],
            "cash_from_financing": period["cash_flow_statement"]["financing"],
            "closing_cash_and_equivalents": period["cash_flow_statement"]["closing_cash"],
            "total_assets": period["total_assets"],
            "total_liabilities_and_equity": period["total_liabilities_and_equity"],
            "fcff_conditional": period["fcff"],
            "fcfe_conditional": period["fcfe"],
        }
        for metric_id, value in metrics.items():
            forecast_rows.append({
                "version_id": version_id, "scenario_id": scenario_id,
                "metric_id": metric_id, "period_start": period["period_start"],
                "period_end": period["period_end"], "economic_scope_id": scope,
                "segment_id": "", "currency": "USD", "unit": "USD", "value": value,
                "driver_or_assumption_id": (
                    period["fcff_output_id"] if metric_id == "fcff_conditional"
                    else period["fcfe_output_id"] if metric_id == "fcfe_conditional"
                    else forecast["core_path_sha256"]
                ),
                "created_at": "", "review_status": "WITHHELD",
            })
    forecast_columns = (
        "version_id", "scenario_id", "metric_id", "period_start", "period_end",
        "economic_scope_id", "segment_id", "currency", "unit", "value",
        "driver_or_assumption_id", "created_at", "review_status",
    )
    scenario_columns = (
        "scenario_id", "scenario_purpose", "version_id", "driver_id", "period_start",
        "period_end", "input_value", "input_unit", "evidence_or_assumption_id",
        "mechanism", "dependency_group", "review_status", "baseline_version_id",
    )
    scenario_rows = [
        {
            "scenario_id": scenario_id, "scenario_purpose": "ANALYST_BASE",
            "version_id": version_id, "driver_id": name,
            "period_start": period["period_start"], "period_end": period["period_end"],
            "input_value": value, "input_unit": "USD" if (
                name.endswith("_income") or name in {
                    "comparable_prior_net_sales", "comparable_prior_other_revenue",
                    "fiscal_year_net_sales_to_date", "fiscal_year_other_revenue_to_date",
                    "fiscal_year_capex_to_date", "interest_expense", "cash_other_income",
                    "ppe_noncash_change", "other_long_lived_assets_investing_cash_change",
                    "other_long_lived_assets_noncash_change", "debt_issuance",
                    "debt_repayment", "debt_carrying_noncash_change",
                    "other_liabilities_operating_cash_change",
                    "other_liabilities_financing_cash_change",
                    "other_liabilities_noncash_change", "dividends_declared",
                    "dividends_paid", "share_issuance", "share_repurchases",
                    "other_comprehensive_income",
                }
            ) else "DECIMAL_RATE",
            "evidence_or_assumption_id": period["driver_evidence"][name],
            "mechanism": "CORE_LINKED_DRIVER", "dependency_group": "CONSOLIDATED_BASE",
            "review_status": "WITHHELD", "baseline_version_id": Q1_VERSION,
        }
        for period in forecast["periods"]
        for name, value in sorted(period["drivers"].items())
    ]
    valuation_columns = (
        "valuation_run_id", "as_of_date", "method", "eligibility_state", "scenario_id",
        "value_basis", "discount_rate_basis", "terminal_basis", "enterprise_value",
        "equity_value", "currency", "range_low", "range_high", "thesis_break",
        "limitations", "review_status",
    )
    valuation_rows = [{
        "valuation_run_id": valuation["dcf_screen"]["output_id"],
        "as_of_date": "2026-05-21", "method": "FCFF_WACC_DCF_ACT_365F",
        "eligibility_state": "WITHHELD", "scenario_id": scenario_id,
        "value_basis": valuation["cash_flow_path_output_id"],
        "discount_rate_basis": valuation["wacc"]["output_id"],
        "terminal_basis": valuation["terminal"]["assumption_id"],
        "enterprise_value": "", "equity_value": "", "currency": "USD",
        "range_low": "", "range_high": "", "thesis_break": "NOT_TESTABLE_FROM_PUBLIC_DATA",
        "limitations": "See conditional_valuation_screen.json; market vintage, lease and claims unresolved",
        "review_status": "WITHHELD",
    }]
    assumption_columns = (
        "assumption_id", "variable", "scenario_id", "value", "unit", "basis",
        "source_id", "mechanism", "range_low", "range_high", "dependency",
        "owner", "reviewer", "expires_at", "trigger", "claim_tag", "status",
    )
    assumption_rows: list[dict[str, str]] = []

    def add_assumption(aid: str, variable: str, value: str, unit: str,
                       sources: tuple[str, ...], basis: str, dependency: str = "") -> None:
        assumption_rows.append({
            "assumption_id": aid, "variable": variable, "scenario_id": scenario_id,
            "value": value, "unit": unit, "basis": basis,
            "source_id": ";".join(sources), "mechanism": "ANALYST_CONDITIONAL_SCENARIO",
            "range_low": "", "range_high": "", "dependency": dependency,
            "owner": "personal_analyst_simulation", "reviewer": "",
            "expires_at": "", "trigger": "new filing or source review",
            "claim_tag": "A", "status": "WITHHELD",
        })

    for name, entry in sorted(config["base_drivers"].items()):
        add_assumption(entry["id"], name, entry["value"],
                       "DECIMAL_RATE" if "rate" in name or "margin" in name else "USD",
                       tuple(entry["sources"]), entry["note"])
    source_map = {
        "net_sales_growth_rate": ("net_sales_growth", (FY26_SOURCE, Q1_SOURCE),
                                  "Analyst growth on comparable fiscal period; FY27 remaining 3.05% yields approximately 4% full-year reported USD growth."),
        "other_revenue_growth_rate": ("other_revenue_growth", (FY26_SOURCE, Q1_SOURCE),
                                     "Analyst other-revenue growth scenario."),
        "capex_rate_of_fiscal_net_sales": ("capex_rate", ("wmt_fy27_capex_sales_guidance_20260521", FY26_SOURCE),
                                          "Full-year capex to sales; FY27 deducts already reported Q1 capex."),
        "interest_expense": ("interest_usd", ("wmt_fy26_net_interest", "wmt_fy27q1_net_interest", "wmt_fy27_net_interest_increase_guidance_20260521"),
                             "Net P&L interest used as cash-interest proxy; FY27 remaining follows guidance midpoint."),
        "debt_issuance": ("debt_issuance_usd", (Q1_SOURCE,), "Hypothetical rollover; not committed funding."),
        "debt_repayment": ("debt_repayment_usd", (Q1_SOURCE,), "Hypothetical rollover; not debt maturity proof."),
        "dividends_declared": ("dividends_declared_usd", (Q1_SOURCE,), "Declared dividend schedule scenario."),
        "dividends_paid": ("dividends_paid_usd", (Q1_SOURCE,), "Payment of opening dividend payable then annual policy scenario."),
    }
    for period in config["forecast_periods"]:
        pid = period["period_id"]
        forecast_period = next(item for item in forecast["periods"] if item["period_id"] == pid)
        for driver_name, (field_name, sources, note) in source_map.items():
            aid = forecast_period["driver_evidence"][driver_name]
            add_assumption(aid, driver_name, period[field_name],
                           "DECIMAL_RATE" if "growth" in driver_name or "rate" in driver_name else "USD",
                           sources, note, pid)
        if pid != "FY27_REMAINING":
            add_assumption(
                f"A_{pid}_FULL_YEAR_NO_PRIOR_YTD", "full_year_prior_ytd_flows",
                "0", "USD", ("02_financial_core/conditional_model_config.json",),
                "Full fiscal forecast period begins on February 1; no earlier actual YTD flow is added.",
                pid,
            )
    wacc_ids = {
        "risk_free_rate": "A_UST10Y_PAR_YIELD_PROXY",
        "beta": "A_SECTOR_BETA_0_90",
        "erp": "A_NYU_ERP_SUSTAINABLE_4_24",
        "marginal_tax_rate": "A_MARGINAL_TAX_RATE_24_PROXY",
        "share_price_usd": "A_NASDAQ_CLOSE_SCREEN",
        "shares_outstanding": "A_MARCH_SHARE_COUNT_PROXY",
        "debt_value_usd": "A_APRIL_BOOK_DEBT_PROXY",
        "debt_spread": "A_APRIL_2036_SPREAD_PROXY",
    }
    wacc_sources = {
        "risk_free_rate": ("usd_ust10y_20260521",),
        "beta": ("us_retail_general_beta_202601", "us_retail_grocery_beta_202601"),
        "erp": ("us_implied_erp_20260501",),
        "marginal_tax_rate": ("wmt_fy27_etr_guidance_20260521",),
        "share_price_usd": ("wmt_close_20260521",),
        "shares_outstanding": ("wmt_shares_20260311",),
        "debt_value_usd": (
            valuation["partial_equity_bridge"]["known_claims"]["debt_claim_source_id"],
        ),
        "debt_spread": ("wmt_2036_bond_spread_20260427",),
    }
    for name, value in sorted(config["wacc_screen"].items()):
        add_assumption(wacc_ids[name], name, value,
                       "USD" if name in {"share_price_usd", "debt_value_usd"} else
                       "SHARES" if name == "shares_outstanding" else "DECIMAL_RATE",
                       wacc_sources[name],
                       "Retrospective WACC screen; exact first-public and/or fit checks remain unresolved.",
                       valuation["wacc"]["output_id"])
    terminal_ids = {
        "ebit_growth": "A_TERMINAL_EBIT_GROWTH_2_PERCENT",
        "growth": "A_TERMINAL_GROWTH_2_PERCENT",
        "cash_tax_rate": "A_TERMINAL_CASH_TAX_24_PERCENT",
        "sustainable_roic": "A_TERMINAL_ROIC_12_PERCENT",
    }
    for name, assumption_id in terminal_ids.items():
        add_assumption(assumption_id, name, config["terminal"][name],
                       "DECIMAL_RATE", ("fed_longrun_real_gdp_20260318", FY26_SOURCE),
                       config["terminal"]["rationale"],
                       valuation["terminal"]["assumption_id"])
    add_assumption(
        "A_UNLEVERED_CASH_TAX_24_PERCENT_EBIT_PROXY",
        "unlevered_cash_tax_rate", config["unlevered_cash_tax_rate"],
        "DECIMAL_RATE", ("wmt_fy27_etr_guidance_20260521",),
        "EBIT times 24%; temporary differences and jurisdictional tax attributes omitted.",
        forecast["cash_flow_path_output_id"],
    )
    return {
        "forecast_versions.csv": _csv_text(forecast_columns, forecast_rows),
        "valuation_runs.csv": _csv_text(valuation_columns, valuation_rows),
        "conditional_scenario_drivers.csv": _csv_text(scenario_columns, scenario_rows),
        "assumptions.csv": _csv_text(assumption_columns, assumption_rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--normalized-actuals", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--replace-staging", action="store_true")
    args = parser.parse_args()
    artifacts = build_review_artifacts(normalized_actuals=args.normalized_actuals)
    outputs = {
        "conditional_linked_forecast.json": artifacts["forecast"],
        "conditional_valuation_screen.json": artifacts["valuation"],
        "conditional_memo_fields.json": artifacts["memo_fields"],
    }
    csv_outputs = review_csvs(artifacts)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for filename in (*outputs, *csv_outputs):
        target = args.output_dir / filename
        if target.exists() and not args.replace_staging:
            parser.error(f"existing output requires --replace-staging: {target}")
    for filename, payload in outputs.items():
        (args.output_dir / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    for filename, payload in csv_outputs.items():
        (args.output_dir / filename).write_text(payload, encoding="utf-8")
    print(artifacts["forecast"]["core_path_sha256"])
    print(artifacts["valuation"]["dcf_screen"]["output_id"])


if __name__ == "__main__":
    main()
