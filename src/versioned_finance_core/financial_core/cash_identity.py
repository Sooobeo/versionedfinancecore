"""Canonical cash identity for normalized, version-pinned financial facts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from versioned_finance_core.contracts import KnowledgeState, NormalizedFact
from versioned_finance_core.financial_core.identities import projected_closing_cash

CASH_ROLLFORWARD_FORMULA_VERSION = "cash_rollforward_v1"
CASH_ROLES = (
    "opening_cash",
    "operating_cash_flow",
    "investing_cash_flow",
    "financing_cash_flow",
    "fx_and_other",
    "closing_cash",
)


@dataclass(frozen=True)
class CashIdentitySpec:
    identity_id: str
    version_id: str
    source_fact_ids: Mapping[str, str]

    @classmethod
    def from_mapping(cls, row: Mapping[str, str]) -> CashIdentitySpec:
        identity_id = row.get("identity_id", "").strip()
        version_id = row.get("version_id", "").strip()
        if not identity_id or not version_id:
            raise ValueError("identity_id and version_id are required")
        ids = {role: row.get(f"{role}_fact_id", "").strip() for role in CASH_ROLES}
        if any(not value for value in ids.values()):
            raise ValueError("all six cash identity source fact IDs are required")
        if len(set(ids.values())) != len(CASH_ROLES):
            raise ValueError("cash identity source fact IDs must be distinct")
        return cls(identity_id, version_id, ids)


@dataclass(frozen=True)
class CashIdentityResult:
    identity_id: str
    output_id: str
    case_id: str
    version_id: str
    currency: str
    unit: str
    normalized_fact_ids: tuple[str, ...]
    calculated_closing_cash: Decimal | None
    reported_closing_cash: Decimal | None
    residual: Decimal | None
    knowledge_state: KnowledgeState

    def as_dict(self) -> dict[str, object]:
        return {
            "identity_id": self.identity_id,
            "output_id": self.output_id,
            "case_id": self.case_id,
            "version_id": self.version_id,
            "currency": self.currency,
            "unit": self.unit,
            "normalized_fact_ids": list(self.normalized_fact_ids),
            "calculated_closing_cash": (
                str(self.calculated_closing_cash)
                if self.calculated_closing_cash is not None else None
            ),
            "reported_closing_cash": (
                str(self.reported_closing_cash)
                if self.reported_closing_cash is not None else None
            ),
            "residual": str(self.residual) if self.residual is not None else None,
            "knowledge_state": self.knowledge_state.value,
        }


def evaluate_cash_identity(
    spec: CashIdentitySpec, normalized_facts: Iterable[NormalizedFact]
) -> CashIdentityResult:
    """Check a filed cash roll-forward with exact scope, version and periods."""

    by_source_id: dict[str, NormalizedFact] = {}
    for fact in normalized_facts:
        if fact.source_fact_id in by_source_id:
            raise ValueError(f"Duplicate normalized source fact: {fact.source_fact_id}")
        by_source_id[fact.source_fact_id] = fact
    try:
        facts = {role: by_source_id[source_id] for role, source_id in spec.source_fact_ids.items()}
    except KeyError as exc:
        raise ValueError(f"Missing normalized source fact: {exc.args[0]}") from exc
    first = facts["opening_cash"]
    for role, fact in facts.items():
        if fact.case_id != first.case_id or fact.scope != first.scope:
            raise ValueError(f"Cash identity scope mismatch: {role}")
        if fact.currency != first.currency or fact.unit != first.unit:
            raise ValueError(f"Cash identity currency/unit mismatch: {role}")
        if fact.version_id != spec.version_id:
            raise ValueError(f"Cash identity version mismatch: {role}")

    opening = facts["opening_cash"].period
    closing = facts["closing_cash"].period
    flow = facts["operating_cash_flow"].period
    if (
        opening.start != opening.end or closing.start != closing.end
        or opening.period_type != "INSTANT" or closing.period_type != "INSTANT"
    ):
        raise ValueError("opening and closing cash must be instant balances")
    if flow.period_type == "INSTANT":
        raise ValueError("cash flows must cover a duration")
    if opening.end != flow.start - timedelta(days=1) or closing.end != flow.end:
        raise ValueError("cash balance dates do not frame the cash-flow period")
    for role in ("investing_cash_flow", "financing_cash_flow", "fx_and_other"):
        if facts[role].period != flow:
            raise ValueError(f"Cash flow period mismatch: {role}")

    identifiers = tuple(facts[role].fact_id for role in CASH_ROLES)
    digest = hashlib.sha256(
        json.dumps(
            {
                "formula": CASH_ROLLFORWARD_FORMULA_VERSION,
                "identity_id": spec.identity_id,
                "normalized_fact_ids": identifiers,
                "values": [str(facts[role].value) for role in CASH_ROLES],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    values = [facts[role].value for role in CASH_ROLES]
    missing = [value for value in values if isinstance(value, KnowledgeState)]
    if missing:
        state = missing[0] if len(set(missing)) == 1 else KnowledgeState.UNKNOWN
        return CashIdentityResult(
            spec.identity_id, f"cash_{digest}", first.case_id, spec.version_id,
            first.currency, first.unit, identifiers,
            None, None, None, state,
        )

    opening_cash, cfo, cfi, cff, fx_other, closing_cash = values
    calculated = projected_closing_cash(opening_cash, cfo, cfi, cff, fx_other)
    return CashIdentityResult(
        spec.identity_id,
        f"cash_{digest}",
        first.case_id,
        spec.version_id,
        first.currency,
        first.unit,
        identifiers,
        calculated,
        closing_cash,
        calculated - closing_cash,
        KnowledgeState.KNOWN,
    )
