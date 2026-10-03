"""Synthetic CAPM/WACC known answers and evidence boundary tests."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal, localcontext

import pytest

from versioned_finance_core.contracts.enums import AccountingScope, GateStatus
from versioned_finance_core.modules.m1.cost_of_capital import (
    BetaBasis,
    DebtValueBasis,
    SourcedValuationParameter,
    WaccInputs,
    calculate_wacc,
)
from versioned_finance_core.modules.m1.valuation import (
    LeasePolicyEvidence,
    LeaseValuationTreatment,
    RateBasis,
)

AS_OF = date(2026, 5, 21)
AVAILABLE = datetime(2026, 5, 20, tzinfo=UTC)
CUTOFF = datetime(2026, 5, 21, 23, 59, tzinfo=UTC)


def _parameter(value: str, name: str, *, as_of: date = AS_OF,
               available: datetime = AVAILABLE) -> SourcedValuationParameter:
    return SourcedValuationParameter(
        Decimal(value), f"synthetic_{name}", (f"source_{name}",),
        as_of, available, f"Synthetic {name} basis",
    )


def _inputs() -> WaccInputs:
    return WaccInputs(
        case_id="synthetic_wacc", assumption_id="wacc_v1",
        valuation_date=AS_OF, information_cutoff=CUTOFF,
        accounting_scope=AccountingScope.CONSOLIDATED,
        economic_scope_id="synthetic_group", currency="USD", rate_basis=RateBasis.NOMINAL,
        risk_free_rate=_parameter("0.04", "risk_free"),
        levered_beta=_parameter("1", "beta"),
        equity_risk_premium=_parameter("0.05", "erp"),
        marginal_tax_rate=_parameter("0.25", "tax"),
        share_price=_parameter("10", "price"),
        shares_outstanding=_parameter("90", "shares"),
        debt_value=_parameter("100", "debt"),
        beta_basis=BetaBasis.COMPANY_OBSERVED,
        debt_value_basis=DebtValueBasis.MARKET_VALUE,
        lease_policy=LeasePolicyEvidence(
            LeaseValuationTreatment.OPERATING_COST_INCLUDED,
            "synthetic_lease_policy", ("lease_source",), AVAILABLE,
            lease_cost_in_fcff=True,
            lease_liability_in_debt_like_claims=False,
            lease_financing_in_wacc=False,
        ),
        marginal_debt_spread=_parameter("0.02", "debt_spread"),
    )


def test_wacc_capm_and_market_weights_known_answer() -> None:
    inputs = _inputs()
    result = calculate_wacc(inputs)
    assert result.market_equity_value == Decimal(900)
    assert result.equity_weight == Decimal("0.9")
    assert result.debt_weight == Decimal("0.1")
    assert result.cost_of_equity == Decimal("0.09")
    assert result.pre_tax_cost_of_debt == Decimal("0.06")
    assert result.after_tax_cost_of_debt == Decimal("0.0450")
    assert result.wacc == Decimal("0.08550")
    assert result.eligibility_status is GateStatus.NOT_EVALUATED
    assert result.output_id == calculate_wacc(inputs).output_id
    assert ("risk_free_rate_source_1", "source_risk_free") in result.input_lineage
    with localcontext() as decimal_context:
        decimal_context.prec = 16
        assert calculate_wacc(inputs).output_id == result.output_id


def test_stale_proxy_and_lease_mismatch_remain_withheld() -> None:
    inputs = _inputs()
    altered = replace(
        inputs,
        shares_outstanding=_parameter("90", "shares", as_of=date(2026, 3, 11)),
        debt_value=_parameter("100", "debt", as_of=date(2026, 4, 30)),
        beta_basis=BetaBasis.SECTOR_PROXY,
        debt_value_basis=DebtValueBasis.CARRYING_PROXY,
        lease_policy=replace(inputs.lease_policy, lease_liability_in_debt_like_claims=True),
    )
    result = calculate_wacc(altered)
    assert result.wacc == calculate_wacc(inputs).wacc
    assert result.eligibility_status is GateStatus.WITHHELD
    assert set(result.failed_structural_checks) == {
        "beta_company_fit", "market_debt_value_basis", "shares_outstanding_as_of_date",
        "debt_value_as_of_date", "lease_valuation_treatment",
    }


def test_late_erp_and_double_debt_rate_fail_closed() -> None:
    inputs = _inputs()
    with pytest.raises(ValueError, match="unavailable at information cutoff"):
        calculate_wacc(replace(
            inputs,
            equity_risk_premium=_parameter(
                "0.05", "erp", available=datetime(2026, 5, 22, tzinfo=UTC)
            ),
        ))
    with pytest.raises(ValueError, match="exactly one"):
        calculate_wacc(replace(
            inputs,
            marginal_pre_tax_debt_rate=_parameter("0.06", "debt_rate"),
        ))
    with pytest.raises(ValueError, match="nominal"):
        calculate_wacc(replace(inputs, rate_basis=RateBasis.REAL))
    with pytest.raises(ValueError, match="exceed -1"):
        calculate_wacc(replace(
            inputs, marginal_debt_spread=_parameter("-1.05", "debt_spread"),
        ))


def test_negative_observed_beta_is_not_silently_clipped() -> None:
    inputs = _inputs()
    result = calculate_wacc(replace(
        inputs, levered_beta=_parameter("-0.2", "negative_beta"),
    ))
    assert result.cost_of_equity == Decimal("0.030")


def test_utc_next_day_publication_is_same_local_valuation_date() -> None:
    inputs = _inputs()
    eastern = timezone(-timedelta(hours=4))
    local_cutoff = datetime(2026, 5, 21, 23, 59, tzinfo=eastern)
    utc_publication = datetime(2026, 5, 22, 2, tzinfo=UTC)
    result = calculate_wacc(replace(
        inputs,
        information_cutoff=local_cutoff,
        share_price=_parameter("10", "price", available=utc_publication),
    ))
    assert result.wacc == Decimal("0.08550")
