"""Known-answer and fail-closed tests for public M2 evidence completeness."""

from __future__ import annotations

import pytest

from versioned_finance_core.contracts import KnowledgeState
from versioned_finance_core.modules.m2 import (
    M2PublicEvidenceCriterion,
    PublicEvidenceCoverage,
    PublicM2EvidenceItem,
    assess_public_m2_evidence,
)


def _item(
    criterion: M2PublicEvidenceCriterion,
    coverage: PublicEvidenceCoverage,
    *,
    evidence_id: str | None = None,
    source_id: str | None = "official_source",
) -> PublicM2EvidenceItem:
    return PublicM2EvidenceItem(
        evidence_id=evidence_id or criterion.value.lower(),
        criterion=criterion,
        coverage=coverage,
        source_id=source_id,
        statement="A bounded source statement.",
        limitation="A bounded limitation.",
    )


def test_complete_public_evidence_is_ready_without_calculating_an_npv() -> None:
    result = assess_public_m2_evidence(
        _item(criterion, PublicEvidenceCoverage.COMPLETE)
        for criterion in M2PublicEvidenceCriterion
    )

    assert result.incremental_cashflow_state is KnowledgeState.KNOWN
    assert result.funding_feasibility_state is KnowledgeState.KNOWN
    assert result.decision_state is KnowledgeState.KNOWN
    assert result.blocking_criteria == ()
    assert result.source_ids == ("official_source",)


def test_partial_or_missing_evidence_fails_closed_and_preserves_all_blockers() -> None:
    result = assess_public_m2_evidence(
        (
            _item(
                M2PublicEvidenceCriterion.STATUS_QUO_CASH_PATH,
                PublicEvidenceCoverage.PARTIAL,
            ),
            _item(
                M2PublicEvidenceCriterion.OPTION_CASH_PATH,
                PublicEvidenceCoverage.MISSING,
                source_id=None,
            ),
        )
    )

    assert result.incremental_cashflow_state is KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA
    assert result.funding_feasibility_state is KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA
    assert result.decision_state is KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA
    assert result.blocking_criteria == (
        M2PublicEvidenceCriterion.STATUS_QUO_CASH_PATH,
        M2PublicEvidenceCriterion.OPTION_CASH_PATH,
        M2PublicEvidenceCriterion.COMMON_AS_OF_TIMING,
        M2PublicEvidenceCriterion.AFTER_TAX_BASIS,
        M2PublicEvidenceCriterion.LEGAL_ECONOMIC_SCOPE,
        M2PublicEvidenceCriterion.FUNDING_ACCESS,
        M2PublicEvidenceCriterion.EXECUTABLE_OPTION_RIGHTS,
    )


def test_complete_or_partial_evidence_requires_source_and_duplicate_ids_fail() -> None:
    with pytest.raises(ValueError, match="requires a source_id"):
        assess_public_m2_evidence(
            (
                _item(
                    M2PublicEvidenceCriterion.STATUS_QUO_CASH_PATH,
                    PublicEvidenceCoverage.PARTIAL,
                    source_id=None,
                ),
            )
        )


def test_later_complete_item_does_not_silently_resolve_an_existing_partial_item() -> None:
    result = assess_public_m2_evidence(
        (
            _item(
                M2PublicEvidenceCriterion.STATUS_QUO_CASH_PATH,
                PublicEvidenceCoverage.PARTIAL,
                evidence_id="old_partial",
            ),
            _item(
                M2PublicEvidenceCriterion.STATUS_QUO_CASH_PATH,
                PublicEvidenceCoverage.COMPLETE,
                evidence_id="new_complete",
            ),
        )
    )

    coverage = dict(result.criterion_coverage)
    assert coverage[M2PublicEvidenceCriterion.STATUS_QUO_CASH_PATH] is PublicEvidenceCoverage.PARTIAL
    assert result.incremental_cashflow_state is KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA

    with pytest.raises(ValueError, match="duplicate public M2 evidence_id"):
        assess_public_m2_evidence(
            (
                _item(
                    M2PublicEvidenceCriterion.STATUS_QUO_CASH_PATH,
                    PublicEvidenceCoverage.COMPLETE,
                    evidence_id="same",
                ),
                _item(
                    M2PublicEvidenceCriterion.OPTION_CASH_PATH,
                    PublicEvidenceCoverage.COMPLETE,
                    evidence_id="same",
                ),
            )
        )
