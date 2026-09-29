"""Evidence-gated, legal-entity-specific illustrative recovery waterfall.

This computes allocation of an explicitly supplied value pool. It does not
establish lien perfection, legal priority, a bankruptcy outcome, PD or LGD.
Unknown claim stacks and values yield a structure-only state with no numbers.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from versioned_finance_core.contracts import KnowledgeState

Money = Decimal | KnowledgeState


def _amount(value: Money, label: str) -> Money:
    if isinstance(value, KnowledgeState):
        if value is KnowledgeState.KNOWN:
            raise ValueError(f"{label}: KNOWN requires a Decimal amount")
        return value
    if not isinstance(value, Decimal):
        raise TypeError(f"{label} must be Decimal or KnowledgeState")
    if not value.is_finite() or value < 0:
        raise ValueError(f"{label} must be finite and nonnegative")
    return value


class RecoveryState(StrEnum):
    ILLUSTRATIVE_PUBLIC_WATERFALL = "ILLUSTRATIVE_PUBLIC_WATERFALL"
    STRUCTURE_ONLY = "STRUCTURE_ONLY"


@dataclass(frozen=True)
class RecoveryValuePool:
    legal_entity_id: str
    currency: str
    unit: str
    gross_value: Money
    value_level_costs: Money
    value_evidence_id: str
    cost_evidence_id: str


@dataclass(frozen=True)
class RecoveryClaim:
    claim_id: str
    legal_entity_id: str
    allowed_amount: Money
    priority_rank: int | None
    amount_evidence_id: str
    priority_evidence_id: str


@dataclass(frozen=True)
class RecoveryAllocation:
    claim_id: str
    priority_rank: int
    allowed_amount: Decimal
    allocated_value: Decimal


@dataclass(frozen=True)
class RecoveryResult:
    state: RecoveryState
    legal_entity_id: str
    currency: str
    unit: str
    allocations: tuple[RecoveryAllocation, ...]
    value_level_costs: Money
    unallocated_value: Money
    conservation_residual: Money
    limitation: str


def illustrative_recovery_waterfall(
    pool: RecoveryValuePool,
    claims: Iterable[RecoveryClaim],
    *, claim_stack_complete: bool,
    claim_stack_basis_id: str,
) -> RecoveryResult:
    """Allocate a reviewed value pool by sourced rank, pro rata within rank.

    Value-level costs are removed once before claims. Costs already represented
    as priority claims must be excluded from ``value_level_costs`` by the
    caller. A guarantee against another entity requires a separate pool.
    """

    if not pool.legal_entity_id or not pool.currency or not pool.unit:
        raise ValueError("legal entity, currency and unit are required")
    gross = _amount(pool.gross_value, "gross_value")
    costs = _amount(pool.value_level_costs, "value_level_costs")
    entries = tuple(claims)
    if not entries:
        raise ValueError("at least one claim is required")
    ids: set[str] = set()
    for claim in entries:
        if not claim.claim_id or claim.claim_id in ids:
            raise ValueError("claim IDs must be nonempty and unique")
        ids.add(claim.claim_id)
        if claim.legal_entity_id != pool.legal_entity_id:
            raise ValueError("guarantor or other-entity claims need a separate value pool")
        _amount(claim.allowed_amount, "allowed_amount")
        if claim.priority_rank is not None:
            if isinstance(claim.priority_rank, bool) or not isinstance(claim.priority_rank, int):
                raise TypeError("priority_rank must be an integer or None")
            if claim.priority_rank < 0:
                raise ValueError("priority_rank cannot be negative")
    if isinstance(gross, Decimal) and isinstance(costs, Decimal) and costs > gross:
        raise ValueError("value-level costs exceed gross value")
    evidence_complete = bool(
        claim_stack_complete and claim_stack_basis_id
        and pool.value_evidence_id and pool.cost_evidence_id
        and isinstance(gross, Decimal) and isinstance(costs, Decimal)
        and all(
            isinstance(claim.allowed_amount, Decimal)
            and claim.priority_rank is not None
            and claim.amount_evidence_id and claim.priority_evidence_id
            for claim in entries
        )
    )
    if not evidence_complete:
        return RecoveryResult(
            RecoveryState.STRUCTURE_ONLY, pool.legal_entity_id, pool.currency,
            pool.unit, (), KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA,
            KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA,
            KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA,
            "Value, complete claim stack, priority or evidence is unavailable.",
        )
    available = gross - costs
    allocations: list[RecoveryAllocation] = []
    for rank in sorted({claim.priority_rank for claim in entries}):
        tier = sorted(
            (claim for claim in entries if claim.priority_rank == rank),
            key=lambda claim: claim.claim_id,
        )
        tier_total = sum((claim.allowed_amount for claim in tier), Decimal(0))
        distributed = min(available, tier_total)
        allocated_in_tier = Decimal(0)
        for index, claim in enumerate(tier):
            if index == len(tier) - 1:
                amount = distributed - allocated_in_tier
            elif tier_total == 0:
                amount = Decimal(0)
            else:
                amount = distributed * claim.allowed_amount / tier_total
            allocated_in_tier += amount
            allocations.append(RecoveryAllocation(
                claim.claim_id, rank, claim.allowed_amount, amount,
            ))
        available -= distributed
    allocated = sum((item.allocated_value for item in allocations), Decimal(0))
    residual = gross - costs - allocated - available
    if residual != 0:
        raise ArithmeticError("recovery value conservation failed")
    return RecoveryResult(
        RecoveryState.ILLUSTRATIVE_PUBLIC_WATERFALL,
        pool.legal_entity_id, pool.currency, pool.unit,
        tuple(allocations), costs, available, residual,
        "Illustrative public-data allocation; legal enforceability is not established.",
    )
