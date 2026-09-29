"""Offline SEC case regression: vintage, scope, cash and debt disclosure checks."""

from __future__ import annotations

import csv
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from versioned_finance_core.contracts import (
    CaseContract,
    FinancialVersion,
    MappingRule,
    MetricDefinition,
    RawFact,
    ScopeBridge,
)
from versioned_finance_core.evidence import (
    load_provenanced_facts,
    load_source_ledger,
    select_known_facts,
)
from versioned_finance_core.financial_core import evaluate_cash_identity, normalize_actuals
from versioned_finance_core.financial_core.cash_identity import CashIdentitySpec
from versioned_finance_core.orchestration.release import case_release_readiness_issues

CASE = Path(__file__).parents[2] / "cases" / "ford_credit_2025ye_m3"
EVIDENCE = CASE / "01_evidence_core"
OUTCOME = CASE / "out_of_time_evaluation"


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_ford_credit_case_replays_2025_without_2026_outcome() -> None:
    case = CaseContract.from_mapping(
        json.loads((CASE / "00_charter" / "case.json").read_text(encoding="utf-8"))
    )
    assert case.analysis_cutoff is not None
    decision_receipts = load_source_ledger(EVIDENCE)
    outcome_receipts = load_source_ledger(OUTCOME)
    assert len(decision_receipts) == len(outcome_receipts) == 1
    assert decision_receipts[0].content_sha256 == (
        "3b5a7914fdb73a6e1425bf5745f8e20fbca6fd3703bdfc4fb3cfc865cc2bdc3b"
    )
    assert outcome_receipts[0].first_public_at > case.analysis_cutoff
    assert not decision_receipts[0].metadata.retention_right
    assert not outcome_receipts[0].metadata.retention_right

    eligible = select_known_facts(load_provenanced_facts(EVIDENCE), case.analysis_cutoff)
    future = select_known_facts(load_provenanced_facts(OUTCOME), case.analysis_cutoff)
    assert len(eligible) == 36
    assert future == ()
    assert {entry.receipt.source_id for entry in eligible} == {"sec_fmcc_2025_10k"}

    normalized = normalize_actuals(
        case.case_id,
        (RawFact.from_mapping(entry.as_csv_row()) for entry in eligible),
        (MappingRule.from_mapping(row) for row in _rows(EVIDENCE / "mappings.csv")),
        (MetricDefinition.from_mapping(row) for row in _rows(EVIDENCE / "metric_dictionary.csv")),
        (FinancialVersion.from_mapping(row) for row in _rows(CASE / "02_financial_core" / "versions.csv")),
        case.analysis_cutoff,
        scope_bridges=(ScopeBridge.from_mapping(row) for row in _rows(EVIDENCE / "scope_bridges.csv")),
    )
    assert len(normalized) == 36
    spec = CashIdentitySpec.from_mapping(_rows(CASE / "02_financial_core" / "cash_identity_checks.csv")[0])
    cash = evaluate_cash_identity(spec, normalized)
    assert cash.residual == Decimal(0)
    assert cash.calculated_closing_cash == cash.reported_closing_cash == Decimal(9377)
    assert cash.currency == "USD" and cash.unit == "USD_MILLION"

    by_metric = {fact.metric_id: fact.value for fact in normalized if fact.period.end == date(2025, 12, 31)}
    assert (
        by_metric["liquidity_cash"]
        + by_metric["liquidity_committed_abs"]
        + by_metric["liquidity_committed_unsecured"]
        - by_metric["liquidity_restricted_cash"]
        - by_metric["liquidity_abs_utilized"]
        - by_metric["liquidity_unsecured_utilized"]
        + by_metric["liquidity_other_adjustments"]
    ) == by_metric["liquidity_net_available"] == Decimal("24.6")
    assert (
        by_metric["debt_gross_principal"]
        + by_metric["debt_unamortized_cost_adjustment"]
        + by_metric["debt_fair_value_adjustment"]
    ) == by_metric["debt_carrying_amount"] == Decimal(141417)

    maturities = _rows(CASE / "05_m3_credit_liquidity_claims" / "maturities.csv")
    assert len(maturities) == 17
    assert all(not row["event_date"] and not row["committed_refinancing_source_id"] for row in maturities)
    assert sum(Decimal(row["principal_amount"]) for row in maturities if row["principal_amount"]) == Decimal(141904)
    assert sum(Decimal(row["cash_interest"]) for row in maturities if row["cash_interest"]) == Decimal(16106)
    assert all(not row["gross_contractual_cash"] for row in maturities)

    errors = case_release_readiness_issues(CASE)
    assert any("M3_CREDIT_LIQUIDITY" in error for error in errors)
