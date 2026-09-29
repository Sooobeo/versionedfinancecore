"""Offline regression for Orion's two filed cash-flow vintages and scopes."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime
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
from versioned_finance_core.evidence import load_provenanced_facts, select_known_facts
from versioned_finance_core.financial_core import evaluate_cash_identity, normalize_actuals
from versioned_finance_core.financial_core.cash_identity import CASH_ROLES, CashIdentitySpec

CASE_DIR = Path(__file__).parents[2] / "cases" / "orion_jincheon_2026h1"

# Independently transcribed from the DART 2026 H1 cash-flow sections. These
# statement-wide amounts do not represent Jincheon-project cash flows.
EXPECTED_BY_SCOPE = {
    "CONSOLIDATED": (
        Decimal(311390944459),
        Decimal(283530566965),
        Decimal(188843904153),
        Decimal(-145108143596),
        Decimal(24627849773),
        Decimal(663285121754),
    ),
    "STANDALONE": (
        Decimal(161635751470),
        Decimal(100489533042),
        Decimal(126410415537),
        Decimal(-139867437973),
        Decimal(5475377150),
        Decimal(254143639226),
    ),
}


def _csv_rows(path: Path) -> tuple[dict[str, str], ...]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return tuple(csv.DictReader(handle))


def test_orion_cash_filing_vintages_normalize_and_reconcile_offline() -> None:
    case = CaseContract.from_mapping(
        json.loads((CASE_DIR / "00_charter" / "case.json").read_text(encoding="utf-8"))
    )
    assert case.analysis_cutoff is not None
    evidence_dir = CASE_DIR / "01_evidence_core"
    core_dir = CASE_DIR / "02_financial_core"

    entries = select_known_facts(load_provenanced_facts(evidence_dir), case.analysis_cutoff)
    assert len(entries) == 24
    assert all(entry.receipt.metadata.transformation_right for entry in entries)
    assert all(not entry.receipt.metadata.retention_right for entry in entries)
    # The later correction must not enter a replay at the original filing cutoff.
    original_cutoff = datetime.fromisoformat("2026-08-14T23:59:59+09:00")
    assert len(select_known_facts(load_provenanced_facts(evidence_dir), original_cutoff)) == 12

    versions = tuple(
        FinancialVersion.from_mapping(row) for row in _csv_rows(core_dir / "versions.csv")
    )
    normalized = normalize_actuals(
        case.case_id,
        (RawFact.from_mapping(entry.as_csv_row()) for entry in entries),
        (MappingRule.from_mapping(row) for row in _csv_rows(evidence_dir / "mappings.csv")),
        (
            MetricDefinition.from_mapping(row)
            for row in _csv_rows(evidence_dir / "metric_dictionary.csv")
        ),
        versions,
        case.analysis_cutoff,
        scope_bridges=(
            ScopeBridge.from_mapping(row) for row in _csv_rows(evidence_dir / "scope_bridges.csv")
        ),
    )
    assert len(normalized) == 24
    assert {fact.source_fact_id for fact in normalized} == {
        entry.fact.fact_id for entry in entries
    }

    grouped = defaultdict(list)
    for fact in normalized:
        grouped[(fact.version_id, fact.scope.accounting_scope.value)].append(fact)
    version_by_status = {version.publication_status.value: version.version_id for version in versions}
    assert set(version_by_status) == {"FILED", "REVISED"}
    assert set(grouped) == {
        (version_id, scope)
        for version_id in version_by_status.values()
        for scope in EXPECTED_BY_SCOPE
    }

    values_by_group = {}
    for (version_id, scope), facts in grouped.items():
        assert len(facts) == len(CASH_ROLES)
        assert len({fact.scope for fact in facts}) == 1
        by_role = {fact.metric_id: fact for fact in facts}
        assert set(by_role) == set(CASH_ROLES)
        spec = CashIdentitySpec.from_mapping({
            "identity_id": f"orion_2026h1_{version_id}_{scope.lower()}",
            "version_id": version_id,
            **{
                f"{role}_fact_id": by_role[role].source_fact_id
                for role in CASH_ROLES
            },
        })
        result = evaluate_cash_identity(spec, normalized)
        assert result.residual == Decimal(0)
        assert result.calculated_closing_cash == result.reported_closing_cash
        values = tuple(by_role[role].value for role in CASH_ROLES)
        assert values == EXPECTED_BY_SCOPE[scope]
        values_by_group[(version_id, scope)] = values

    for scope in EXPECTED_BY_SCOPE:
        assert values_by_group[(version_by_status["FILED"], scope)] == values_by_group[
            (version_by_status["REVISED"], scope)
        ]
    for version_id in version_by_status.values():
        assert values_by_group[(version_id, "CONSOLIDATED")][-1] != values_by_group[
            (version_id, "STANDALONE")
        ][-1]
