"""Independent arithmetic audits of disclosed credit tables, not a cash forecast.

Inputs are references to Core-normalized facts. Recalculation is solely an
independent disclosure reconciliation; no balance or forecast is republished
as a new canonical financial state or legally drawable funding source.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from versioned_finance_core.contracts import KnowledgeState
from versioned_finance_core.financial_core.identities import _exact_sum


@dataclass(frozen=True)
class PublicCreditFact:
    fact_id: str
    metric_id: str
    value: Decimal | KnowledgeState
    currency: str
    unit: str
    scope_key: tuple[str, ...]
    period_start: date
    period_end: date
    period_type: str


def _audit(
    audit_id: str, terms: tuple[tuple[PublicCreditFact, int], ...],
    target: PublicCreditFact | None, missing: tuple[str, ...] = (),
) -> dict[str, object]:
    facts = tuple(fact for fact, _ in terms) + ((target,) if target else ())
    if facts and any(
        (fact.currency, fact.unit, fact.scope_key)
        != (facts[0].currency, facts[0].unit, facts[0].scope_key) for fact in facts
    ):
        raise ValueError(f"Credit disclosure audit scope/currency/unit mismatch: {audit_id}")
    unknown = missing or target is None or any(
        not isinstance(fact.value, Decimal) for fact in facts
    )
    if unknown:
        calculated = residual = "UNKNOWN"
        state = "NOT_TESTABLE_FROM_PUBLIC_DATA"
    else:
        calculated_value = _exact_sum(
            fact.value if sign == 1 else fact.value.copy_negate() for fact, sign in terms
        )
        residual_value = _exact_sum((calculated_value, target.value.copy_negate()))
        calculated, residual = str(calculated_value), str(residual_value)
        state = "PASS" if residual_value == 0 else "FAIL"
    return {
        "audit_id": audit_id, "state": state, "claim_tag": "D",
        "purpose": "INDEPENDENT_DISCLOSURE_RECONCILIATION_NOT_FORECAST",
        "calculated_value": calculated, "residual": residual,
        "disclosed_total": str(target.value) if target else "UNKNOWN",
        "currency": facts[0].currency if facts else "UNKNOWN",
        "unit": facts[0].unit if facts else "UNKNOWN",
        "normalized_fact_ids": [fact.fact_id for fact in facts],
        "missing_metrics": list(missing),
    }


def audit_public_credit_disclosures(
    facts: Iterable[PublicCreditFact], *, balance_date: date,
) -> tuple[dict[str, object], ...]:
    """Audit published liquidity, face/carrying and maturity arithmetic.

    Metric names are explicit semantic definitions. Positive utilization
    magnitudes are subtracted; signed carrying adjustments are added. Missing
    categories are not replaced by zero and exact amounts must reconcile.
    """
    entries = tuple(facts)
    if len({fact.fact_id for fact in entries}) != len(entries):
        raise ValueError("Duplicate normalized credit fact ID")
    keys = [(fact.metric_id, fact.period_start, fact.period_end) for fact in entries]
    if len(set(keys)) != len(keys):
        raise ValueError("Ambiguous normalized credit metric/period")
    for fact in entries:
        if not isinstance(fact.value, (Decimal, KnowledgeState)):
            raise TypeError("Credit amounts require Decimal or explicit knowledge state")
        if isinstance(fact.value, Decimal) and not fact.value.is_finite():
            raise ValueError("Credit amounts must be finite")
        if fact.period_start > fact.period_end:
            raise ValueError("Invalid credit disclosure period")
    instants = {fact.metric_id: fact for fact in entries
                if fact.period_type == "INSTANT" and fact.period_end == balance_date
                and fact.period_start == balance_date}

    def identity(audit_id: str, definition: tuple[tuple[str, int], ...], total: str):
        missing = tuple(metric for metric, _ in definition if metric not in instants)
        if total not in instants:
            missing += (total,)
        return _audit(audit_id, tuple((instants[metric], sign) for metric, sign in definition
                                     if metric in instants), instants.get(total), missing)

    checks = [
        identity("reported_available_liquidity", (
            ("liquidity_cash", 1), ("liquidity_committed_abs", 1),
            ("liquidity_committed_unsecured", 1), ("liquidity_restricted_cash", -1),
            ("liquidity_abs_utilized", -1), ("liquidity_unsecured_utilized", -1),
        ), "liquidity_available"),
        identity("reported_net_liquidity", (
            ("liquidity_available", 1), ("liquidity_other_adjustments", 1),
        ), "liquidity_net_available"),
        identity("reported_face_to_carrying", (
            ("debt_gross_principal", 1), ("debt_unamortized_cost_adjustment", 1),
            ("debt_fair_value_adjustment", 1),
        ), "debt_carrying_amount"),
    ]
    principal_metrics = ("maturity_unsecured_principal", "maturity_asset_backed_principal")
    buckets = tuple(fact for fact in entries if fact.metric_id in principal_metrics)
    for metric in principal_metrics:
        selected = sorted((fact for fact in buckets if fact.metric_id == metric),
                          key=lambda fact: fact.period_start)
        previous_end = balance_date
        for fact in selected:
            if fact.period_type != "MATURITY_BUCKET" or fact.period_start <= previous_end:
                raise ValueError("Maturity buckets must be nonoverlapping and after balance date")
            if isinstance(fact.value, Decimal) and fact.value < 0:
                raise ValueError("Principal maturity cannot be negative")
            previous_end = fact.period_end
    checks.append(_audit(
        "reported_principal_maturity_total", tuple((fact, 1) for fact in buckets),
        instants.get("debt_gross_principal"),
        tuple(metric for metric in principal_metrics
              if not any(fact.metric_id == metric for fact in buckets)),
    ))
    return tuple(checks)


def audit_nominal_capacity(
    *, commitment: Decimal | KnowledgeState, drawn: Decimal | KnowledgeState,
    disclosed_undrawn: Decimal | KnowledgeState,
) -> dict[str, str]:
    """Check reported nominal subtraction only; never infer legal drawability."""
    for value in (commitment, drawn, disclosed_undrawn):
        if not isinstance(value, (Decimal, KnowledgeState)):
            raise TypeError("Facility amounts require Decimal or explicit knowledge state")
        if isinstance(value, Decimal) and (not value.is_finite() or value < 0):
            raise ValueError("Facility amounts must be finite and nonnegative")
    if not all(isinstance(value, Decimal) for value in (commitment, drawn, disclosed_undrawn)):
        return {"state": "NOT_TESTABLE_FROM_PUBLIC_DATA", "residual": "UNKNOWN",
                "drawable_amount": "UNKNOWN"}
    residual = _exact_sum((commitment, drawn.copy_negate(), disclosed_undrawn.copy_negate()))
    return {"state": "PASS" if residual == 0 else "FAIL", "residual": str(residual),
            "drawable_amount": "UNKNOWN"}
