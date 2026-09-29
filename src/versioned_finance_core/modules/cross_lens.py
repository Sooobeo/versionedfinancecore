"""Keep corporate value and credit feasibility as separate decision lenses.

The caller supplies reviewed module states and their output IDs. This module
only combines those states into the P0 communication convention; it never
weights values, recalculates cash, or upgrades missing evidence.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum


class CorporateValueState(StrEnum):
    FAVOURABLE = "FAVOURABLE"
    UNFAVOURABLE = "UNFAVOURABLE"
    UNKNOWN = "UNKNOWN"


class CreditFeasibilityState(StrEnum):
    FEASIBLE = "FEASIBLE"
    CONSTRAINED = "CONSTRAINED"
    UNKNOWN = "UNKNOWN"


class CrossLensState(StrEnum):
    EXECUTION_CANDIDATE = "EXECUTION_CANDIDATE"
    FUNDING_REDESIGN = "FUNDING_REDESIGN"
    VALUE_UNFAVOURABLE_BUT_SERVICEABLE = "VALUE_UNFAVOURABLE_BUT_SERVICEABLE"
    DEFER_FOR_EVIDENCE = "DEFER_FOR_EVIDENCE"
    DUAL_ADVERSE = "DUAL_ADVERSE"


@dataclass(frozen=True, slots=True)
class CrossLensDecision:
    output_id: str
    value_state: CorporateValueState
    credit_state: CreditFeasibilityState
    state: CrossLensState
    value_reference_id: str
    credit_reference_id: str
    claim_tag: str = "I"

    def as_dict(self) -> dict[str, str]:
        return {
            "output_id": self.output_id,
            "value_state": self.value_state.value,
            "credit_state": self.credit_state.value,
            "state": self.state.value,
            "value_reference_id": self.value_reference_id,
            "credit_reference_id": self.credit_reference_id,
            "claim_tag": self.claim_tag,
        }


def classify_cross_lens(
    value_state: CorporateValueState,
    credit_state: CreditFeasibilityState,
    *,
    value_reference_id: str,
    credit_reference_id: str,
) -> CrossLensDecision:
    """Classify two independently reviewed states without making a new score."""

    if not isinstance(value_state, CorporateValueState):
        raise TypeError("value_state must be CorporateValueState")
    if not isinstance(credit_state, CreditFeasibilityState):
        raise TypeError("credit_state must be CreditFeasibilityState")
    if not value_reference_id or not value_reference_id.strip():
        raise ValueError("value_reference_id is required")
    if not credit_reference_id or not credit_reference_id.strip():
        raise ValueError("credit_reference_id is required")
    if value_state is CorporateValueState.UNKNOWN or credit_state is CreditFeasibilityState.UNKNOWN:
        state = CrossLensState.DEFER_FOR_EVIDENCE
    elif value_state is CorporateValueState.FAVOURABLE:
        state = (
            CrossLensState.EXECUTION_CANDIDATE
            if credit_state is CreditFeasibilityState.FEASIBLE
            else CrossLensState.FUNDING_REDESIGN
        )
    else:
        state = (
            CrossLensState.VALUE_UNFAVOURABLE_BUT_SERVICEABLE
            if credit_state is CreditFeasibilityState.FEASIBLE
            else CrossLensState.DUAL_ADVERSE
        )
    payload = {
        "formula": "p0_cross_lens_v1",
        "value_state": value_state.value,
        "credit_state": credit_state.value,
        "value_reference_id": value_reference_id.strip(),
        "credit_reference_id": credit_reference_id.strip(),
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return CrossLensDecision(
        output_id=f"cross_lens_{digest}",
        value_state=value_state,
        credit_state=credit_state,
        state=state,
        value_reference_id=value_reference_id.strip(),
        credit_reference_id=credit_reference_id.strip(),
    )
