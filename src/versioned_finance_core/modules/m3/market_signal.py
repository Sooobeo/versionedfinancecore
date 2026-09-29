"""Preserve external credit observations without turning them into model PDs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class MarketSignalType(StrEnum):
    RATING = "RATING"
    SPREAD = "SPREAD"
    TRADE = "TRADE"


class MarketSignalState(StrEnum):
    OBSERVED_EXTERNAL_SIGNAL = "OBSERVED_EXTERNAL_SIGNAL"
    NO_PUBLIC_MARKET_SIGNAL = "NO_PUBLIC_MARKET_SIGNAL"
    WITHHELD = "WITHHELD"


@dataclass(frozen=True)
class ExternalMarketSignal:
    instrument_id: str
    signal_type: MarketSignalType
    observed_value: str | Decimal
    observed_at: datetime
    source_id: str
    rights_cleared: bool
    unit: str


@dataclass(frozen=True)
class MarketSignalAssessment:
    state: MarketSignalState
    instrument_id: str
    signal_type: MarketSignalType | None
    observed_value: str | Decimal | None
    observed_at: datetime | None
    source_id: str | None
    limitation: str


def assess_external_market_signal(
    signal: ExternalMarketSignal | None,
    *, instrument_id: str,
    information_cutoff: datetime,
) -> MarketSignalAssessment:
    """Keep an eligible as-of observation; do not infer PD, LGD or funding cost."""

    if not instrument_id:
        raise ValueError("instrument_id is required")
    if information_cutoff.tzinfo is None or information_cutoff.utcoffset() is None:
        raise ValueError("information_cutoff must be timezone aware")
    if signal is None:
        return MarketSignalAssessment(
            MarketSignalState.NO_PUBLIC_MARKET_SIGNAL, instrument_id,
            None, None, None, None, "No eligible public observation supplied.",
        )
    if signal.observed_at.tzinfo is None or signal.observed_at.utcoffset() is None:
        raise ValueError("observed_at must be timezone aware")
    if signal.observed_at > information_cutoff:
        raise ValueError("market signal was observed after the information cutoff")
    if signal.instrument_id != instrument_id:
        raise ValueError("market signal instrument does not match the claim")
    if not signal.source_id or not signal.unit or not signal.rights_cleared:
        return MarketSignalAssessment(
            MarketSignalState.WITHHELD, instrument_id, signal.signal_type,
            None, None, signal.source_id or None,
            "Source, unit or data-use right is not established.",
        )
    value = signal.observed_value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("observed market value must be finite")
    elif not isinstance(value, str) or not value.strip():
        raise ValueError("observed market value must be nonblank text or Decimal")
    return MarketSignalAssessment(
        MarketSignalState.OBSERVED_EXTERNAL_SIGNAL, instrument_id,
        signal.signal_type, value, signal.observed_at, signal.source_id,
        "External observation only; no model PD, LGD or issuer rating inferred.",
    )
