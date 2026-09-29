"""Canonical inclusion of already-normalized, signed cash components.

The six views share each component's one pinned NormalizedFact amount. This
module does not derive FCFF, FCFE, CFADS, tax, or financing assumptions; the
case rule explicitly determines where an amount is included.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from versioned_finance_core.contracts import KnowledgeState, NormalizedFact, Period, ScopeRef
from versioned_finance_core.financial_core.identities import _exact_sum


class CashView(StrEnum):
    FCFF = "FCFF"
    FCFE = "FCFE"
    CFADS = "CFADS"
    DEBT_SERVICE = "DEBT_SERVICE"
    LIQUIDITY = "LIQUIDITY"
    SOURCES_USES = "SOURCES_USES"


_VIEW_FLAGS = {
    CashView.FCFF: "included_in_fcff",
    CashView.FCFE: "included_in_fcfe",
    CashView.CFADS: "included_in_cfads",
    CashView.DEBT_SERVICE: "included_in_debt_service",
    CashView.LIQUIDITY: "included_in_liquidity",
    CashView.SOURCES_USES: "included_in_sources_uses",
}


def _required(row: Mapping[str, str], key: str) -> str:
    value = row.get(key, "").strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _yes_no(row: Mapping[str, str], key: str) -> bool:
    value = row.get(key, "").strip()
    if value not in {"YES", "NO"}:
        raise ValueError(f"{key} must be YES or NO")
    return value == "YES"


@dataclass(frozen=True)
class CashComponentRule:
    component_id: str
    metric_id: str
    tax_basis: str
    obligation_id: str | None
    funding_source_id: str | None
    included_in_fcff: bool
    included_in_fcfe: bool
    included_in_cfads: bool
    included_in_debt_service: bool
    included_in_liquidity: bool
    included_in_sources_uses: bool
    display_name: str = ""
    double_count_check: str = ""

    @classmethod
    def from_mapping(cls, row: Mapping[str, str]) -> CashComponentRule:
        """Parse exactly the six explicit YES/NO case-template inclusion flags."""

        rule = cls(
            component_id=_required(row, "cash_component_id"),
            metric_id=_required(row, "metric_id"),
            tax_basis=_required(row, "tax_basis"),
            obligation_id=row.get("obligation_id", "").strip() or None,
            funding_source_id=row.get("funding_source_id", "").strip() or None,
            included_in_fcff=_yes_no(row, "included_in_fcff"),
            included_in_fcfe=_yes_no(row, "included_in_fcfe"),
            included_in_cfads=_yes_no(row, "included_in_cfads"),
            included_in_debt_service=_yes_no(row, "included_in_debt_service"),
            included_in_liquidity=_yes_no(row, "included_in_liquidity"),
            included_in_sources_uses=_yes_no(row, "included_in_sources_uses"),
            display_name=row.get("display_name", "").strip(),
            double_count_check=row.get("double_count_check", "").strip(),
        )
        rule.validate()
        return rule

    def validate(self) -> None:
        if any(
            not value or value != value.strip()
            for value in (self.component_id, self.metric_id, self.tax_basis)
        ):
            raise ValueError("component_id, metric_id and tax_basis are required")
        for flag in _VIEW_FLAGS.values():
            if type(getattr(self, flag)) is not bool:
                raise TypeError(f"{flag} must be a boolean parsed from YES or NO")
        if self.included_in_cfads and self.included_in_debt_service:
            raise ValueError("one cash component cannot be in both CFADS and debt_service")

    def includes(self, view: CashView) -> bool:
        return getattr(self, _VIEW_FLAGS[view])


@dataclass(frozen=True)
class CashComponentInput:
    rule: CashComponentRule
    fact: NormalizedFact


@dataclass(frozen=True)
class CashViewTotal:
    view: CashView
    value: Decimal | KnowledgeState
    component_ids: tuple[str, ...]
    normalized_fact_ids: tuple[str, ...]
    unresolved_states: tuple[KnowledgeState, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "view": self.view.value,
            "value": self.value.value if isinstance(self.value, KnowledgeState) else str(self.value),
            "component_ids": list(self.component_ids),
            "normalized_fact_ids": list(self.normalized_fact_ids),
            "unresolved_states": [state.value for state in self.unresolved_states],
        }


@dataclass(frozen=True)
class CashInclusionResult:
    output_id: str
    case_id: str
    scope: ScopeRef
    version_id: str
    period: Period
    currency: str
    unit: str
    views: tuple[CashViewTotal, ...]

    def total_for(self, view: CashView | str) -> CashViewTotal:
        selected = CashView(view)
        return next(total for total in self.views if total.view is selected)

    def as_dict(self) -> dict[str, object]:
        return {
            "output_id": self.output_id,
            "case_id": self.case_id,
            "scope": self.scope.key(),
            "version_id": self.version_id,
            "period": self.period.key(),
            "currency": self.currency,
            "unit": self.unit,
            "views": [total.as_dict() for total in self.views],
        }


def _amount_text(value: Decimal | KnowledgeState) -> str:
    return value.value if isinstance(value, KnowledgeState) else str(value)


def _total(view: CashView, components: tuple[CashComponentInput, ...]) -> CashViewTotal:
    included = tuple(item for item in components if item.rule.includes(view))
    if not included:
        return CashViewTotal(view, KnowledgeState.NOT_APPLICABLE, (), (), ())
    states = tuple(
        sorted(
            {item.fact.value for item in included if isinstance(item.fact.value, KnowledgeState)},
            key=lambda state: state.value,
        )
    )
    if states:
        value: Decimal | KnowledgeState = states[0] if len(states) == 1 else KnowledgeState.UNKNOWN
    else:
        value = _exact_sum(item.fact.value for item in included)
    return CashViewTotal(
        view=view,
        value=value,
        component_ids=tuple(item.rule.component_id for item in included),
        normalized_fact_ids=tuple(item.fact.fact_id for item in included),
        unresolved_states=states,
    )


def aggregate_cash_components(
    components: Iterable[CashComponentInput], *, case_id: str, version_id: str
) -> CashInclusionResult:
    """Aggregate each signed fact once and reuse it through explicit view flags.

    A missing amount never contributes a zero. A view with mixed missing states
    returns UNKNOWN and also lists every underlying state for review.
    """

    if not case_id or not version_id:
        raise ValueError("case_id and version_id must pin the cash aggregation")
    entries = tuple(components)
    if not entries:
        raise ValueError("at least one cash component is required")
    first = entries[0].fact
    component_ids: set[str] = set()
    normalized_ids: set[str] = set()
    raw_ids: set[str] = set()
    normalized_keys: set[tuple[str, ...]] = set()
    for entry in entries:
        rule, fact = entry.rule, entry.fact
        rule.validate()
        if rule.component_id in component_ids:
            raise ValueError(f"duplicate cash component_id: {rule.component_id}")
        component_ids.add(rule.component_id)
        if fact.fact_id in normalized_ids or fact.source_fact_id in raw_ids or fact.key() in normalized_keys:
            raise ValueError(f"normalized fact is reused across cash components: {fact.fact_id}")
        normalized_ids.add(fact.fact_id)
        raw_ids.add(fact.source_fact_id)
        normalized_keys.add(fact.key())
        if rule.metric_id != fact.metric_id:
            raise ValueError(f"cash component metric mismatch: {rule.component_id}")
        if fact.case_id != case_id:
            raise ValueError(f"cash component case mismatch: {rule.component_id}")
        if fact.version_id != version_id:
            raise ValueError(f"cash component version mismatch: {rule.component_id}")
        if fact.scope != first.scope:
            raise ValueError(f"cash component scope mismatch: {rule.component_id}")
        if fact.period != first.period:
            raise ValueError(f"cash component period mismatch: {rule.component_id}")
        if fact.currency != first.currency:
            raise ValueError(f"cash component currency mismatch: {rule.component_id}")
        if fact.unit != first.unit:
            raise ValueError(f"cash component unit mismatch: {rule.component_id}")
        if fact.publication_status != first.publication_status:
            raise ValueError(f"cash component publication status mismatch: {rule.component_id}")
        if isinstance(fact.value, KnowledgeState):
            if fact.value is KnowledgeState.KNOWN:
                raise ValueError("KNOWN requires a Decimal cash amount")
        elif not isinstance(fact.value, Decimal):
            raise TypeError("cash component amount must be Decimal or KnowledgeState")
        elif not fact.value.is_finite():
            raise ValueError("cash component amount must be a finite Decimal")

    ordered = tuple(sorted(entries, key=lambda item: item.rule.component_id))
    views = tuple(_total(view, ordered) for view in CashView)
    identity = {
        "formula": "cash_inclusion_v1",
        "case_id": case_id,
        "scope": first.scope.key(),
        "version_id": version_id,
        "period": first.period.key(),
        "currency": first.currency,
        "unit": first.unit,
        "components": [
            {
                "component_id": item.rule.component_id,
                "metric_id": item.rule.metric_id,
                "tax_basis": item.rule.tax_basis,
                "obligation_id": item.rule.obligation_id,
                "funding_source_id": item.rule.funding_source_id,
                "flags": {view.value: item.rule.includes(view) for view in CashView},
                "fact_id": item.fact.fact_id,
                "source_fact_id": item.fact.source_fact_id,
                "source_id": item.fact.provenance.source_id,
                "snapshot_id": item.fact.provenance.snapshot_id,
                "content_sha256": item.fact.provenance.content_sha256,
                "mapping_version": item.fact.mapping_version,
                "publication_status": item.fact.publication_status.value,
                "amount": _amount_text(item.fact.value),
            }
            for item in ordered
        ],
    }
    digest = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return CashInclusionResult(
        output_id=f"cash_components_{digest}",
        case_id=case_id,
        scope=first.scope,
        version_id=version_id,
        period=first.period,
        currency=first.currency,
        unit=first.unit,
        views=views,
    )
