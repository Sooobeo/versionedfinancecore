"""A narrow, reproducible cash projection from a pinned scenario driver path."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from versioned_finance_core.contracts import KnowledgeState, NormalizedFact
from versioned_finance_core.financial_core.cash_identity import (
    CASH_ROLES,
    CashIdentitySpec,
    evaluate_cash_identity,
)
from versioned_finance_core.financial_core.identities import projected_closing_cash
from versioned_finance_core.financial_core.scenarios import (
    DriverPeriodKey,
    ScenarioDriverOverride,
    apply_absolute_scenario_overrides,
)


@dataclass(frozen=True)
class ScenarioCashResult:
    output_id: str
    baseline_output_id: str
    scenario_id: str
    scenario_version_id: str
    baseline_version_id: str
    projected_closing_cash: Decimal
    currency: str
    unit: str
    evidence_or_assumption_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "output_id": self.output_id,
            "baseline_output_id": self.baseline_output_id,
            "scenario_id": self.scenario_id,
            "scenario_version_id": self.scenario_version_id,
            "baseline_version_id": self.baseline_version_id,
            "projected_closing_cash": str(self.projected_closing_cash),
            "currency": self.currency,
            "unit": self.unit,
            "evidence_or_assumption_ids": list(self.evidence_or_assumption_ids),
            "knowledge_state": KnowledgeState.KNOWN.value,
            "claim_tag": "D",
        }


def project_cash_scenario(
    spec: CashIdentitySpec,
    normalized_facts: Iterable[NormalizedFact],
    overrides: Iterable[ScenarioDriverOverride],
) -> ScenarioCashResult:
    """Apply absolute overrides to the six normalized identity components.

    This first slice projects only the cash identity's stated driver periods.
    A broader linked P&L/BS/CF schedule must be provided by a later Core build.
    """

    facts = tuple(normalized_facts)
    identity = evaluate_cash_identity(spec, facts)
    if identity.knowledge_state is not KnowledgeState.KNOWN or identity.residual != 0:
        raise ValueError("cash scenario requires a known, exactly reconciled baseline")
    by_source_id = {fact.source_fact_id: fact for fact in facts}
    selected = {role: by_source_id[spec.source_fact_ids[role]] for role in CASH_ROLES}
    keys = {
        role: DriverPeriodKey(
            fact.metric_id, fact.period.start, fact.period.end, fact.unit
        )
        for role, fact in selected.items()
    }
    if len(set(keys.values())) != len(keys):
        raise ValueError("cash identity driver-period keys are not unique")
    baseline = {
        keys[role]: fact.value for role, fact in selected.items()
    }
    if any(not isinstance(value, Decimal) for value in baseline.values()):
        raise ValueError("scenario baseline contains nonnumeric knowledge states")
    selected_overrides = tuple(overrides)
    if any(override.mechanism != "ABSOLUTE_OVERRIDE" for override in selected_overrides):
        raise ValueError("cash scenario supports explicit ABSOLUTE_OVERRIDE only")
    path = apply_absolute_scenario_overrides(
        baseline, baseline_version_id=spec.version_id, overrides=selected_overrides
    )
    projected = projected_closing_cash(
        *(path.values[keys[role]] for role in CASH_ROLES[:-1])
    )
    identity_payload = {
        "formula": "cash_scenario_v1",
        "baseline_output_id": identity.output_id,
        "scenario_id": path.scenario_id,
        "scenario_version_id": path.scenario_version_id,
        "overrides": [
            {
                "driver_id": override.driver_id,
                "period_start": override.period_start.isoformat(),
                "period_end": override.period_end.isoformat(),
                "input_unit": override.input_unit,
                "input_value": str(override.input_value),
                "evidence_or_assumption_id": override.evidence_or_assumption_id,
            }
            for override in sorted(selected_overrides, key=lambda item: item.driver_period)
        ],
    }
    digest = hashlib.sha256(
        json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return ScenarioCashResult(
        output_id=f"scenario_cash_{digest}",
        baseline_output_id=identity.output_id,
        scenario_id=path.scenario_id,
        scenario_version_id=path.scenario_version_id,
        baseline_version_id=path.baseline_version_id,
        projected_closing_cash=projected,
        currency=identity.currency,
        unit=identity.unit,
        evidence_or_assumption_ids=tuple(sorted({
            override.evidence_or_assumption_id for override in selected_overrides
        })),
    )
