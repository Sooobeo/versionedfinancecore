"""Read-only memo projections of canonical core outputs."""

from __future__ import annotations

from dataclasses import dataclass

from versioned_finance_core.financial_core.cash_identity import CashIdentityResult
from versioned_finance_core.financial_core.scenario_cash import ScenarioCashResult


@dataclass(frozen=True)
class MemoField:
    output_id: str
    label: str
    value: str
    currency: str
    unit: str
    claim_tag: str

    def as_dict(self) -> dict[str, str]:
        return {
            "output_id": self.output_id,
            "label": self.label,
            "value": self.value,
            "currency": self.currency,
            "unit": self.unit,
            "claim_tag": self.claim_tag,
        }


def cash_identity_memo_field(result: CashIdentityResult) -> MemoField:
    """Expose the core residual exactly; this layer performs no calculation."""

    value = (
        str(result.residual)
        if result.residual is not None else result.knowledge_state.value
    )
    return MemoField(
        output_id=result.output_id,
        label="Cash roll-forward residual",
        value=value,
        currency=result.currency,
        unit=result.unit,
        claim_tag="D",
    )


def scenario_cash_memo_field(result: ScenarioCashResult) -> MemoField:
    """Expose the calculated scenario amount by ID with no reporting adjustment."""

    return MemoField(
        output_id=result.output_id,
        label="Scenario projected closing cash",
        value=str(result.projected_closing_cash),
        currency=result.currency,
        unit=result.unit,
        claim_tag="D",
    )
