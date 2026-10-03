"""Pure completeness checks for public M2 evidence before valuation.

This module deliberately does not turn a partly disclosed contract, grant, or
project forecast into a cash-flow assumption.  It records which of the inputs
needed for a dated ``option world - status quo world`` comparison are actually
complete.  Adapters own CSV parsing and source-receipt checks; this module only
evaluates already typed evidence statements.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from versioned_finance_core.contracts import KnowledgeState


class M2PublicEvidenceCriterion(StrEnum):
    """Evidence categories needed before an M2 public-data valuation."""

    STATUS_QUO_CASH_PATH = "STATUS_QUO_CASH_PATH"
    OPTION_CASH_PATH = "OPTION_CASH_PATH"
    COMMON_AS_OF_TIMING = "COMMON_AS_OF_TIMING"
    AFTER_TAX_BASIS = "AFTER_TAX_BASIS"
    LEGAL_ECONOMIC_SCOPE = "LEGAL_ECONOMIC_SCOPE"
    FUNDING_ACCESS = "FUNDING_ACCESS"
    EXECUTABLE_OPTION_RIGHTS = "EXECUTABLE_OPTION_RIGHTS"


class PublicEvidenceCoverage(StrEnum):
    """Completeness of a criterion, not the amount of a cash-flow item."""

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"


@dataclass(frozen=True, slots=True)
class PublicM2EvidenceItem:
    """One source-linked public fact or bounded evidence-gap statement."""

    evidence_id: str
    criterion: M2PublicEvidenceCriterion
    coverage: PublicEvidenceCoverage
    source_id: str | None
    statement: str
    limitation: str


@dataclass(frozen=True, slots=True)
class PublicM2EvidenceAssessment:
    """Fail-closed readiness result for a public M2 comparison.

    ``incremental_cashflow_state`` says only whether the public evidence is
    sufficient to construct dated, same-scope incremental cash flows.  It is
    never an NPV, approval, or conclusion about an undisclosed obligation.
    """

    criterion_coverage: tuple[tuple[M2PublicEvidenceCriterion, PublicEvidenceCoverage], ...]
    incremental_cashflow_state: KnowledgeState
    funding_feasibility_state: KnowledgeState
    decision_state: KnowledgeState
    blocking_criteria: tuple[M2PublicEvidenceCriterion, ...]
    source_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "criterion_coverage": [
                {"criterion": criterion.value, "coverage": coverage.value}
                for criterion, coverage in self.criterion_coverage
            ],
            "incremental_cashflow_state": self.incremental_cashflow_state.value,
            "funding_feasibility_state": self.funding_feasibility_state.value,
            "decision_state": self.decision_state.value,
            "blocking_criteria": [criterion.value for criterion in self.blocking_criteria],
            "source_ids": list(self.source_ids),
        }


_INCREMENTAL_CASHFLOW_CRITERIA = (
    M2PublicEvidenceCriterion.STATUS_QUO_CASH_PATH,
    M2PublicEvidenceCriterion.OPTION_CASH_PATH,
    M2PublicEvidenceCriterion.COMMON_AS_OF_TIMING,
    M2PublicEvidenceCriterion.AFTER_TAX_BASIS,
    M2PublicEvidenceCriterion.LEGAL_ECONOMIC_SCOPE,
)
_FUNDING_CRITERIA = (
    M2PublicEvidenceCriterion.FUNDING_ACCESS,
    M2PublicEvidenceCriterion.EXECUTABLE_OPTION_RIGHTS,
)
_ALL_CRITERIA = _INCREMENTAL_CASHFLOW_CRITERIA + _FUNDING_CRITERIA
_COVERAGE_RANK = {
    PublicEvidenceCoverage.MISSING: 0,
    PublicEvidenceCoverage.PARTIAL: 1,
    PublicEvidenceCoverage.COMPLETE: 2,
}


def _required(value: str, field: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field} is required without surrounding whitespace")


def _state_for(
    coverage: dict[M2PublicEvidenceCriterion, PublicEvidenceCoverage],
    criteria: tuple[M2PublicEvidenceCriterion, ...],
) -> KnowledgeState:
    if all(coverage[criterion] is PublicEvidenceCoverage.COMPLETE for criterion in criteria):
        return KnowledgeState.KNOWN
    return KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA


def assess_public_m2_evidence(
    items: Iterable[PublicM2EvidenceItem],
) -> PublicM2EvidenceAssessment:
    """Assess public M2 input completeness without inferring cash amounts.

    Multiple items can describe one criterion.  A criterion becomes COMPLETE
    only when *every* supplied item for it explicitly says COMPLETE.  An older
    PARTIAL or MISSING item therefore keeps the criterion unresolved until a
    separate, explicit supersession process changes the evidence register.
    A MISSING item is a case evidence-record gap, not a claim that no
    obligation exists outside the reviewed evidence.
    """

    entries = tuple(items)
    if not entries:
        raise ValueError("at least one public M2 evidence item is required")
    seen_ids: set[str] = set()
    coverage_by_criterion: dict[
        M2PublicEvidenceCriterion, PublicEvidenceCoverage | None
    ] = {
        criterion: None for criterion in _ALL_CRITERIA
    }
    source_ids: set[str] = set()
    for item in entries:
        if not isinstance(item, PublicM2EvidenceItem):
            raise TypeError("public M2 evidence items must be PublicM2EvidenceItem values")
        _required(item.evidence_id, "evidence_id")
        _required(item.statement, "statement")
        _required(item.limitation, "limitation")
        if item.evidence_id in seen_ids:
            raise ValueError(f"duplicate public M2 evidence_id: {item.evidence_id}")
        seen_ids.add(item.evidence_id)
        if not isinstance(item.criterion, M2PublicEvidenceCriterion):
            raise TypeError("public M2 evidence criterion is invalid")
        if not isinstance(item.coverage, PublicEvidenceCoverage):
            raise TypeError("public M2 evidence coverage is invalid")
        if item.coverage is not PublicEvidenceCoverage.MISSING:
            if item.source_id is None:
                raise ValueError("complete or partial public evidence requires a source_id")
            _required(item.source_id, "source_id")
            source_ids.add(item.source_id)
        elif item.source_id is not None:
            _required(item.source_id, "source_id")
            source_ids.add(item.source_id)
        prior = coverage_by_criterion[item.criterion]
        if prior is None or _COVERAGE_RANK[item.coverage] < _COVERAGE_RANK[prior]:
            coverage_by_criterion[item.criterion] = item.coverage

    ordered_coverage = tuple(
        (criterion, coverage_by_criterion[criterion] or PublicEvidenceCoverage.MISSING)
        for criterion in _ALL_CRITERIA
    )
    resolved_coverage = dict(ordered_coverage)
    incremental_state = _state_for(resolved_coverage, _INCREMENTAL_CASHFLOW_CRITERIA)
    funding_state = _state_for(resolved_coverage, _FUNDING_CRITERIA)
    decision_state = (
        KnowledgeState.KNOWN
        if incremental_state is KnowledgeState.KNOWN and funding_state is KnowledgeState.KNOWN
        else KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA
    )
    return PublicM2EvidenceAssessment(
        criterion_coverage=ordered_coverage,
        incremental_cashflow_state=incremental_state,
        funding_feasibility_state=funding_state,
        decision_state=decision_state,
        blocking_criteria=tuple(
            criterion
            for criterion, coverage in ordered_coverage
            if coverage is not PublicEvidenceCoverage.COMPLETE
        ),
        source_ids=tuple(sorted(source_ids)),
    )
