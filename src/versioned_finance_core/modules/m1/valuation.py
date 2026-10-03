"""Structural DCF and enterprise-to-equity math with explicit claim matching.

These functions do not establish that a company's forecast, terminal state,
peer set, discount rate or claims are evidentially adequate. The caller must
complete those case-specific review gates before releasing a valuation.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, localcontext
from enum import StrEnum
from types import MappingProxyType

from versioned_finance_core.contracts.enums import AccountingScope, GateStatus, KnowledgeState
from versioned_finance_core.financial_core.free_cash_flow import FreeCashFlowPathResult
from versioned_finance_core.financial_core.identities import _exact_sum

DCF_REVIEW_CHECKS = frozenset(
    {
        "source_rights_and_vintage",
        "linked_forecast_reconciled",
        "discount_rate_supported",
        "terminal_state_supported",
        "claim_scope_reconciled",
    }
)
EQUITY_BRIDGE_REVIEW_CHECKS = frozenset(
    {
        "source_rights_and_vintage",
        "claim_balances_complete",
        "claim_scope_reconciled",
    }
)


class CashFlowClaim(StrEnum):
    FCFF = "FCFF"
    FCFE = "FCFE"


class DiscountRateClaim(StrEnum):
    WACC = "WACC"
    COST_OF_EQUITY = "COST_OF_EQUITY"


class RateBasis(StrEnum):
    NOMINAL = "NOMINAL"
    REAL = "REAL"


class DiscountTiming(StrEnum):
    ANNUAL_PERIOD_END = "ANNUAL_PERIOD_END"
    ACT_365_FIXED = "ACT_365_FIXED"


@dataclass(frozen=True, slots=True)
class ForecastCashFlow:
    period_index: int
    amount: Decimal
    output_id: str
    period_end: date | None = None

    def __post_init__(self) -> None:
        if isinstance(self.period_index, bool) or not isinstance(self.period_index, int):
            raise TypeError("period_index must be an integer")
        if self.period_index < 1:
            raise ValueError("period_index must be positive")
        _finite(self.amount, "amount")
        _nonempty(self.output_id, "output_id")
        if self.period_end is not None and (
            not isinstance(self.period_end, date) or isinstance(self.period_end, datetime)
        ):
            raise TypeError("period_end must be a date")


@dataclass(frozen=True, slots=True)
class TerminalOperatingEconomics:
    """Sustainable next-year NOPAT and reinvestment needed for perpetual growth."""

    next_year_unlevered_nopat: Decimal
    sustainable_roic: Decimal
    growth_rate: Decimal
    assumption_id: str
    basis_source_ids: tuple[str, ...]
    available_at: datetime
    rationale: str
    next_year_ebit: Decimal | None = None
    unlevered_cash_tax_rate: Decimal | None = None
    sustainable_ebit_growth: Decimal | None = None
    parameter_assumption_ids: tuple[tuple[str, str], ...] = ()
    final_core_fcff: Decimal | None = None
    final_core_fcff_output_id: str | None = None

    def __post_init__(self) -> None:
        nopat = _finite(self.next_year_unlevered_nopat, "next_year_unlevered_nopat")
        roic = _finite(self.sustainable_roic, "sustainable_roic")
        growth = _finite(self.growth_rate, "growth_rate")
        if nopat <= 0 or roic <= 0 or growth < 0 or growth >= roic:
            raise ValueError("terminal economics require positive NOPAT and ROIC > nonnegative g")
        _nonempty(self.assumption_id, "assumption_id")
        _nonempty(self.rationale, "rationale")
        if not isinstance(self.basis_source_ids, tuple) or not self.basis_source_ids:
            raise ValueError("terminal economics require source IDs")
        for source_id in self.basis_source_ids:
            _nonempty(source_id, "terminal_economics_source_id")
        if len(set(self.basis_source_ids)) != len(self.basis_source_ids):
            raise ValueError("duplicate terminal economics source ID")
        if not isinstance(self.available_at, datetime) or (
            self.available_at.tzinfo is None or self.available_at.utcoffset() is None
        ):
            raise ValueError("terminal economics available_at must be offset-aware")
        for name in ("next_year_ebit", "unlevered_cash_tax_rate", "sustainable_ebit_growth"):
            value = getattr(self, name)
            if value is not None:
                _finite(value, name)
        for parameter, assumption_id in self.parameter_assumption_ids:
            _nonempty(parameter, "terminal_parameter")
            _nonempty(assumption_id, "terminal_parameter_assumption_id")
        if len({name for name, _ in self.parameter_assumption_ids}) != len(
            self.parameter_assumption_ids
        ):
            raise ValueError("duplicate terminal parameter assumption")
        if (self.final_core_fcff is None) != (self.final_core_fcff_output_id is None):
            raise ValueError("final Core FCFF and output ID must be supplied together")
        if self.final_core_fcff is not None:
            _finite(self.final_core_fcff, "final_core_fcff")
            _nonempty(self.final_core_fcff_output_id, "final_core_fcff_output_id")

    @property
    def reinvestment_rate(self) -> Decimal:
        with localcontext() as decimal_context:
            decimal_context.prec = 50
            return self.growth_rate / self.sustainable_roic

    @property
    def next_year_fcff(self) -> Decimal:
        with localcontext() as decimal_context:
            decimal_context.prec = 50
            return self.next_year_unlevered_nopat * (Decimal(1) - self.reinvestment_rate)

    @property
    def transition_difference(self) -> Decimal | None:
        if self.final_core_fcff is None:
            return None
        with localcontext() as decimal_context:
            decimal_context.prec = 50
            return self.next_year_fcff - self.final_core_fcff

    @property
    def transition_ratio(self) -> Decimal | KnowledgeState | None:
        """Next sustainable FCFF divided by final forecast FCFF; NM at zero."""

        if self.final_core_fcff is None:
            return None
        if self.final_core_fcff == 0:
            return KnowledgeState.NM
        with localcontext() as decimal_context:
            decimal_context.prec = 50
            return self.next_year_fcff / self.final_core_fcff


def terminal_operating_economics_from_forecast(
    path: FreeCashFlowPathResult,
    *,
    sustainable_ebit_growth: Decimal,
    terminal_growth_rate: Decimal,
    unlevered_cash_tax_rate: Decimal,
    sustainable_roic: Decimal,
    assumption_id: str,
    ebit_growth_assumption_id: str,
    cash_tax_rate_assumption_id: str,
    roic_assumption_id: str,
    growth_assumption_id: str,
    basis_source_ids: tuple[str, ...],
    available_at: datetime,
    rationale: str,
) -> TerminalOperatingEconomics:
    """Tie terminal NOPAT and g/ROIC reinvestment to the final annual Core EBIT.

    The EBIT growth, unlevered tax and ROIC are externally governed assumptions.
    This helper checks their lineage and calculates their consequence; it does
    not assert that the company's sustainable economics have been established.
    """

    if not isinstance(path, FreeCashFlowPathResult) or not path.periods:
        raise TypeError("path must be a nonempty Core FreeCashFlowPathResult")
    if len(path.periods) != len(path.baseline.periods) or any(
        actual.period_id != reference.period_id
        or actual.period_start != reference.period_start
        or actual.period_end != reference.period_end
        for actual, reference in zip(path.periods, path.baseline.periods, strict=True)
    ):
        raise ValueError("Core FCF period identity differs from pinned baseline")
    final = path.periods[-1]
    if (final.period_end - final.period_start).days + 1 not in (364, 365, 366, 371):
        raise ValueError("terminal economics require a full annual final Core period")
    _nonempty(final.fcff_output_id, "final Core FCFF output ID")
    if isinstance(final.fcff, KnowledgeState):
        raise TypeError("terminal transition requires resolved final Core FCFF")
    _finite(final.fcff, "final Core FCFF")
    if not isinstance(available_at, datetime) or (
        available_at.tzinfo is None or available_at.utcoffset() is None
    ):
        raise ValueError("terminal economics available_at must be offset-aware")
    if available_at > path.baseline.information_cutoff:
        raise ValueError("terminal economics are unavailable at Core cutoff")
    ebit_growth = _finite(sustainable_ebit_growth, "sustainable_ebit_growth")
    tax_rate = _finite(unlevered_cash_tax_rate, "unlevered_cash_tax_rate")
    if ebit_growth <= -1 or not Decimal(0) <= tax_rate < Decimal(1):
        raise ValueError("terminal EBIT growth or unlevered cash tax rate is invalid")
    for name, value in (
        ("ebit_growth_assumption_id", ebit_growth_assumption_id),
        ("cash_tax_rate_assumption_id", cash_tax_rate_assumption_id),
        ("roic_assumption_id", roic_assumption_id),
        ("growth_assumption_id", growth_assumption_id),
    ):
        _nonempty(value, name)
    if not isinstance(basis_source_ids, tuple) or not basis_source_ids:
        raise ValueError("terminal economics require external basis source IDs")
    with localcontext() as decimal_context:
        decimal_context.prec = 50
        next_ebit = final.ebit * (Decimal(1) + ebit_growth)
        next_nopat = next_ebit * (Decimal(1) - tax_rate)
    return TerminalOperatingEconomics(
        next_year_unlevered_nopat=next_nopat,
        sustainable_roic=sustainable_roic,
        growth_rate=terminal_growth_rate,
        assumption_id=assumption_id,
        basis_source_ids=(final.fcff_output_id, *basis_source_ids),
        available_at=available_at,
        rationale=rationale,
        next_year_ebit=next_ebit,
        unlevered_cash_tax_rate=tax_rate,
        sustainable_ebit_growth=ebit_growth,
        parameter_assumption_ids=(
            ("ebit_growth", ebit_growth_assumption_id),
            ("cash_tax_rate", cash_tax_rate_assumption_id),
            ("roic", roic_assumption_id),
            ("terminal_growth", growth_assumption_id),
        ),
        final_core_fcff=final.fcff,
        final_core_fcff_output_id=final.fcff_output_id,
    )


@dataclass(frozen=True, slots=True)
class DcfInputs:
    cash_flow_claim: CashFlowClaim
    discount_rate_claim: DiscountRateClaim
    cash_flow_basis: RateBasis
    discount_rate_basis: RateBasis
    cash_flow_currency: str
    discount_rate_currency: str
    forecast_version_id: str
    annual_cash_flows: tuple[ForecastCashFlow, ...]
    annual_discount_rate: Decimal
    discount_rate_assumption_id: str
    terminal_next_cash_flow: Decimal
    terminal_growth_rate: Decimal
    terminal_state_assumption_id: str
    case_id: str | None = None
    operating_baseline_output_id: str | None = None
    core_cash_flow_path_output_id: str | None = None
    discount_timing: DiscountTiming = DiscountTiming.ANNUAL_PERIOD_END
    valuation_date: date | None = None
    first_forecast_period_start: date | None = None
    information_cutoff: datetime | None = None
    discount_rate_available_at: datetime | None = None
    terminal_state_available_at: datetime | None = None
    discount_rate_basis_source_ids: tuple[str, ...] = ()
    terminal_state_basis_source_ids: tuple[str, ...] = ()
    accounting_scope: AccountingScope | None = None
    economic_scope_id: str | None = None
    legal_entity_id: str | None = None
    unit: str | None = None
    discount_rate_rationale: str | None = None
    terminal_cash_flow_rationale: str | None = None
    terminal_economics: TerminalOperatingEconomics | None = None


@dataclass(frozen=True, slots=True)
class DcfResult:
    value_claim: str
    forecast_version_id: str
    explicit_period_value: Decimal
    terminal_value_at_horizon: Decimal
    present_terminal_value: Decimal
    total_value: Decimal
    output_id: str
    input_lineage: tuple[tuple[str, str], ...]
    eligibility_status: GateStatus = GateStatus.NOT_EVALUATED
    case_id: str | None = None
    operating_baseline_output_id: str | None = None
    core_cash_flow_path_output_id: str | None = None
    discount_timing: DiscountTiming = DiscountTiming.ANNUAL_PERIOD_END
    valuation_date: date | None = None
    first_forecast_period_start: date | None = None
    information_cutoff: datetime | None = None
    accounting_scope: AccountingScope | None = None
    economic_scope_id: str | None = None
    legal_entity_id: str | None = None
    currency: str | None = None
    unit: str | None = None
    period_year_fractions: tuple[Decimal, ...] = ()


def value_perpetuity_dcf(inputs: DcfInputs) -> DcfResult:
    """Discount annual FCF and a separately supported terminal-year cash flow."""

    if not isinstance(inputs.cash_flow_claim, CashFlowClaim):
        raise TypeError("cash_flow_claim must be a CashFlowClaim")
    if not isinstance(inputs.discount_rate_claim, DiscountRateClaim):
        raise TypeError("discount_rate_claim must be a DiscountRateClaim")
    if not isinstance(inputs.cash_flow_basis, RateBasis) or not isinstance(
        inputs.discount_rate_basis, RateBasis
    ):
        raise TypeError("cash-flow and discount-rate basis must be RateBasis")
    expected_rate = {
        CashFlowClaim.FCFF: DiscountRateClaim.WACC,
        CashFlowClaim.FCFE: DiscountRateClaim.COST_OF_EQUITY,
    }
    if inputs.discount_rate_claim != expected_rate.get(inputs.cash_flow_claim):
        raise ValueError("cash-flow claim and discount-rate claim do not match")
    if inputs.cash_flow_basis != inputs.discount_rate_basis:
        raise ValueError("cash-flow and discount-rate nominal/real basis differ")
    if inputs.cash_flow_currency != inputs.discount_rate_currency:
        raise ValueError("cash-flow and discount-rate currency differ")
    _nonempty(inputs.cash_flow_currency, "cash_flow_currency")
    _nonempty(inputs.forecast_version_id, "forecast_version_id")
    _nonempty(inputs.discount_rate_assumption_id, "discount_rate_assumption_id")
    _nonempty(inputs.terminal_state_assumption_id, "terminal_state_assumption_id")
    if (inputs.operating_baseline_output_id is None) != (
        inputs.core_cash_flow_path_output_id is None
    ):
        raise ValueError("Core baseline and cash-flow path IDs must be supplied together")
    if (inputs.case_id is None) != (inputs.operating_baseline_output_id is None):
        raise ValueError("case_id must accompany a Core-pinned DCF")
    if inputs.operating_baseline_output_id is not None:
        _nonempty(inputs.case_id, "case_id")
        _nonempty(inputs.operating_baseline_output_id, "operating_baseline_output_id")
        _nonempty(inputs.core_cash_flow_path_output_id, "core_cash_flow_path_output_id")
    rate = _finite(inputs.annual_discount_rate, "annual_discount_rate")
    growth = _finite(inputs.terminal_growth_rate, "terminal_growth_rate")
    terminal_cash_flow = _finite(inputs.terminal_next_cash_flow, "terminal_next_cash_flow")
    if rate <= growth:
        raise ValueError("annual_discount_rate must exceed terminal_growth_rate")
    if rate <= -1 or growth <= -1:
        raise ValueError("discount and growth rates must exceed -1")
    if terminal_cash_flow <= 0:
        raise ValueError("terminal_next_cash_flow must be positive for perpetuity DCF")
    flows = inputs.annual_cash_flows
    if not isinstance(flows, tuple) or any(
        not isinstance(flow, ForecastCashFlow) for flow in flows
    ):
        raise ValueError("annual_cash_flows must be a tuple of ForecastCashFlow")
    if not flows:
        raise ValueError("at least one forecast cash flow is required")
    if tuple(flow.period_index for flow in flows) != tuple(range(1, len(flows) + 1)):
        raise ValueError("forecast period_index must be contiguous from one")
    if len({flow.output_id for flow in flows}) != len(flows):
        raise ValueError("forecast output_id must be unique")

    if not isinstance(inputs.discount_timing, DiscountTiming):
        raise TypeError("discount_timing must be DiscountTiming")
    if inputs.discount_timing is DiscountTiming.ACT_365_FIXED:
        _dated_dcf_provenance(inputs)
        assert inputs.valuation_date is not None
        ends = tuple(flow.period_end for flow in flows)
        if any(end is None for end in ends):
            raise ValueError("dated DCF requires every Core cash-flow period end")
        if any(end <= previous for previous, end in zip(
            (inputs.valuation_date, *ends[:-1]), ends, strict=True
        )):
            raise ValueError("dated DCF period ends must increase after valuation_date")
        # Fractional powers need a declared precision; no display quantization
        # is applied to any intermediate cash flow or present value.
        with localcontext() as decimal_context:
            decimal_context.prec = 50
            year_fractions = tuple(
                Decimal((end - inputs.valuation_date).days) / Decimal(365)
                for end in ends
            )
            explicit = sum(
                (flow.amount / (Decimal(1) + rate) ** elapsed
                 for flow, elapsed in zip(flows, year_fractions, strict=True)),
                Decimal(0),
            )
            terminal = terminal_cash_flow / (rate - growth)
            present_terminal = terminal / (Decimal(1) + rate) ** year_fractions[-1]
            total_value = explicit + present_terminal
    else:
        if inputs.valuation_date is not None or any(flow.period_end is not None for flow in flows):
            raise ValueError("dated cash flows require ACT_365_FIXED timing")
        year_fractions = tuple(Decimal(flow.period_index) for flow in flows)
        explicit = sum(
            (flow.amount / (Decimal(1) + rate) ** flow.period_index for flow in flows),
            Decimal(0),
        )
        terminal = terminal_cash_flow / (rate - growth)
        present_terminal = terminal / (Decimal(1) + rate) ** len(flows)
        total_value = explicit + present_terminal
    value_claim = (
        "ENTERPRISE_VALUE" if inputs.cash_flow_claim is CashFlowClaim.FCFF else "EQUITY_VALUE"
    )
    lineage = (
        *((("case", inputs.case_id),) if inputs.case_id is not None else ()),
        ("forecast_version", inputs.forecast_version_id),
        *(
            (("operating_baseline", inputs.operating_baseline_output_id),)
            if inputs.operating_baseline_output_id is not None else ()
        ),
        *(
            (("core_cash_flow_path", inputs.core_cash_flow_path_output_id),)
            if inputs.core_cash_flow_path_output_id is not None else ()
        ),
        *((f"cash_flow_period_{flow.period_index}", flow.output_id) for flow in flows),
        ("discount_rate_assumption", inputs.discount_rate_assumption_id),
        ("terminal_state_assumption", inputs.terminal_state_assumption_id),
        *((f"discount_rate_basis_source_{index}", source_id)
          for index, source_id in enumerate(inputs.discount_rate_basis_source_ids, start=1)),
        *((f"terminal_state_basis_source_{index}", source_id)
          for index, source_id in enumerate(inputs.terminal_state_basis_source_ids, start=1)),
    )
    dated_payload = (
        {
            "discount_timing": inputs.discount_timing.value,
            "valuation_date": inputs.valuation_date.isoformat(),
            "first_forecast_period_start": inputs.first_forecast_period_start.isoformat(),
            "information_cutoff": inputs.information_cutoff.astimezone(UTC).isoformat(),
            "cash_flow_period_ends": [end.isoformat() for end in ends],
            "period_year_fractions": [str(elapsed) for elapsed in year_fractions],
            "discount_rate_available_at": inputs.discount_rate_available_at.astimezone(UTC).isoformat(),
            "terminal_state_available_at": inputs.terminal_state_available_at.astimezone(UTC).isoformat(),
            "accounting_scope": inputs.accounting_scope.value,
            "economic_scope_id": inputs.economic_scope_id,
            "legal_entity_id": inputs.legal_entity_id,
            "unit": inputs.unit,
            "discount_rate_rationale": inputs.discount_rate_rationale,
            "terminal_cash_flow_rationale": inputs.terminal_cash_flow_rationale,
            "terminal_economics": (
                {
                    "next_year_unlevered_nopat": str(inputs.terminal_economics.next_year_unlevered_nopat),
                    "sustainable_roic": str(inputs.terminal_economics.sustainable_roic),
                    "growth_rate": str(inputs.terminal_economics.growth_rate),
                    "reinvestment_rate": str(inputs.terminal_economics.reinvestment_rate),
                    "next_year_fcff": str(inputs.terminal_economics.next_year_fcff),
                    "final_core_fcff": (
                        str(inputs.terminal_economics.final_core_fcff)
                        if inputs.terminal_economics.final_core_fcff is not None else None
                    ),
                    "final_core_fcff_output_id": (
                        inputs.terminal_economics.final_core_fcff_output_id
                    ),
                    "transition_difference": (
                        str(inputs.terminal_economics.transition_difference)
                        if inputs.terminal_economics.transition_difference is not None else None
                    ),
                    "transition_ratio": (
                        inputs.terminal_economics.transition_ratio.value
                        if isinstance(inputs.terminal_economics.transition_ratio, KnowledgeState)
                        else str(inputs.terminal_economics.transition_ratio)
                        if inputs.terminal_economics.transition_ratio is not None else None
                    ),
                    "assumption_id": inputs.terminal_economics.assumption_id,
                    "basis_source_ids": inputs.terminal_economics.basis_source_ids,
                    "available_at": inputs.terminal_economics.available_at.astimezone(UTC).isoformat(),
                    "rationale": inputs.terminal_economics.rationale,
                    "next_year_ebit": (
                        str(inputs.terminal_economics.next_year_ebit)
                        if inputs.terminal_economics.next_year_ebit is not None else None
                    ),
                    "unlevered_cash_tax_rate": (
                        str(inputs.terminal_economics.unlevered_cash_tax_rate)
                        if inputs.terminal_economics.unlevered_cash_tax_rate is not None else None
                    ),
                    "sustainable_ebit_growth": (
                        str(inputs.terminal_economics.sustainable_ebit_growth)
                        if inputs.terminal_economics.sustainable_ebit_growth is not None else None
                    ),
                    "parameter_assumption_ids": inputs.terminal_economics.parameter_assumption_ids,
                } if inputs.terminal_economics is not None else None
            ),
        }
        if inputs.discount_timing is DiscountTiming.ACT_365_FIXED else {}
    )
    output_id = _output_id(
        "m1_dcf",
        {
            "schema_version": 2 if dated_payload else 1,
            "value_claim": value_claim,
            "cash_flow_claim": inputs.cash_flow_claim.value,
            "discount_rate_claim": inputs.discount_rate_claim.value,
            "rate_basis": inputs.discount_rate_basis.value,
            "currency": inputs.cash_flow_currency,
            "lineage": lineage,
            "cash_flows": [(flow.period_index, str(flow.amount)) for flow in flows],
            "annual_discount_rate": str(rate),
            "terminal_next_cash_flow": str(terminal_cash_flow),
            "terminal_growth_rate": str(growth),
            "explicit_period_value": str(explicit),
            "terminal_value_at_horizon": str(terminal),
            "present_terminal_value": str(present_terminal),
            "total_value": str(total_value),
            **dated_payload,
        },
    )
    return DcfResult(
        value_claim=value_claim,
        forecast_version_id=inputs.forecast_version_id,
        explicit_period_value=explicit,
        terminal_value_at_horizon=terminal,
        present_terminal_value=present_terminal,
        total_value=total_value,
        output_id=output_id,
        input_lineage=lineage,
        case_id=inputs.case_id,
        operating_baseline_output_id=inputs.operating_baseline_output_id,
        core_cash_flow_path_output_id=inputs.core_cash_flow_path_output_id,
        discount_timing=inputs.discount_timing,
        valuation_date=inputs.valuation_date,
        first_forecast_period_start=inputs.first_forecast_period_start,
        information_cutoff=inputs.information_cutoff,
        accounting_scope=inputs.accounting_scope,
        economic_scope_id=inputs.economic_scope_id,
        legal_entity_id=inputs.legal_entity_id,
        currency=inputs.cash_flow_currency,
        unit=inputs.unit,
        period_year_fractions=year_fractions,
    )


def dcf_inputs_from_core_cash_flows(
    path: FreeCashFlowPathResult,
    *,
    case_id: str,
    forecast_version_id: str,
    accounting_scope: AccountingScope,
    economic_scope_id: str,
    legal_entity_id: str | None,
    currency: str,
    unit: str,
    cash_flow_claim: CashFlowClaim,
    discount_rate_claim: DiscountRateClaim,
    rate_basis: RateBasis,
    annual_discount_rate: Decimal,
    discount_rate_assumption_id: str,
    discount_rate_available_at: datetime,
    terminal_next_cash_flow: Decimal,
    terminal_growth_rate: Decimal,
    terminal_state_assumption_id: str,
    terminal_state_available_at: datetime,
    discount_timing: DiscountTiming = DiscountTiming.ANNUAL_PERIOD_END,
    discount_rate_basis_source_ids: tuple[str, ...] = (),
    terminal_state_basis_source_ids: tuple[str, ...] = (),
    valuation_date: date | None = None,
    discount_rate_rationale: str | None = None,
    terminal_cash_flow_rationale: str | None = None,
    terminal_economics: TerminalOperatingEconomics | None = None,
) -> DcfInputs:
    """Pin DCF cash-flow inputs to Core output, without rederiving FCF in M1.

    Annual timing preserves the original end-of-year convention. Explicit
    ACT/365F timing discounts a partial first fiscal period by its actual
    period-end date without annualizing that Core cash flow.
    """

    if not isinstance(path, FreeCashFlowPathResult):
        raise TypeError("path must be a Core FreeCashFlowPathResult")
    if not isinstance(cash_flow_claim, CashFlowClaim):
        raise TypeError("cash_flow_claim must be CashFlowClaim")
    if not isinstance(discount_rate_claim, DiscountRateClaim):
        raise TypeError("discount_rate_claim must be DiscountRateClaim")
    if not isinstance(rate_basis, RateBasis):
        raise TypeError("rate_basis must be RateBasis")
    if rate_basis is not RateBasis.NOMINAL:
        raise ValueError("Core financial-statement cash flows require a nominal discount-rate basis")
    if not isinstance(discount_timing, DiscountTiming):
        raise TypeError("discount_timing must be DiscountTiming")
    if valuation_date is not None and discount_timing is not DiscountTiming.ACT_365_FIXED:
        raise ValueError("valuation_date requires ACT_365_FIXED timing")
    baseline = path.baseline
    for name, supplied, pinned in (
        ("case_id", case_id, baseline.case_id),
        ("forecast_version_id", forecast_version_id, baseline.version_id),
        ("economic_scope_id", economic_scope_id, baseline.economic_scope_id),
        ("currency", currency, baseline.currency),
        ("unit", unit, baseline.unit),
    ):
        _nonempty(supplied, name)
        if supplied != pinned:
            raise ValueError(f"{name} differs from the Core operating baseline")
    if not isinstance(accounting_scope, AccountingScope):
        raise TypeError("accounting_scope must be AccountingScope")
    if accounting_scope != baseline.accounting_scope:
        raise ValueError("accounting_scope differs from the Core operating baseline")
    if legal_entity_id != baseline.legal_entity_id:
        raise ValueError("legal_entity_id differs from the Core operating baseline")
    _nonempty(path.output_id, "core_cash_flow_path_output_id")
    _nonempty(baseline.output_id, "operating_baseline_output_id")
    if not path.periods or len(path.periods) != len(baseline.periods):
        raise ValueError("Core cash-flow periods do not match the operating baseline")
    for name, available_at in (
        ("discount_rate_available_at", discount_rate_available_at),
        ("terminal_state_available_at", terminal_state_available_at),
    ):
        if (
            not isinstance(available_at, datetime)
            or available_at.tzinfo is None
            or available_at.utcoffset() is None
        ):
            raise ValueError(f"{name} must be offset-aware")
        if available_at > baseline.information_cutoff:
            raise ValueError(f"{name} is after the Core information cutoff")

    annual_flows: list[ForecastCashFlow] = []
    for period_index, (period, reference) in enumerate(
        zip(path.periods, baseline.periods, strict=True), start=1
    ):
        if (
            period.period_id != reference.period_id
            or period.period_start != reference.period_start
            or period.period_end != reference.period_end
        ):
            raise ValueError("Core cash-flow period identity differs from baseline")
        period_days = (period.period_end - period.period_start).days + 1
        if (discount_timing is DiscountTiming.ANNUAL_PERIOD_END
                and period_days not in (364, 365, 366, 371)):
            raise ValueError("DCF adapter requires annual fiscal cash-flow periods")
        if cash_flow_claim is CashFlowClaim.FCFF:
            amount, output_id = period.fcff, period.fcff_output_id
        else:
            amount, output_id = period.fcfe, period.fcfe_output_id
        if isinstance(amount, KnowledgeState) or output_id is None:
            raise ValueError(f"Core {cash_flow_claim.value} is unresolved: {period.period_id}")
        _finite(amount, f"Core {cash_flow_claim.value} amount")
        annual_flows.append(ForecastCashFlow(
            period_index, amount, output_id,
            period.period_end if discount_timing is DiscountTiming.ACT_365_FIXED else None,
        ))

    return DcfInputs(
        cash_flow_claim=cash_flow_claim,
        discount_rate_claim=discount_rate_claim,
        cash_flow_basis=rate_basis,
        discount_rate_basis=rate_basis,
        cash_flow_currency=baseline.currency,
        discount_rate_currency=baseline.currency,
        forecast_version_id=baseline.version_id,
        annual_cash_flows=tuple(annual_flows),
        annual_discount_rate=annual_discount_rate,
        discount_rate_assumption_id=discount_rate_assumption_id,
        terminal_next_cash_flow=terminal_next_cash_flow,
        terminal_growth_rate=terminal_growth_rate,
        terminal_state_assumption_id=terminal_state_assumption_id,
        case_id=baseline.case_id,
        operating_baseline_output_id=baseline.output_id,
        core_cash_flow_path_output_id=path.output_id,
        discount_timing=discount_timing,
        valuation_date=(valuation_date or baseline.information_cutoff.date()
                        if discount_timing is DiscountTiming.ACT_365_FIXED else None),
        first_forecast_period_start=(baseline.periods[0].period_start
                                     if discount_timing is DiscountTiming.ACT_365_FIXED else None),
        information_cutoff=baseline.information_cutoff,
        discount_rate_available_at=discount_rate_available_at,
        terminal_state_available_at=terminal_state_available_at,
        discount_rate_basis_source_ids=discount_rate_basis_source_ids,
        terminal_state_basis_source_ids=terminal_state_basis_source_ids,
        accounting_scope=baseline.accounting_scope,
        economic_scope_id=baseline.economic_scope_id,
        legal_entity_id=baseline.legal_entity_id,
        unit=baseline.unit,
        discount_rate_rationale=discount_rate_rationale,
        terminal_cash_flow_rationale=terminal_cash_flow_rationale,
        terminal_economics=terminal_economics,
    )


@dataclass(frozen=True, slots=True)
class EnterpriseToEquityInputs:
    enterprise_value: Decimal
    excess_cash: Decimal
    nonoperating_assets: Decimal
    debt_like_claims: Decimal
    minority_interest: Decimal
    other_senior_claims: Decimal


def enterprise_to_equity(inputs: EnterpriseToEquityInputs) -> Decimal:
    """Return arithmetic only; this value has no release eligibility on its own."""

    _finite(inputs.enterprise_value, "enterprise_value")
    for name in (
        "excess_cash", "nonoperating_assets", "debt_like_claims",
        "minority_interest", "other_senior_claims",
    ):
        value = _finite(getattr(inputs, name), name)
        if value < 0:
            raise ValueError(f"{name} must be nonnegative")
    return (
        inputs.enterprise_value + inputs.excess_cash + inputs.nonoperating_assets
        - inputs.debt_like_claims - inputs.minority_interest - inputs.other_senior_claims
    )


@dataclass(frozen=True, slots=True)
class ClaimBridgeEvidence:
    enterprise_value_output_id: str
    excess_cash_source_id: str
    nonoperating_assets_source_id: str
    debt_like_claims_source_id: str
    minority_interest_source_id: str
    other_senior_claims_source_id: str

    def __post_init__(self) -> None:
        for name in (
            "enterprise_value_output_id", "excess_cash_source_id",
            "nonoperating_assets_source_id", "debt_like_claims_source_id",
            "minority_interest_source_id", "other_senior_claims_source_id",
        ):
            _nonempty(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class EquityClaimBridgeResult:
    parent_dcf_output_id: str
    equity_value: Decimal
    output_id: str
    input_lineage: tuple[tuple[str, str], ...]
    eligibility_status: GateStatus = GateStatus.NOT_EVALUATED


def bridge_enterprise_to_equity(
    dcf: DcfResult,
    inputs: EnterpriseToEquityInputs,
    evidence: ClaimBridgeEvidence,
) -> EquityClaimBridgeResult:
    """Pin claim arithmetic to one FCFF DCF output and identified claim inputs."""

    if dcf.value_claim != "ENTERPRISE_VALUE":
        raise ValueError("claim bridge requires an FCFF enterprise-value DCF")
    if inputs.enterprise_value != dcf.total_value:
        raise ValueError("enterprise_value must equal the pinned DCF result")
    if evidence.enterprise_value_output_id != dcf.output_id:
        raise ValueError("enterprise_value_output_id does not match DCF result")
    equity_value = enterprise_to_equity(inputs)
    lineage = (
        ("enterprise_value", dcf.output_id),
        ("excess_cash", evidence.excess_cash_source_id),
        ("nonoperating_assets", evidence.nonoperating_assets_source_id),
        ("debt_like_claims", evidence.debt_like_claims_source_id),
        ("minority_interest", evidence.minority_interest_source_id),
        ("other_senior_claims", evidence.other_senior_claims_source_id),
    )
    output_id = _output_id(
        "m1_equity_bridge",
        {
            "schema_version": 1,
            "lineage": lineage,
            "enterprise_value": str(inputs.enterprise_value),
            "excess_cash": str(inputs.excess_cash),
            "nonoperating_assets": str(inputs.nonoperating_assets),
            "debt_like_claims": str(inputs.debt_like_claims),
            "minority_interest": str(inputs.minority_interest),
            "other_senior_claims": str(inputs.other_senior_claims),
            "equity_value": str(equity_value),
        },
    )
    return EquityClaimBridgeResult(
        parent_dcf_output_id=dcf.output_id,
        equity_value=equity_value,
        output_id=output_id,
        input_lineage=lineage,
    )


class LeaseValuationTreatment(StrEnum):
    OPERATING_COST_INCLUDED = "OPERATING_COST_INCLUDED"
    CAPITALIZED_FINANCING = "CAPITALIZED_FINANCING"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class DatedClaimBalance:
    amount: Decimal
    source_id: str
    as_of_date: date
    available_at: datetime
    accounting_scope: AccountingScope
    economic_scope_id: str
    legal_entity_id: str | None
    currency: str
    unit: str
    component_source_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if _finite(self.amount, "claim amount") < 0:
            raise ValueError("claim amount must be nonnegative")
        for name in ("source_id", "economic_scope_id", "currency", "unit"):
            _nonempty(getattr(self, name), name)
        if not isinstance(self.as_of_date, date) or isinstance(self.as_of_date, datetime):
            raise TypeError("claim as_of_date must be a date")
        if not isinstance(self.available_at, datetime) or (
            self.available_at.tzinfo is None or self.available_at.utcoffset() is None
        ):
            raise ValueError("claim available_at must be offset-aware")
        if not isinstance(self.accounting_scope, AccountingScope):
            raise TypeError("claim accounting_scope must be AccountingScope")
        if not isinstance(self.component_source_ids, tuple):
            raise TypeError("component_source_ids must be a tuple")
        for source_id in self.component_source_ids:
            _nonempty(source_id, "component_source_id")
        if len(set(self.component_source_ids)) != len(self.component_source_ids):
            raise ValueError("duplicate component source ID")
        if self.source_id in self.component_source_ids:
            raise ValueError("claim aggregate source ID duplicates a component source ID")


def aggregate_dated_claim_balances(
    claims: tuple[DatedClaimBalance, ...],
    *,
    aggregate_name: str,
    information_cutoff: datetime,
) -> DatedClaimBalance:
    """Sum sourced claim balances at one date/scope and retain every source ID."""

    _nonempty(aggregate_name, "aggregate_name")
    if not isinstance(information_cutoff, datetime) or (
        information_cutoff.tzinfo is None or information_cutoff.utcoffset() is None
    ):
        raise ValueError("information_cutoff must be offset-aware")
    if not isinstance(claims, tuple) or not claims or any(
        not isinstance(claim, DatedClaimBalance) for claim in claims
    ):
        raise TypeError("claims must be a nonempty tuple of DatedClaimBalance")
    ordered = tuple(sorted(claims, key=lambda claim: claim.source_id))
    if len({claim.source_id for claim in ordered}) != len(ordered):
        raise ValueError("duplicate claim source ID")
    first = ordered[0]
    if first.as_of_date > information_cutoff.date():
        raise ValueError("claim balance date is after information cutoff")
    for claim in ordered:
        for name in ("as_of_date", "accounting_scope", "economic_scope_id",
                     "legal_entity_id", "currency", "unit"):
            if getattr(claim, name) != getattr(first, name):
                raise ValueError(f"claim aggregate {name} differs")
        if claim.available_at > information_cutoff:
            raise ValueError("claim component is unavailable at information cutoff")
    component_ids = tuple(sorted(
        source_id
        for claim in ordered
        for source_id in (claim.component_source_ids or (claim.source_id,))
    ))
    if len(set(component_ids)) != len(component_ids):
        raise ValueError("duplicate underlying claim component source ID")
    amount = _exact_sum(claim.amount for claim in ordered)
    available_at = max(claim.available_at for claim in ordered)
    aggregate_id = _output_id("m1_claim_aggregate", {
        "schema_version": 1,
        "aggregate_name": aggregate_name,
        "as_of_date": first.as_of_date.isoformat(),
        "accounting_scope": first.accounting_scope.value,
        "economic_scope_id": first.economic_scope_id,
        "legal_entity_id": first.legal_entity_id,
        "currency": first.currency,
        "unit": first.unit,
        "components": [
            (claim.source_id, str(claim.amount), claim.available_at.astimezone(UTC).isoformat(),
             claim.component_source_ids)
            for claim in ordered
        ],
        "total": str(amount),
    })
    return DatedClaimBalance(
        amount, aggregate_id, first.as_of_date, available_at,
        first.accounting_scope, first.economic_scope_id, first.legal_entity_id,
        first.currency, first.unit, component_ids,
    )


@dataclass(frozen=True, slots=True)
class LeasePolicyEvidence:
    treatment: LeaseValuationTreatment
    policy_id: str
    source_ids: tuple[str, ...]
    available_at: datetime
    lease_cost_in_fcff: bool
    lease_liability_in_debt_like_claims: bool
    lease_financing_in_wacc: bool

    def __post_init__(self) -> None:
        if not isinstance(self.treatment, LeaseValuationTreatment):
            raise TypeError("treatment must be LeaseValuationTreatment")
        _nonempty(self.policy_id, "policy_id")
        if not self.source_ids or not isinstance(self.source_ids, tuple):
            raise ValueError("lease policy requires source IDs")
        for source_id in self.source_ids:
            _nonempty(source_id, "lease_policy_source_id")
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("duplicate lease policy source ID")
        if not isinstance(self.available_at, datetime) or (
            self.available_at.tzinfo is None or self.available_at.utcoffset() is None
        ):
            raise ValueError("lease policy available_at must be offset-aware")
        for name in ("lease_cost_in_fcff", "lease_liability_in_debt_like_claims",
                     "lease_financing_in_wacc"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be bool")


@dataclass(frozen=True, slots=True)
class DatedEquityClaimBridgeResult:
    parent_dcf_output_id: str
    equity_value: Decimal
    valuation_date: date
    input_lineage: tuple[tuple[str, str], ...]
    failed_structural_checks: tuple[str, ...]
    eligibility_status: GateStatus
    output_id: str


@dataclass(frozen=True, slots=True)
class PartialDatedEquityClaimBridgeResult:
    parent_dcf_output_id: str
    valuation_date: date
    known_subtotal: Decimal
    unknown_components: tuple[str, ...]
    failed_structural_checks: tuple[str, ...]
    input_lineage: tuple[tuple[str, str], ...]
    output_id: str
    equity_value: None = None
    eligibility_status: GateStatus = GateStatus.WITHHELD


def bridge_enterprise_to_equity_partial(
    dcf: DcfResult,
    *,
    excess_cash: DatedClaimBalance | KnowledgeState,
    nonoperating_assets: DatedClaimBalance | KnowledgeState,
    debt_like_claims: DatedClaimBalance | KnowledgeState,
    minority_interest: DatedClaimBalance | KnowledgeState,
    other_senior_claims: DatedClaimBalance | KnowledgeState,
    lease_policy: LeasePolicyEvidence,
) -> PartialDatedEquityClaimBridgeResult:
    """Expose known claim arithmetic without making unknown claims equal zero."""

    if dcf.value_claim != "ENTERPRISE_VALUE" or dcf.valuation_date is None:
        raise ValueError("partial claim bridge requires a dated FCFF enterprise-value DCF")
    if dcf.information_cutoff is None or dcf.accounting_scope is None:
        raise ValueError("dated DCF is missing Core scope or cutoff")
    if not isinstance(lease_policy, LeasePolicyEvidence):
        raise TypeError("lease_policy must be LeasePolicyEvidence")
    if lease_policy.available_at > dcf.information_cutoff:
        raise ValueError("lease policy is unavailable at information cutoff")
    claims = (
        ("excess_cash", excess_cash, Decimal(1)),
        ("nonoperating_assets", nonoperating_assets, Decimal(1)),
        ("debt_like_claims", debt_like_claims, Decimal(-1)),
        ("minority_interest", minority_interest, Decimal(-1)),
        ("other_senior_claims", other_senior_claims, Decimal(-1)),
    )
    unknown: list[str] = []
    failed: list[str] = []
    known_claims: list[tuple[str, DatedClaimBalance, Decimal]] = []
    for name, claim, sign in claims:
        if claim is KnowledgeState.UNKNOWN:
            unknown.append(name)
            continue
        if not isinstance(claim, DatedClaimBalance):
            raise TypeError(f"{name} must be DatedClaimBalance or KnowledgeState.UNKNOWN")
        for field_name, expected in (
            ("accounting_scope", dcf.accounting_scope),
            ("economic_scope_id", dcf.economic_scope_id),
            ("legal_entity_id", dcf.legal_entity_id),
            ("currency", dcf.currency),
            ("unit", dcf.unit),
        ):
            if getattr(claim, field_name) != expected:
                raise ValueError(f"{name} {field_name} differs from Core DCF")
        if claim.available_at > dcf.information_cutoff:
            raise ValueError(f"{name} is unavailable at information cutoff")
        if claim.as_of_date != dcf.valuation_date:
            failed.append(f"{name}_as_of_date")
        known_claims.append((name, claim, sign))
    if not unknown:
        raise ValueError("partial bridge requires at least one UNKNOWN claim")
    lease_flags = (
        lease_policy.lease_cost_in_fcff,
        lease_policy.lease_liability_in_debt_like_claims,
        lease_policy.lease_financing_in_wacc,
    )
    expected_lease_flags = {
        LeaseValuationTreatment.OPERATING_COST_INCLUDED: (True, False, False),
        LeaseValuationTreatment.CAPITALIZED_FINANCING: (False, True, True),
        LeaseValuationTreatment.NOT_APPLICABLE: (False, False, False),
    }
    if expected_lease_flags.get(lease_policy.treatment) != lease_flags:
        failed.append("lease_valuation_treatment")
    with localcontext() as decimal_context:
        decimal_context.prec = 50
        subtotal = dcf.total_value + sum(
            (claim.amount * sign for _, claim, sign in known_claims), Decimal(0)
        )
    lineage = (
        ("enterprise_value", dcf.output_id),
        *((name, claim.source_id) for name, claim, _ in known_claims),
        *((f"{name}_component_{index}", source_id)
          for name, claim, _ in known_claims
          for index, source_id in enumerate(claim.component_source_ids, start=1)),
        ("lease_policy", lease_policy.policy_id),
    )
    output_id = _output_id("m1_partial_equity_bridge", {
        "schema_version": 1,
        "parent_dcf_output_id": dcf.output_id,
        "valuation_date": dcf.valuation_date.isoformat(),
        "known_claims": [
            (name, str(claim.amount), str(sign), claim.source_id,
             claim.as_of_date.isoformat(), claim.available_at.astimezone(UTC).isoformat(),
             claim.component_source_ids)
            for name, claim, sign in known_claims
        ],
        "unknown_components": unknown,
        "lease_policy": (lease_policy.treatment.value, lease_policy.policy_id,
                         lease_policy.source_ids, lease_flags),
        "known_subtotal": str(subtotal),
        "failed_structural_checks": failed,
    })
    return PartialDatedEquityClaimBridgeResult(
        dcf.output_id, dcf.valuation_date, subtotal,
        tuple(unknown), tuple(failed), lineage, output_id,
    )


def bridge_enterprise_to_equity_dated(
    dcf: DcfResult,
    *,
    excess_cash: DatedClaimBalance,
    nonoperating_assets: DatedClaimBalance,
    debt_like_claims: DatedClaimBalance,
    minority_interest: DatedClaimBalance,
    other_senior_claims: DatedClaimBalance,
    lease_policy: LeasePolicyEvidence,
) -> DatedEquityClaimBridgeResult:
    """Calculate a dated bridge, withholding eligibility on date or lease mismatch.

    The arithmetic remains inspectable when the most recent filed claim balances
    precede the DCF valuation date. A separate review is still required after
    the structural checks pass; this function never publishes a target price.
    """

    if dcf.value_claim != "ENTERPRISE_VALUE" or dcf.valuation_date is None:
        raise ValueError("dated claim bridge requires a dated FCFF enterprise-value DCF")
    if dcf.information_cutoff is None or dcf.accounting_scope is None:
        raise ValueError("dated DCF is missing Core scope or cutoff")
    claims = (
        ("excess_cash", excess_cash),
        ("nonoperating_assets", nonoperating_assets),
        ("debt_like_claims", debt_like_claims),
        ("minority_interest", minority_interest),
        ("other_senior_claims", other_senior_claims),
    )
    for name, claim in claims:
        if not isinstance(claim, DatedClaimBalance):
            raise TypeError(f"{name} must be DatedClaimBalance")
        for field_name, expected in (
            ("accounting_scope", dcf.accounting_scope),
            ("economic_scope_id", dcf.economic_scope_id),
            ("legal_entity_id", dcf.legal_entity_id),
            ("currency", dcf.currency),
            ("unit", dcf.unit),
        ):
            if getattr(claim, field_name) != expected:
                raise ValueError(f"{name} {field_name} differs from Core DCF")
        if claim.available_at > dcf.information_cutoff:
            raise ValueError(f"{name} is unavailable at information cutoff")
    if not isinstance(lease_policy, LeasePolicyEvidence):
        raise TypeError("lease_policy must be LeasePolicyEvidence")
    if lease_policy.available_at > dcf.information_cutoff:
        raise ValueError("lease policy is unavailable at information cutoff")

    with localcontext() as decimal_context:
        decimal_context.prec = 50
        arithmetic = bridge_enterprise_to_equity(
            dcf,
            EnterpriseToEquityInputs(dcf.total_value, *(claim.amount for _, claim in claims)),
            ClaimBridgeEvidence(dcf.output_id, *(claim.source_id for _, claim in claims)),
        )
    failed: list[str] = []
    if any(claim.as_of_date != dcf.valuation_date for _, claim in claims):
        failed.append("claim_balance_as_of_date")
    expected_lease_flags = {
        LeaseValuationTreatment.OPERATING_COST_INCLUDED: (True, False, False),
        LeaseValuationTreatment.CAPITALIZED_FINANCING: (False, True, True),
        LeaseValuationTreatment.NOT_APPLICABLE: (False, False, False),
    }
    observed_lease_flags = (
        lease_policy.lease_cost_in_fcff,
        lease_policy.lease_liability_in_debt_like_claims,
        lease_policy.lease_financing_in_wacc,
    )
    if expected_lease_flags.get(lease_policy.treatment) != observed_lease_flags:
        failed.append("lease_valuation_treatment")
    lineage = (
        *arithmetic.input_lineage,
        *((f"{name}_component_{index}", source_id)
          for name, claim in claims
          for index, source_id in enumerate(claim.component_source_ids, start=1)),
        ("lease_policy", lease_policy.policy_id),
        *((f"lease_policy_source_{index}", source_id)
          for index, source_id in enumerate(lease_policy.source_ids, start=1)),
    )
    status = GateStatus.WITHHELD if failed else GateStatus.NOT_EVALUATED
    output_id = _output_id("m1_dated_equity_bridge", {
        "schema_version": 1,
        "parent_dcf_output_id": dcf.output_id,
        "arithmetic_output_id": arithmetic.output_id,
        "valuation_date": dcf.valuation_date.isoformat(),
        "claims": [
            (name, str(claim.amount), claim.source_id, claim.as_of_date.isoformat(),
             claim.available_at.astimezone(UTC).isoformat(), claim.component_source_ids)
            for name, claim in claims
        ],
        "lease_policy": (
            lease_policy.treatment.value, lease_policy.policy_id,
            lease_policy.source_ids,
            lease_policy.available_at.astimezone(UTC).isoformat(),
            observed_lease_flags,
        ),
        "failed_structural_checks": failed,
        "equity_value": str(arithmetic.equity_value),
    })
    return DatedEquityClaimBridgeResult(
        dcf.output_id, arithmetic.equity_value, dcf.valuation_date,
        lineage, tuple(failed), status, output_id,
    )


@dataclass(frozen=True, slots=True)
class ValuationEligibilityReview:
    """Explicit human review assertions; their factual truth is external to code."""

    review_id: str
    reviewer_id: str
    reviewed_at: datetime
    checks: Mapping[str, bool]

    def __post_init__(self) -> None:
        _nonempty(self.review_id, "review_id")
        _nonempty(self.reviewer_id, "reviewer_id")
        if (
            not isinstance(self.reviewed_at, datetime)
            or self.reviewed_at.tzinfo is None
            or self.reviewed_at.utcoffset() is None
        ):
            raise ValueError("reviewed_at must be offset-aware")
        if not isinstance(self.checks, Mapping):
            raise TypeError("checks must be a mapping")
        checked = dict(self.checks)
        if any(not isinstance(name, str) or not isinstance(value, bool) for name, value in checked.items()):
            raise ValueError("review checks must map names to booleans")
        object.__setattr__(self, "checks", MappingProxyType(checked))


@dataclass(frozen=True, slots=True)
class ValuationEligibilityResult:
    calculation_output_id: str
    review_id: str
    reviewer_id: str
    reviewed_at: datetime
    status: GateStatus
    failed_checks: tuple[str, ...]
    dependency_output_ids: tuple[str, ...]
    output_id: str


def assess_dcf_eligibility(
    result: DcfResult, review: ValuationEligibilityReview
) -> ValuationEligibilityResult:
    """Only an explicit review can mark a numeric DCF eligible for release."""

    required_checks = DCF_REVIEW_CHECKS
    if result.discount_timing is DiscountTiming.ACT_365_FIXED:
        required_checks |= frozenset({"dated_discount_timing_reviewed"})
        required_checks |= frozenset({"terminal_cash_flow_economics_reviewed"})
        if result.first_forecast_period_start <= result.valuation_date:
            required_checks |= frozenset({"interim_cash_treatment_reviewed"})
    return _assess(result.output_id, review, required_checks)


def assess_equity_bridge_eligibility(
    bridge: EquityClaimBridgeResult,
    dcf_eligibility: ValuationEligibilityResult,
    review: ValuationEligibilityReview,
) -> ValuationEligibilityResult:
    """Require a passed parent DCF gate as well as reviewed equity claims."""

    if dcf_eligibility.calculation_output_id != bridge.parent_dcf_output_id:
        raise ValueError("parent DCF eligibility does not match claim bridge")
    additional_failed = (
        ("parent_dcf_eligibility",)
        if dcf_eligibility.status is not GateStatus.PASS else ()
    )
    return _assess(
        bridge.output_id, review, EQUITY_BRIDGE_REVIEW_CHECKS,
        additional_failed=additional_failed,
        dependency_output_ids=(dcf_eligibility.output_id,),
    )


def assess_dated_equity_bridge_eligibility(
    bridge: DatedEquityClaimBridgeResult,
    dcf_eligibility: ValuationEligibilityResult,
    review: ValuationEligibilityReview,
) -> ValuationEligibilityResult:
    """Require date/lease consistency, an eligible parent DCF, and claim review."""

    if dcf_eligibility.calculation_output_id != bridge.parent_dcf_output_id:
        raise ValueError("parent DCF eligibility does not match claim bridge")
    additional_failed = (
        *bridge.failed_structural_checks,
        *(("parent_dcf_eligibility",)
          if dcf_eligibility.status is not GateStatus.PASS else ()),
    )
    return _assess(
        bridge.output_id,
        review,
        EQUITY_BRIDGE_REVIEW_CHECKS | frozenset({"lease_policy_and_claim_basis_reviewed"}),
        additional_failed=additional_failed,
        dependency_output_ids=(dcf_eligibility.output_id,),
    )


def eligible_valuation_amount(
    result: DcfResult | EquityClaimBridgeResult | DatedEquityClaimBridgeResult |
        PartialDatedEquityClaimBridgeResult,
    eligibility: ValuationEligibilityResult,
) -> Decimal:
    """Memo/release adapter must use a matching passed review to emit a value."""

    if isinstance(result, PartialDatedEquityClaimBridgeResult):
        raise TypeError("partial equity bridge has unknown claims and is not eligible")
    if eligibility.calculation_output_id != result.output_id:
        raise ValueError("eligibility does not match valuation output_id")
    if eligibility.status is not GateStatus.PASS:
        raise ValueError("valuation is not eligible for release")
    return result.total_value if isinstance(result, DcfResult) else result.equity_value


def _assess(
    calculation_output_id: str,
    review: ValuationEligibilityReview,
    required_checks: frozenset[str],
    *,
    additional_failed: tuple[str, ...] = (),
    dependency_output_ids: tuple[str, ...] = (),
) -> ValuationEligibilityResult:
    failed = tuple(
        sorted({*additional_failed, *(name for name in required_checks if review.checks.get(name) is not True)})
    )
    status = GateStatus.WITHHELD if failed else GateStatus.PASS
    output_id = _output_id(
        "m1_valuation_review",
        {
            "schema_version": 1,
            "calculation_output_id": calculation_output_id,
            "review_id": review.review_id,
            "reviewer_id": review.reviewer_id,
            "reviewed_at": review.reviewed_at.astimezone(UTC).isoformat(),
            "checks": sorted(review.checks.items()),
            "status": status.value,
            "failed_checks": failed,
            "dependency_output_ids": dependency_output_ids,
        },
    )
    return ValuationEligibilityResult(
        calculation_output_id=calculation_output_id,
        review_id=review.review_id,
        reviewer_id=review.reviewer_id,
        reviewed_at=review.reviewed_at,
        status=status,
        failed_checks=failed,
        dependency_output_ids=dependency_output_ids,
        output_id=output_id,
    )


def _output_id(prefix: str, payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()}"


def _dated_dcf_provenance(inputs: DcfInputs) -> None:
    """Require a dated Core path and independently identified rate/terminal bases."""

    if not isinstance(inputs.valuation_date, date) or isinstance(inputs.valuation_date, datetime):
        raise TypeError("dated DCF requires valuation_date")
    if not isinstance(inputs.information_cutoff, datetime) or (
        inputs.information_cutoff.tzinfo is None
        or inputs.information_cutoff.utcoffset() is None
    ):
        raise ValueError("dated DCF requires offset-aware information_cutoff")
    if inputs.valuation_date > inputs.information_cutoff.date():
        raise ValueError("valuation_date is after information_cutoff")
    if not isinstance(inputs.first_forecast_period_start, date) or isinstance(
        inputs.first_forecast_period_start, datetime
    ):
        raise TypeError("dated DCF requires first_forecast_period_start")
    if inputs.valuation_date < inputs.first_forecast_period_start - timedelta(days=1):
        raise ValueError("valuation_date precedes the Core opening balance date")
    for name in ("case_id", "operating_baseline_output_id", "core_cash_flow_path_output_id",
                 "economic_scope_id", "unit"):
        _nonempty(getattr(inputs, name), name)
    if not isinstance(inputs.accounting_scope, AccountingScope):
        raise TypeError("dated DCF requires accounting_scope")
    first_start = inputs.annual_cash_flows[0].period_end
    if first_start is not None and inputs.valuation_date >= first_start:
        raise ValueError("valuation_date must precede the first forecast period end")
    for name in ("discount_rate_available_at", "terminal_state_available_at"):
        available = getattr(inputs, name)
        if not isinstance(available, datetime) or (
            available.tzinfo is None or available.utcoffset() is None
        ):
            raise ValueError(f"{name} must be offset-aware")
        if available > inputs.information_cutoff:
            raise ValueError(f"{name} is after information_cutoff")
        if available.astimezone(inputs.information_cutoff.tzinfo).date() > inputs.valuation_date:
            raise ValueError(f"{name} is after valuation_date")
    for name in ("discount_rate_basis_source_ids", "terminal_state_basis_source_ids"):
        source_ids = getattr(inputs, name)
        if not isinstance(source_ids, tuple) or not source_ids:
            raise ValueError(f"{name} requires at least one source ID")
        for source_id in source_ids:
            _nonempty(source_id, "basis_source_id")
        if len(set(source_ids)) != len(source_ids):
            raise ValueError(f"{name} contains a duplicate source ID")
    _nonempty(inputs.discount_rate_rationale, "discount_rate_rationale")
    _nonempty(inputs.terminal_cash_flow_rationale, "terminal_cash_flow_rationale")
    if inputs.terminal_economics is not None:
        economics = inputs.terminal_economics
        if not isinstance(economics, TerminalOperatingEconomics):
            raise TypeError("terminal_economics must be TerminalOperatingEconomics")
        if economics.available_at > inputs.information_cutoff or (
            economics.available_at.astimezone(
                inputs.information_cutoff.tzinfo
            ).date() > inputs.valuation_date
        ):
            raise ValueError("terminal economics are unavailable at valuation date")
        if economics.assumption_id != inputs.terminal_state_assumption_id:
            raise ValueError("terminal economics assumption ID differs from DCF terminal state")
        if economics.growth_rate != inputs.terminal_growth_rate:
            raise ValueError("terminal economics growth differs from DCF growth")
        if economics.next_year_fcff != inputs.terminal_next_cash_flow:
            raise ValueError("terminal cash flow differs from sustainable operating economics")
        if economics.final_core_fcff is not None and (
            economics.final_core_fcff != inputs.annual_cash_flows[-1].amount
            or economics.final_core_fcff_output_id != inputs.annual_cash_flows[-1].output_id
        ):
            raise ValueError("terminal transition differs from pinned final Core FCFF")
        if not set(economics.basis_source_ids).issubset(
            inputs.terminal_state_basis_source_ids
        ):
            raise ValueError("terminal economics sources are absent from DCF basis")


def _finite(value: Decimal, name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal")
    return value


def _nonempty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
