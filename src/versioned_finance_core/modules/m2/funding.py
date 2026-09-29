"""M2 closing cash sources/uses and confirmed funding, pinned to Core.

Amounts come from the same normalized cash components used by the financial
Core's SOURCES_USES view. This layer classifies their closing purpose and
availability; it does not book cash, draw debt, or test liquidity troughs.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from versioned_finance_core.contracts import ClaimTag, GateStatus, KnowledgeState, Period, ScopeRef
from versioned_finance_core.financial_core import (
    CashComponentInput,
    CashInclusionResult,
    CashView,
    aggregate_cash_components,
)
from versioned_finance_core.financial_core.identities import _exact_sum

Money = Decimal | KnowledgeState


class ClosingCashSide(StrEnum):
    SOURCE = "SOURCE"
    USE = "USE"


class ClosingCashKind(StrEnum):
    ACQUIRER_CASH = "ACQUIRER_CASH"
    DEBT_CASH_PROCEEDS = "DEBT_CASH_PROCEEDS"
    EQUITY_CASH_PROCEEDS = "EQUITY_CASH_PROCEEDS"
    ASSET_SALE_CASH_PROCEEDS = "ASSET_SALE_CASH_PROCEEDS"
    OTHER_CASH_SOURCE = "OTHER_CASH_SOURCE"
    SELLER_CASH_PAYMENT = "SELLER_CASH_PAYMENT"
    TARGET_DEBT_CASH_REPAYMENT = "TARGET_DEBT_CASH_REPAYMENT"
    TRANSACTION_CASH_FEE = "TRANSACTION_CASH_FEE"
    OTHER_CASH_USE = "OTHER_CASH_USE"


class FundingAvailability(StrEnum):
    SETTLED_OR_ACCESSIBLE = "SETTLED_OR_ACCESSIBLE"
    COMMITTED_DRAWABLE = "COMMITTED_DRAWABLE"
    COMMITTED_CONDITIONAL = "COMMITTED_CONDITIONAL"
    UNCOMMITTED = "UNCOMMITTED"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


_SOURCE_KINDS = {
    ClosingCashKind.ACQUIRER_CASH,
    ClosingCashKind.DEBT_CASH_PROCEEDS,
    ClosingCashKind.EQUITY_CASH_PROCEEDS,
    ClosingCashKind.ASSET_SALE_CASH_PROCEEDS,
    ClosingCashKind.OTHER_CASH_SOURCE,
}
_USE_KINDS = set(ClosingCashKind) - _SOURCE_KINDS
_CONFIRMED = {
    FundingAvailability.SETTLED_OR_ACCESSIBLE,
    FundingAvailability.COMMITTED_DRAWABLE,
}


@dataclass(frozen=True, slots=True)
class ClosingCashLine:
    """One signed Core cash component classified for a single option close.

    SOURCE facts are positive, USE facts negative. ``availability_source_id``
    supports the funding claim separately from the amount's fact provenance.
    COMMITTED_CONDITIONAL and UNCOMMITTED amounts are visible in the nominal
    plan but never count as confirmed cash at close.
    """

    option_id: str
    event_date: date
    economic_event_id: str
    side: ClosingCashSide
    kind: ClosingCashKind
    availability: FundingAvailability
    component: CashComponentInput
    classification_source_id: str
    availability_source_id: str = ""


@dataclass(frozen=True, slots=True)
class FundingLineResult:
    component_id: str
    normalized_fact_id: str
    amount_source_id: str
    economic_event_id: str
    side: ClosingCashSide
    kind: ClosingCashKind
    availability: FundingAvailability
    signed_amount: Money
    classification_source_id: str
    availability_source_id: str

    def as_dict(self) -> dict[str, str]:
        return {
            "component_id": self.component_id,
            "normalized_fact_id": self.normalized_fact_id,
            "amount_source_id": self.amount_source_id,
            "economic_event_id": self.economic_event_id,
            "side": self.side.value,
            "kind": self.kind.value,
            "availability": self.availability.value,
            "signed_amount": _text(self.signed_amount),
            "classification_source_id": self.classification_source_id,
            "availability_source_id": self.availability_source_id,
        }


@dataclass(frozen=True, slots=True)
class FundingPlanResult:
    output_id: str
    case_id: str
    option_id: str
    version_id: str
    scope: ScopeRef
    period: Period
    settlement_date: date
    currency: str
    unit: str
    core_output_id: str
    recomputed_core_output_id: str
    core_content_identity_status: GateStatus
    lines: tuple[FundingLineResult, ...]
    planned_sources: Money
    planned_uses: Money
    sources_uses_residual: Money
    core_reconciliation_residual: Money
    settled_or_accessible_sources: Money
    committed_drawable_sources: Money
    committed_conditional_sources: Money
    uncommitted_sources: Money
    unknown_availability_sources: Money
    confirmed_funding_gap: Money
    status: GateStatus
    evidence_or_assumption_ids: tuple[str, ...]
    claim_tag: ClaimTag = ClaimTag.DERIVED

    def as_dict(self) -> dict[str, object]:
        return {
            "output_id": self.output_id,
            "case_id": self.case_id,
            "option_id": self.option_id,
            "version_id": self.version_id,
            "scope": self.scope.key(),
            "period": self.period.key(),
            "settlement_date": self.settlement_date.isoformat(),
            "currency": self.currency,
            "unit": self.unit,
            "core_output_id": self.core_output_id,
            "recomputed_core_output_id": self.recomputed_core_output_id,
            "core_content_identity_status": self.core_content_identity_status.value,
            "claim_tag": self.claim_tag.value,
            "lines": [line.as_dict() for line in self.lines],
            "planned_sources": _text(self.planned_sources),
            "planned_uses": _text(self.planned_uses),
            "sources_uses_residual": _text(self.sources_uses_residual),
            "core_reconciliation_residual": _text(self.core_reconciliation_residual),
            "settled_or_accessible_sources": _text(self.settled_or_accessible_sources),
            "committed_drawable_sources": _text(self.committed_drawable_sources),
            "committed_conditional_sources": _text(self.committed_conditional_sources),
            "uncommitted_sources": _text(self.uncommitted_sources),
            "unknown_availability_sources": _text(self.unknown_availability_sources),
            "confirmed_funding_gap": _text(self.confirmed_funding_gap),
            "status": self.status.value,
            "evidence_or_assumption_ids": list(self.evidence_or_assumption_ids),
        }


def _required(value: str, name: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} is required without surrounding whitespace")


def _text(value: Money) -> str:
    return value.value if isinstance(value, KnowledgeState) else str(value)


def _money(value: Money, name: str) -> Money:
    if isinstance(value, KnowledgeState):
        if value in {KnowledgeState.KNOWN, KnowledgeState.NM, KnowledgeState.NOT_APPLICABLE}:
            raise ValueError(f"{name} needs a Decimal or a valid missing cash state")
        return value
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be Decimal or KnowledgeState")
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
    return value


def _missing(values: Iterable[Money]) -> KnowledgeState:
    states = {value for value in values if isinstance(value, KnowledgeState)}
    if KnowledgeState.WITHHELD in states:
        return KnowledgeState.WITHHELD
    if KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA in states:
        return KnowledgeState.NOT_TESTABLE_FROM_PUBLIC_DATA
    return KnowledgeState.UNKNOWN


def _sum_money(values: Iterable[Money]) -> Money:
    selected = tuple(values)
    if any(isinstance(value, KnowledgeState) for value in selected):
        return _missing(selected)
    return _exact_sum(selected)


def _subtract(left: Money, right: Money) -> Money:
    if isinstance(left, Decimal) and isinstance(right, Decimal):
        return _exact_sum((left, right.copy_negate()))
    return _missing((left, right))


def _category_total(lines: tuple[FundingLineResult, ...], availability: FundingAvailability) -> Money:
    return _sum_money(
        line.signed_amount for line in lines
        if line.side is ClosingCashSide.SOURCE and line.availability is availability
    )


def evaluate_funding_plan(
    *,
    option_id: str,
    core_cash: CashInclusionResult,
    settlement_date: date,
    lines: Iterable[ClosingCashLine],
    all_core_components: Iterable[CashComponentInput] | None = None,
) -> FundingPlanResult:
    """Reconcile closing cash and show the gap after confirmed sources.

    The Core aggregation is repeated *only* as an independent content-identity
    check. If Core includes non-closing components, supply its complete input
    set in ``all_core_components``. Otherwise identity is unverified and the
    status stays WITHHELD, even when signed net cash agrees.

    A zero funding gap only covers this dated closing cash plan. It is not a
    finding on obligor-accessible cash, cash trough, covenant, or refinancing;
    those require the separate M3 lens.
    """

    _required(option_id, "option_id")
    if not isinstance(core_cash, CashInclusionResult):
        raise TypeError("core_cash must be a CashInclusionResult")
    if not isinstance(settlement_date, date) or isinstance(settlement_date, datetime):
        raise TypeError("settlement_date must be a date")
    if not core_cash.period.start <= settlement_date <= core_cash.period.end:
        raise ValueError("settlement_date must fall inside the pinned Core period")
    for name, value in (
        ("Core output_id", core_cash.output_id),
        ("Core case_id", core_cash.case_id),
        ("Core version_id", core_cash.version_id),
        ("Core currency", core_cash.currency),
        ("Core unit", core_cash.unit),
    ):
        _required(value, name)
    entries = tuple(lines)
    if not entries:
        raise ValueError("at least one source and one use are required")

    expected_view = core_cash.total_for(CashView.SOURCES_USES)
    expected_ids = set(expected_view.component_ids)
    expected_facts = set(expected_view.normalized_fact_ids)
    if len(expected_ids) != len(expected_view.component_ids):
        raise ValueError("duplicate Core SOURCES_USES component ID")
    if len(expected_facts) != len(expected_view.normalized_fact_ids):
        raise ValueError("duplicate Core SOURCES_USES normalized fact ID")
    _money(expected_view.value, "Core SOURCES_USES value")

    seen_components: set[str] = set()
    seen_facts: set[str] = set()
    seen_raw_facts: set[str] = set()
    seen_events: set[str] = set()
    results: list[FundingLineResult] = []
    for line in entries:
        if line.option_id != option_id:
            raise ValueError("funding line option_id mismatch")
        if line.event_date != settlement_date:
            raise ValueError("funding line event_date mismatch")
        if not isinstance(line.side, ClosingCashSide) or not isinstance(line.kind, ClosingCashKind):
            raise TypeError("funding line side and kind must use their enums")
        if not isinstance(line.availability, FundingAvailability):
            raise TypeError("funding line availability must use its enum")
        _required(line.economic_event_id, "economic_event_id")
        _required(line.classification_source_id, "classification_source_id")
        component = line.component
        if not isinstance(component, CashComponentInput):
            raise TypeError("funding line component must be CashComponentInput")
        rule, fact = component.rule, component.fact
        rule.validate()
        if not rule.included_in_sources_uses:
            raise ValueError("funding component must be included in Core SOURCES_USES")
        if rule.metric_id != fact.metric_id:
            raise ValueError("funding component metric mismatch")
        if fact.case_id != core_cash.case_id or fact.version_id != core_cash.version_id:
            raise ValueError("funding component case/version mismatch")
        if fact.scope != core_cash.scope or fact.period != core_cash.period:
            raise ValueError("funding component scope/period mismatch")
        if fact.currency != core_cash.currency or fact.unit != core_cash.unit:
            raise ValueError("funding component currency/unit mismatch")
        if rule.component_id in seen_components or fact.fact_id in seen_facts:
            raise ValueError("duplicate funding component or normalized fact")
        if fact.source_fact_id in seen_raw_facts:
            raise ValueError("raw fact counted twice in closing cash")
        if line.economic_event_id in seen_events:
            raise ValueError("economic event counted twice in closing cash")
        seen_components.add(rule.component_id)
        seen_facts.add(fact.fact_id)
        seen_raw_facts.add(fact.source_fact_id)
        seen_events.add(line.economic_event_id)
        amount = _money(fact.value, "funding line amount")
        if line.side is ClosingCashSide.SOURCE:
            if line.kind not in _SOURCE_KINDS:
                raise ValueError("cash USE kind cannot be classified as SOURCE")
            if line.kind in {
                ClosingCashKind.ACQUIRER_CASH,
                ClosingCashKind.DEBT_CASH_PROCEEDS,
                ClosingCashKind.EQUITY_CASH_PROCEEDS,
            } and rule.included_in_fcff:
                raise ValueError("funding cash source cannot enter enterprise FCFF")
            if line.kind is ClosingCashKind.ACQUIRER_CASH and rule.included_in_liquidity:
                raise ValueError("existing acquirer cash cannot be a new LIQUIDITY inflow")
            if line.availability is FundingAvailability.NOT_APPLICABLE:
                raise ValueError("SOURCE requires a funding availability state")
            _required(line.availability_source_id, "availability_source_id")
            _required(rule.funding_source_id or "", "funding_source_id")
            if isinstance(amount, Decimal) and amount < 0:
                raise ValueError("SOURCE cash amount must be nonnegative")
        else:
            if line.kind not in _USE_KINDS:
                raise ValueError("cash SOURCE kind cannot be classified as USE")
            if line.availability is not FundingAvailability.NOT_APPLICABLE:
                raise ValueError("USE funding availability must be NOT_APPLICABLE")
            if line.availability_source_id:
                raise ValueError("USE must not carry an availability_source_id")
            _required(rule.obligation_id or "", "obligation_id")
            if isinstance(amount, Decimal) and amount > 0:
                raise ValueError("USE cash amount must be nonpositive")
        _required(fact.provenance.source_id, "amount source_id")
        results.append(FundingLineResult(
            component_id=rule.component_id,
            normalized_fact_id=fact.fact_id,
            amount_source_id=fact.provenance.source_id,
            economic_event_id=line.economic_event_id,
            side=line.side,
            kind=line.kind,
            availability=line.availability,
            signed_amount=amount,
            classification_source_id=line.classification_source_id,
            availability_source_id=line.availability_source_id,
        ))

    if not any(line.side is ClosingCashSide.SOURCE for line in results):
        raise ValueError("closing cash plan requires at least one SOURCE")
    if not any(line.side is ClosingCashSide.USE for line in results):
        raise ValueError("closing cash plan requires at least one USE")
    if seen_components != expected_ids or seen_facts != expected_facts:
        raise ValueError("funding lines do not match pinned Core SOURCES_USES components")

    canonical_inputs = (
        tuple(all_core_components) if all_core_components is not None
        else tuple(line.component for line in entries)
    )
    canonical_by_id = {item.rule.component_id: item for item in canonical_inputs}
    if len(canonical_by_id) != len(canonical_inputs):
        raise ValueError("duplicate component in all_core_components")
    if any(canonical_by_id.get(line.component.rule.component_id) != line.component for line in entries):
        raise ValueError("funding line differs from the matching full Core component")
    recomputed_core = aggregate_cash_components(
        canonical_inputs, case_id=core_cash.case_id, version_id=core_cash.version_id
    )
    identity_status = (
        GateStatus.PASS if recomputed_core.output_id == core_cash.output_id
        else GateStatus.WITHHELD
    )

    ordered = tuple(sorted(results, key=lambda line: line.component_id))
    sources = _sum_money(
        line.signed_amount for line in ordered if line.side is ClosingCashSide.SOURCE
    )
    uses = _sum_money(
        line.signed_amount.copy_negate() if isinstance(line.signed_amount, Decimal)
        else line.signed_amount
        for line in ordered if line.side is ClosingCashSide.USE
    )
    residual = _subtract(sources, uses)
    core_residual = _subtract(residual, expected_view.value)
    accessible = _category_total(ordered, FundingAvailability.SETTLED_OR_ACCESSIBLE)
    drawable = _category_total(ordered, FundingAvailability.COMMITTED_DRAWABLE)
    conditional = _category_total(ordered, FundingAvailability.COMMITTED_CONDITIONAL)
    uncommitted = _category_total(ordered, FundingAvailability.UNCOMMITTED)
    unknown = _category_total(ordered, FundingAvailability.UNKNOWN)
    if isinstance(uses, Decimal) and isinstance(accessible, Decimal) and isinstance(drawable, Decimal):
        if any(line.availability is FundingAvailability.UNKNOWN for line in ordered):
            gap: Money = KnowledgeState.UNKNOWN
        else:
            confirmed = _exact_sum((accessible, drawable))
            difference = _subtract(uses, confirmed)
            gap = max(Decimal(0), difference)
    else:
        gap = _missing((uses, accessible, drawable))
    status = (
        GateStatus.PASS
        if identity_status is GateStatus.PASS
        and all(isinstance(value, Decimal) and value == 0
                for value in (residual, core_residual, gap))
        else GateStatus.WITHHELD
    )
    evidence_ids = tuple(sorted({
        source_id for line in ordered
        for source_id in (line.amount_source_id, line.classification_source_id,
                          line.availability_source_id)
        if source_id
    }))
    identity = {
        "formula": "m2_closing_funding_v1",
        "option_id": option_id,
        "core_output_id": core_cash.output_id,
        "recomputed_core_output_id": recomputed_core.output_id,
        "core_content_identity_status": identity_status.value,
        "case_id": core_cash.case_id,
        "version_id": core_cash.version_id,
        "scope": core_cash.scope.key(),
        "period": core_cash.period.key(),
        "settlement_date": settlement_date.isoformat(),
        "currency": core_cash.currency,
        "unit": core_cash.unit,
        "core_sources_uses_value": _text(expected_view.value),
        "lines": [line.as_dict() for line in ordered],
        "planned_sources": _text(sources),
        "planned_uses": _text(uses),
        "sources_uses_residual": _text(residual),
        "core_reconciliation_residual": _text(core_residual),
        "confirmed_funding_gap": _text(gap),
    }
    digest = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return FundingPlanResult(
        output_id=f"m2_funding_{digest}",
        case_id=core_cash.case_id,
        option_id=option_id,
        version_id=core_cash.version_id,
        scope=core_cash.scope,
        period=core_cash.period,
        settlement_date=settlement_date,
        currency=core_cash.currency,
        unit=core_cash.unit,
        core_output_id=core_cash.output_id,
        recomputed_core_output_id=recomputed_core.output_id,
        core_content_identity_status=identity_status,
        lines=ordered,
        planned_sources=sources,
        planned_uses=uses,
        sources_uses_residual=residual,
        core_reconciliation_residual=core_residual,
        settled_or_accessible_sources=accessible,
        committed_drawable_sources=drawable,
        committed_conditional_sources=conditional,
        uncommitted_sources=uncommitted,
        unknown_availability_sources=unknown,
        confirmed_funding_gap=gap,
        status=status,
        evidence_or_assumption_ids=evidence_ids,
    )
