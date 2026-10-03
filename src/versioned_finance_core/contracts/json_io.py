"""Strict JSON decoding for versioned contracts and release controls."""

from __future__ import annotations

import json
import math
from collections.abc import Sequence


def _strict_object(pairs: Sequence[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_nonfinite_constant(token: str) -> object:
    raise ValueError(f"Non-finite JSON numeric constant is not allowed: {token}")


def _finite_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise ValueError(f"Non-finite JSON numeric value is not allowed: {token}")
    return value


def strict_json_loads(text: str) -> object:
    """Decode JSON while rejecting duplicate keys and non-finite numerics.

    Python's standard decoder otherwise silently accepts a duplicate key by
    retaining its final value, and accepts the non-standard NaN/Infinity
    constants.  Both behaviours are unsafe for versioned control artifacts.
    """

    return json.loads(
        text,
        object_pairs_hook=_strict_object,
        parse_constant=_reject_nonfinite_constant,
        parse_float=_finite_float,
    )
