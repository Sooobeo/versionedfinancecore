"""P1 method choice and valuation diagnostics over pinned M1/Core outputs.

These records describe a case-specific analysis; they do not make a numeric
valuation publishable. Source quality, forecast fitness and independent review
remain explicit gates in :mod:`valuation` and the release pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from versioned_finance_core.contracts.enums import GateStatus
from versioned_finance_core.modules.m1.valuation import (
    DcfInputs,
    DcfResult,
    ValuationEligibilityResult,
    ValuationEligibilityReview,
    _assess,
    _finite,
    _nonempty,
    _output_id,
    value_perpetuity_dcf,
)

METHOD_REVIEW_CHECKS = frozenset(
    {
        "case_purpose_and_company_fit",
        "data_quality_and_vintage",
        "included_and_excluded_methods_justified",
    }
)


class ValuationMethod(StrEnum):
    DCF = "DCF"
    TRADING_COMPS = "TRADING_COMPS"


class MethodDisposition(StrEnum):
    SELECTED = "SELECTED"
    EXCLUDED = "EXCLUDED"


@dataclass(frozen=True, slots=True)
class MethodChoice:
    method: ValuationMethod
    disposition: MethodDisposition
    rationale: str
    evidence_or_assumption_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.method, ValuationMethod):
            raise TypeError("method must be ValuationMethod")
        if not isinstance(self.disposition, MethodDisposition):
            raise TypeError("disposition must be MethodDisposition")
        _nonempty(self.rationale, "rationale")
        if not isinstance(self.evidence_or_assumption_ids, tuple) or not self.evidence_or_assumption_ids:
            raise ValueError("method choice requires evidence or assumption IDs")
        for evidence_id in self.evidence_or_assumption_ids:
            _nonempty(evidence_id, "evidence_or_assumption_id")
        if len(set(self.evidence_or_assumption_ids)) != len(self.evidence_or_assumption_ids):
            raise ValueError("duplicate method evidence or assumption ID")


@dataclass(frozen=True, slots=True)
class MethodSelectionResult:
    case_id: str
    information_cutoff: datetime
    choices: tuple[MethodChoice, ...]
    selected_methods: tuple[ValuationMethod, ...]
    output_id: str
    eligibility_status: GateStatus = GateStatus.NOT_EVALUATED


def select_valuation_methods(
    *, case_id: str, information_cutoff: datetime, choices: tuple[MethodChoice, ...]
) -> MethodSelectionResult:
    """Record both selected and excluded methods without fixed weights or counts.

    Selection is a documented judgment. It is not an eligibility assertion.
    Missing methods must be stated as exclusions, so the review can challenge
    their rationale rather than silently assuming a mandatory DCF/peer pair.
    """

    _nonempty(case_id, "case_id")
    _aware(information_cutoff, "information_cutoff")
    if not isinstance(choices, tuple) or len(choices) != len(ValuationMethod):
        raise ValueError("state a choice for every supported valuation method")
    if any(not isinstance(choice, MethodChoice) for choice in choices):
        raise TypeError("choices must contain MethodChoice")
    by_method = {choice.method: choice for choice in choices}
    if len(by_method) != len(ValuationMethod):
        raise ValueError("duplicate or missing method choice")
    selected = tuple(
        method for method in ValuationMethod
        if by_method[method].disposition is MethodDisposition.SELECTED
    )
    ordered = tuple(by_method[method] for method in ValuationMethod)
    output_id = _output_id(
        "m1_method_selection",
        {
            "schema_version": 1,
            "case_id": case_id,
            "information_cutoff": information_cutoff.astimezone(UTC).isoformat(),
            "choices": [
                {
                    "method": choice.method.value,
                    "disposition": choice.disposition.value,
                    "rationale": choice.rationale,
                    "evidence_or_assumption_ids": choice.evidence_or_assumption_ids,
                }
                for choice in ordered
            ],
        },
    )
    return MethodSelectionResult(
        case_id, information_cutoff, ordered, selected, output_id
    )


def assess_method_selection(
    selection: MethodSelectionResult, review: ValuationEligibilityReview
) -> ValuationEligibilityResult:
    """Require an identified reviewer and all method-choice checks to pass."""

    additional = () if selection.selected_methods else ("no_selected_valuation_method",)
    return _assess(
        selection.output_id, review, METHOD_REVIEW_CHECKS, additional_failed=additional
    )


@dataclass(frozen=True, slots=True)
class SupportedParameterPoint:
    value: Decimal
    evidence_or_assumption_id: str
    basis_source_ids: tuple[str, ...]
    available_at: datetime
    rationale: str

    def __post_init__(self) -> None:
        _finite(self.value, "value")
        _nonempty(self.evidence_or_assumption_id, "evidence_or_assumption_id")
        _nonempty(self.rationale, "rationale")
        _aware(self.available_at, "available_at")
        if not isinstance(self.basis_source_ids, tuple) or not self.basis_source_ids:
            raise ValueError("sensitivity point requires a documented source basis")
        for source_id in self.basis_source_ids:
            _nonempty(source_id, "basis_source_id")
        if len(set(self.basis_source_ids)) != len(self.basis_source_ids):
            raise ValueError("duplicate basis source ID")


@dataclass(frozen=True, slots=True)
class DcfSensitivityCell:
    discount_rate: Decimal
    terminal_growth_rate: Decimal
    discount_rate_assumption_id: str
    terminal_growth_assumption_id: str
    dcf_output_id: str
    value: Decimal


@dataclass(frozen=True, slots=True)
class DcfSensitivityResult:
    base_dcf_output_id: str
    forecast_version_id: str
    cells: tuple[DcfSensitivityCell, ...]
    output_id: str
    eligibility_status: GateStatus = GateStatus.NOT_EVALUATED


def evaluate_dcf_parameter_sensitivity(
    inputs: DcfInputs,
    *,
    information_cutoff: datetime,
    discount_rates: tuple[SupportedParameterPoint, ...],
    terminal_growth_rates: tuple[SupportedParameterPoint, ...],
) -> DcfSensitivityResult:
    """Value an evidence-bounded rate/g grid over unchanged Core cash flows.

    This is a valuation-parameter diagnostic, not a coherent operating scenario.
    Invalid WACC/g pairs fail instead of being silently clipped or omitted.
    """

    _aware(information_cutoff, "information_cutoff")
    if not discount_rates or not terminal_growth_rates:
        raise ValueError("both sensitivity axes require at least one point")
    for name, points in (("discount_rates", discount_rates), ("terminal_growth_rates", terminal_growth_rates)):
        if not isinstance(points, tuple) or any(
            not isinstance(point, SupportedParameterPoint) for point in points
        ):
            raise TypeError(f"{name} must be a tuple of SupportedParameterPoint")
        if len({point.value for point in points}) != len(points):
            raise ValueError(f"{name} contains duplicate values")
        if any(point.available_at > information_cutoff for point in points):
            raise ValueError(f"{name} includes a point unavailable at cutoff")
    if inputs.annual_discount_rate not in {point.value for point in discount_rates}:
        raise ValueError("discount rate axis must include the base rate")
    if inputs.terminal_growth_rate not in {point.value for point in terminal_growth_rates}:
        raise ValueError("terminal growth axis must include the base growth rate")
    base_rate_point = next(
        point for point in discount_rates if point.value == inputs.annual_discount_rate
    )
    base_growth_point = next(
        point for point in terminal_growth_rates if point.value == inputs.terminal_growth_rate
    )
    if base_rate_point.evidence_or_assumption_id != inputs.discount_rate_assumption_id:
        raise ValueError("base discount rate assumption ID differs from DCF input")
    if base_growth_point.evidence_or_assumption_id != inputs.terminal_state_assumption_id:
        raise ValueError("base terminal state assumption ID differs from DCF input")

    base = value_perpetuity_dcf(inputs)
    cells: list[DcfSensitivityCell] = []
    for rate_point in discount_rates:
        for growth_point in terminal_growth_rates:
            result = value_perpetuity_dcf(
                replace(
                    inputs,
                    annual_discount_rate=rate_point.value,
                    discount_rate_assumption_id=rate_point.evidence_or_assumption_id,
                    terminal_growth_rate=growth_point.value,
                    terminal_state_assumption_id=growth_point.evidence_or_assumption_id,
                )
            )
            cells.append(
                DcfSensitivityCell(
                    rate_point.value,
                    growth_point.value,
                    rate_point.evidence_or_assumption_id,
                    growth_point.evidence_or_assumption_id,
                    result.output_id,
                    result.total_value,
                )
            )
    cells.sort(key=lambda cell: (cell.discount_rate, cell.terminal_growth_rate))
    ordered_cells = tuple(cells)
    output_id = _output_id(
        "m1_dcf_sensitivity",
        {
            "schema_version": 1,
            "base_dcf_output_id": base.output_id,
            "information_cutoff": information_cutoff.astimezone(UTC).isoformat(),
            "rate_points": [_point_payload(point) for point in sorted(discount_rates, key=lambda p: p.value)],
            "growth_points": [_point_payload(point) for point in sorted(terminal_growth_rates, key=lambda p: p.value)],
            "cells": [
                (str(cell.discount_rate), str(cell.terminal_growth_rate), cell.dcf_output_id)
                for cell in ordered_cells
            ],
        },
    )
    return DcfSensitivityResult(
        base.output_id, inputs.forecast_version_id, ordered_cells, output_id
    )


@dataclass(frozen=True, slots=True)
class CoherentScenarioValue:
    baseline_output_id: str
    scenario_output_id: str
    driver_id: str
    driver_value: Decimal
    valuation_output_id: str
    valuation_value: Decimal
    value_claim: str

    def __post_init__(self) -> None:
        for name in (
            "baseline_output_id", "scenario_output_id", "driver_id",
            "valuation_output_id", "value_claim",
        ):
            _nonempty(getattr(self, name), name)
        _finite(self.driver_value, "driver_value")
        _finite(self.valuation_value, "valuation_value")


@dataclass(frozen=True, slots=True)
class ThesisBreakBracket:
    baseline_output_id: str
    driver_id: str
    lower_driver_value: Decimal
    upper_driver_value: Decimal
    decision_value: Decimal
    value_claim: str
    scenario_output_ids: tuple[str, str]
    valuation_output_ids: tuple[str, str]
    output_id: str
    eligibility_status: GateStatus = GateStatus.NOT_EVALUATED


def bracket_thesis_break(
    first: CoherentScenarioValue,
    second: CoherentScenarioValue,
    *,
    decision_value: Decimal,
    decision_value_source_id: str,
) -> ThesisBreakBracket:
    """Locate a decision switch between two fully valued Core scenario paths.

    No linear interpolation is claimed: a nonlinear model may switch anywhere
    inside the returned driver interval. The caller must examine other drivers
    and scenario coherence before treating the interval as a thesis boundary.
    """

    target = _finite(decision_value, "decision_value")
    _nonempty(decision_value_source_id, "decision_value_source_id")
    if first.baseline_output_id != second.baseline_output_id:
        raise ValueError("scenario baseline output IDs differ")
    if first.driver_id != second.driver_id or first.value_claim != second.value_claim:
        raise ValueError("scenario driver or valuation claim differs")
    if first.driver_value == second.driver_value:
        raise ValueError("scenario driver values must differ")
    if first.scenario_output_id == second.scenario_output_id:
        raise ValueError("scenario output IDs must differ")
    if (first.valuation_value - target) * (second.valuation_value - target) > 0:
        raise ValueError("scenario valuations do not bracket the decision value")
    ordered = tuple(sorted((first, second), key=lambda point: point.driver_value))
    output_id = _output_id(
        "m1_thesis_break_bracket",
        {
            "schema_version": 1,
            "baseline_output_id": first.baseline_output_id,
            "driver_id": first.driver_id,
            "decision_value": str(target),
            "decision_value_source_id": decision_value_source_id,
            "value_claim": first.value_claim,
            "points": [
                {
                    "driver_value": str(point.driver_value),
                    "valuation_value": str(point.valuation_value),
                    "scenario_output_id": point.scenario_output_id,
                    "valuation_output_id": point.valuation_output_id,
                }
                for point in ordered
            ],
        },
    )
    return ThesisBreakBracket(
        first.baseline_output_id,
        first.driver_id,
        ordered[0].driver_value,
        ordered[1].driver_value,
        target,
        first.value_claim,
        (ordered[0].scenario_output_id, ordered[1].scenario_output_id),
        (ordered[0].valuation_output_id, ordered[1].valuation_output_id),
        output_id,
    )


def eligible_decision_value(
    dcf: DcfResult,
    dcf_eligibility: ValuationEligibilityResult,
    method_selection: MethodSelectionResult,
    method_eligibility: ValuationEligibilityResult,
) -> Decimal:
    """Expose a Core-pinned DCF claim only when numeric and method gates pass.

    An FCFF result is enterprise value; an investor equity conclusion must also
    pass the separate enterprise-to-equity claim bridge gate.
    """

    if (
        dcf.case_id is None
        or dcf.operating_baseline_output_id is None
        or dcf.core_cash_flow_path_output_id is None
    ):
        raise ValueError("decision DCF requires a Core-pinned cash-flow path")
    if method_selection.case_id != dcf.case_id:
        raise ValueError("method selection case differs from DCF case")
    if method_eligibility.calculation_output_id != method_selection.output_id:
        raise ValueError("method review does not match method selection")
    if method_eligibility.status is not GateStatus.PASS:
        raise ValueError("valuation method is not eligible")
    if ValuationMethod.DCF not in method_selection.selected_methods:
        raise ValueError("DCF was not selected for this case")
    if dcf_eligibility.calculation_output_id != dcf.output_id:
        raise ValueError("DCF review does not match valuation")
    if dcf_eligibility.status is not GateStatus.PASS:
        raise ValueError("DCF is not eligible")
    return dcf.total_value


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be offset-aware")


def _point_payload(point: SupportedParameterPoint) -> dict[str, object]:
    return {
        "value": str(point.value),
        "evidence_or_assumption_id": point.evidence_or_assumption_id,
        "basis_source_ids": point.basis_source_ids,
        "available_at": point.available_at.astimezone(UTC).isoformat(),
        "rationale": point.rationale,
    }
