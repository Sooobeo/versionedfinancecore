from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from versioned_finance_core.modules.m3 import (
    ExternalMarketSignal,
    MarketSignalState,
    MarketSignalType,
    assess_external_market_signal,
)

AS_OF = datetime(2026, 6, 30, tzinfo=timezone(timedelta(hours=9)))


def test_missing_signal_stays_missing() -> None:
    result = assess_external_market_signal(
        None, instrument_id="synthetic_bond", information_cutoff=AS_OF,
    )
    assert result.state is MarketSignalState.NO_PUBLIC_MARKET_SIGNAL
    assert result.observed_value is None


def test_observation_is_preserved_without_implied_pd_or_rating() -> None:
    signal = ExternalMarketSignal(
        "synthetic_bond", MarketSignalType.SPREAD, Decimal("0.0125"),
        AS_OF, "synthetic_public_quote", True, "DECIMAL_RATE",
    )
    result = assess_external_market_signal(
        signal, instrument_id="synthetic_bond", information_cutoff=AS_OF,
    )
    assert result.state is MarketSignalState.OBSERVED_EXTERNAL_SIGNAL
    assert result.observed_value == Decimal("0.0125")
    assert "no model PD" in result.limitation


def test_rights_and_vintage_gate_fail_closed() -> None:
    unavailable_rights = ExternalMarketSignal(
        "synthetic_bond", MarketSignalType.RATING, "BBB", AS_OF,
        "synthetic_rating", False, "AGENCY_SCALE",
    )
    result = assess_external_market_signal(
        unavailable_rights, instrument_id="synthetic_bond", information_cutoff=AS_OF,
    )
    assert result.state is MarketSignalState.WITHHELD
    assert result.observed_value is None

    future = ExternalMarketSignal(
        "synthetic_bond", MarketSignalType.TRADE, Decimal(99),
        AS_OF + timedelta(days=1), "synthetic_trade", True, "PRICE",
    )
    with pytest.raises(ValueError, match="after the information cutoff"):
        assess_external_market_signal(
            future, instrument_id="synthetic_bond", information_cutoff=AS_OF,
        )
    with pytest.raises(ValueError, match="does not match"):
        assess_external_market_signal(
            unavailable_rights, instrument_id="other_bond", information_cutoff=AS_OF,
        )
