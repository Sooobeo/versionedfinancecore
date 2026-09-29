from __future__ import annotations

import pytest

from versioned_finance_core.modules.cross_lens import (
    CorporateValueState,
    CreditFeasibilityState,
    CrossLensState,
    classify_cross_lens,
)


@pytest.mark.parametrize(
    ("value", "credit", "expected"),
    [
        ("FAVOURABLE", "FEASIBLE", CrossLensState.EXECUTION_CANDIDATE),
        ("FAVOURABLE", "CONSTRAINED", CrossLensState.FUNDING_REDESIGN),
        ("UNFAVOURABLE", "FEASIBLE", CrossLensState.VALUE_UNFAVOURABLE_BUT_SERVICEABLE),
        ("UNFAVOURABLE", "CONSTRAINED", CrossLensState.DUAL_ADVERSE),
        ("UNKNOWN", "FEASIBLE", CrossLensState.DEFER_FOR_EVIDENCE),
        ("FAVOURABLE", "UNKNOWN", CrossLensState.DEFER_FOR_EVIDENCE),
    ],
)
def test_cross_lens_preserves_separate_states_and_references(value, credit, expected) -> None:
    result = classify_cross_lens(
        CorporateValueState(value), CreditFeasibilityState(credit),
        value_reference_id="m2_output_1", credit_reference_id="m3_output_2",
    )
    assert result.state is expected
    assert result.as_dict()["value_reference_id"] == "m2_output_1"
    assert result.as_dict()["credit_reference_id"] == "m3_output_2"
    assert result.as_dict()["claim_tag"] == "I"


def test_cross_lens_identity_is_deterministic_and_requires_provenance() -> None:
    args = (
        CorporateValueState.FAVOURABLE,
        CreditFeasibilityState.CONSTRAINED,
    )
    first = classify_cross_lens(*args, value_reference_id="v1", credit_reference_id="c1")
    assert first == classify_cross_lens(*args, value_reference_id="v1", credit_reference_id="c1")
    second = classify_cross_lens(*args, value_reference_id="v2", credit_reference_id="c1")
    assert first.output_id != second.output_id
    with pytest.raises(ValueError, match="value_reference_id"):
        classify_cross_lens(*args, value_reference_id="", credit_reference_id="c1")
