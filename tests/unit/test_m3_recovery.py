"""Synthetic priority and evidence-gate checks; no real claim is valued."""

from decimal import Decimal

import pytest

from versioned_finance_core.contracts import KnowledgeState
from versioned_finance_core.modules.m3 import (
    RecoveryClaim,
    RecoveryState,
    RecoveryValuePool,
    illustrative_recovery_waterfall,
)


def _pool(value: Decimal | KnowledgeState = Decimal(100)) -> RecoveryValuePool:
    return RecoveryValuePool(
        "synthetic_obligor", "KRW", "KRW", value, Decimal(10),
        "synthetic_value_source", "synthetic_cost_source",
    )


def _claim(claim_id: str, amount: int, rank: int) -> RecoveryClaim:
    return RecoveryClaim(
        claim_id, "synthetic_obligor", Decimal(amount), rank,
        f"amount_source_{claim_id}", f"priority_source_{claim_id}",
    )


def test_waterfall_allocates_by_rank_and_pro_rata_with_exact_conservation() -> None:
    result = illustrative_recovery_waterfall(
        _pool(), (_claim("senior_a", 60, 1), _claim("senior_b", 60, 1),
                  _claim("junior", 40, 2)),
        claim_stack_complete=True, claim_stack_basis_id="synthetic_claim_register",
    )
    assert result.state is RecoveryState.ILLUSTRATIVE_PUBLIC_WATERFALL
    by_id = {item.claim_id: item.allocated_value for item in result.allocations}
    assert by_id == {
        "senior_a": Decimal(45),
        "senior_b": Decimal(45),
        "junior": Decimal(0),
    }
    assert result.unallocated_value == Decimal(0)
    assert result.conservation_residual == Decimal(0)


def test_incomplete_stack_or_unknown_value_has_no_numeric_recovery() -> None:
    claims = (_claim("senior", 50, 1),)
    incomplete = illustrative_recovery_waterfall(
        _pool(), claims, claim_stack_complete=False, claim_stack_basis_id="",
    )
    assert incomplete.state is RecoveryState.STRUCTURE_ONLY
    assert incomplete.allocations == ()
    assert incomplete.conservation_residual is KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA
    unknown = illustrative_recovery_waterfall(
        _pool(KnowledgeState.UNKNOWN), claims,
        claim_stack_complete=True, claim_stack_basis_id="synthetic_claim_register",
    )
    assert unknown.state is RecoveryState.STRUCTURE_ONLY
    assert unknown.unallocated_value is KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA


def test_guarantor_claim_requires_separate_entity_pool_and_claims_are_unique() -> None:
    other_entity = RecoveryClaim(
        "guarantee", "synthetic_guarantor", Decimal(50), 1, "amount", "priority",
    )
    with pytest.raises(ValueError, match="separate value pool"):
        illustrative_recovery_waterfall(
            _pool(), (other_entity,),
            claim_stack_complete=True, claim_stack_basis_id="synthetic_claim_register",
        )
    with pytest.raises(ValueError, match="unique"):
        illustrative_recovery_waterfall(
            _pool(), (_claim("same", 10, 1), _claim("same", 20, 2)),
            claim_stack_complete=True, claim_stack_basis_id="synthetic_claim_register",
        )


def test_unallocated_value_is_preserved_and_excess_cost_rejected() -> None:
    result = illustrative_recovery_waterfall(
        _pool(), (_claim("senior", 20, 1),),
        claim_stack_complete=True, claim_stack_basis_id="synthetic_claim_register",
    )
    assert result.unallocated_value == Decimal(70)
    assert result.conservation_residual == Decimal(0)
    with pytest.raises(ValueError, match="costs exceed"):
        illustrative_recovery_waterfall(
            RecoveryValuePool("synthetic_obligor", "KRW", "KRW", Decimal(1),
                              Decimal(2), "value", "cost"),
            (_claim("senior", 20, 1),),
            claim_stack_complete=True, claim_stack_basis_id="synthetic_claim_register",
        )
