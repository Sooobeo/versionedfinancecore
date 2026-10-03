"""Exact identities between reported, normalized historical statement lines.

The check consumes Core-normalized facts only. It does not infer missing lines,
mix publication vintages, or silently apply a tolerance to filing amounts.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from versioned_finance_core.contracts import KnowledgeState, NormalizedFact, Period, ScopeRef
from versioned_finance_core.financial_core.identities import _exact_sum

BALANCE_SHEET_FORMULA = "reported_assets_vs_liabilities_and_equity_v1"
OPERATING_INCOME_FORMULA = "reported_revenue_less_cogs_sga_vs_operating_income_v1"


@dataclass(frozen=True)
class ReportedStatementIdentity:
    identity_kind: str
    output_id: str
    case_id: str
    version_id: str
    scope: ScopeRef
    period: Period
    currency: str
    unit: str
    normalized_fact_ids: tuple[str, ...]
    source_fact_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    source_content_sha256: tuple[str, ...]
    calculated_amount: Decimal | None
    reported_amount: Decimal | None
    residual: Decimal | None
    knowledge_state: KnowledgeState

    @property
    def reconciled(self) -> bool | None:
        return self.residual == 0 if self.residual is not None else None

    def as_dict(self) -> dict[str, object]:
        return {
            "identity_kind": self.identity_kind,
            "output_id": self.output_id,
            "case_id": self.case_id,
            "version_id": self.version_id,
            "economic_scope_id": self.scope.economic_scope_id,
            "accounting_scope": self.scope.accounting_scope.value,
            "legal_entity_id": self.scope.legal_entity_id,
            "segment_id": self.scope.segment_id,
            "instrument_id": self.scope.instrument_id,
            "economic_legal_scope_bridge_id": self.scope.economic_legal_scope_bridge_id,
            "period_start": self.period.start.isoformat(),
            "period_end": self.period.end.isoformat(),
            "period_type": self.period.period_type,
            "currency": self.currency,
            "unit": self.unit,
            "normalized_fact_ids": list(self.normalized_fact_ids),
            "source_fact_ids": list(self.source_fact_ids),
            "source_ids": list(self.source_ids),
            "source_content_sha256": list(self.source_content_sha256),
            "calculated_amount": (
                str(self.calculated_amount) if self.calculated_amount is not None else None
            ),
            "reported_amount": (
                str(self.reported_amount) if self.reported_amount is not None else None
            ),
            "residual": str(self.residual) if self.residual is not None else None,
            "knowledge_state": self.knowledge_state.value,
            "reconciled": self.reconciled,
        }


def _check_shared_grain(
    facts: tuple[NormalizedFact, ...], analysis_cutoff: datetime, identity_kind: str
) -> NormalizedFact:
    if analysis_cutoff.tzinfo is None or analysis_cutoff.utcoffset() is None:
        raise ValueError("analysis_cutoff must include a UTC offset")
    first = facts[0]
    if len({fact.fact_id for fact in facts}) != len(facts):
        raise ValueError("Reported identity normalized fact IDs must be distinct")
    if len({fact.source_fact_id for fact in facts}) != len(facts):
        raise ValueError("Reported identity source fact IDs must be distinct")
    for fact in facts:
        if fact.case_id != first.case_id or fact.scope != first.scope:
            raise ValueError(f"{identity_kind} scope mismatch")
        if fact.version_id != first.version_id or fact.period != first.period:
            raise ValueError(f"{identity_kind} version/period mismatch")
        if fact.currency != first.currency or fact.unit != first.unit:
            raise ValueError(f"{identity_kind} currency/unit mismatch")
        if (
            fact.provenance.snapshot_id != first.provenance.snapshot_id
            or fact.provenance.source_id != first.provenance.source_id
            or fact.provenance.content_sha256 != first.provenance.content_sha256
        ):
            raise ValueError(f"{identity_kind} source snapshot mismatch")
        if fact.provenance.first_public_at > analysis_cutoff:
            raise ValueError(f"{identity_kind} fact first public after analysis cutoff")
        if isinstance(fact.value, KnowledgeState):
            if fact.value is KnowledgeState.KNOWN:
                raise ValueError("KNOWN requires a decimal value")
        elif not isinstance(fact.value, Decimal) or not fact.value.is_finite():
            raise TypeError("Reported identity requires finite Decimal or knowledge state")
    return first


def _evaluate(
    identity_kind: str,
    formula: str,
    facts: tuple[NormalizedFact, ...],
    analysis_cutoff: datetime,
) -> ReportedStatementIdentity:
    first = _check_shared_grain(facts, analysis_cutoff, identity_kind)
    if identity_kind == "BALANCE_SHEET":
        if first.period.period_type != "INSTANT" or first.period.start != first.period.end:
            raise ValueError("Balance-sheet identity requires an instant period")
    elif first.period.period_type == "INSTANT":
        raise ValueError("Operating-income identity requires a duration period")

    identity = {
        "formula": formula,
        "case_id": first.case_id,
        "version_id": first.version_id,
        "scope": first.scope.key(),
        "period": first.period.key(),
        "currency": first.currency,
        "unit": first.unit,
        "normalized_fact_ids": [fact.fact_id for fact in facts],
        "source_fact_ids": [fact.source_fact_id for fact in facts],
        "source_ids": [fact.provenance.source_id for fact in facts],
        "snapshot_ids": [fact.provenance.snapshot_id for fact in facts],
        "source_content_sha256": [fact.provenance.content_sha256 for fact in facts],
        "values": [str(fact.value) for fact in facts],
    }
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    missing = [fact.value for fact in facts if isinstance(fact.value, KnowledgeState)]
    if missing:
        state = missing[0] if len(set(missing)) == 1 else KnowledgeState.UNKNOWN
        calculated = reported = residual = None
    else:
        amounts = tuple(fact.value for fact in facts)
        if identity_kind == "BALANCE_SHEET":
            calculated = amounts[0]
            reported = amounts[1]
        else:
            calculated = _exact_sum((
                amounts[0], amounts[1].copy_negate(), amounts[2].copy_negate()
            ))
            reported = amounts[3]
        residual = _exact_sum((calculated, reported.copy_negate()))
        state = KnowledgeState.KNOWN
    return ReportedStatementIdentity(
        identity_kind=identity_kind,
        output_id=f"stmt_{digest}",
        case_id=first.case_id,
        version_id=first.version_id,
        scope=first.scope,
        period=first.period,
        currency=first.currency,
        unit=first.unit,
        normalized_fact_ids=tuple(fact.fact_id for fact in facts),
        source_fact_ids=tuple(fact.source_fact_id for fact in facts),
        source_ids=tuple(fact.provenance.source_id for fact in facts),
        source_content_sha256=tuple(fact.provenance.content_sha256 for fact in facts),
        calculated_amount=calculated,
        reported_amount=reported,
        residual=residual,
        knowledge_state=state,
    )


def evaluate_reported_balance_sheet_identity(
    total_assets: NormalizedFact,
    total_liabilities_and_equity: NormalizedFact,
    *,
    analysis_cutoff: datetime,
) -> ReportedStatementIdentity:
    """Compare two published balance-sheet totals; never derive liabilities."""

    return _evaluate(
        "BALANCE_SHEET",
        BALANCE_SHEET_FORMULA,
        (total_assets, total_liabilities_and_equity),
        analysis_cutoff,
    )


def evaluate_reported_operating_income_identity(
    total_revenue: NormalizedFact,
    cost_of_sales: NormalizedFact,
    operating_sga: NormalizedFact,
    operating_income: NormalizedFact,
    *,
    analysis_cutoff: datetime,
) -> ReportedStatementIdentity:
    """Check reported revenue minus cost of sales and SG&A against reported OI."""

    return _evaluate(
        "OPERATING_INCOME",
        OPERATING_INCOME_FORMULA,
        (total_revenue, cost_of_sales, operating_sga, operating_income),
        analysis_cutoff,
    )
