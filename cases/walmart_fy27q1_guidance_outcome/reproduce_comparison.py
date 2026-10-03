"""Recreate the limited Q1 FY27 actual-to-public-guidance outcome artifact.

Run from the repository root with ``python cases/walmart_fy27q1_guidance_outcome/reproduce_comparison.py``.
Only local numeric facts and source locators are read; no network fetch is needed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "src"))

from versioned_finance_core.orchestration.public_reproductions import (
    guidance_legacy_artifact,
    reproduce_guidance,
)

CASE = Path(__file__).resolve().parent


def reproduce() -> dict[str, object]:
    """Return the established artifact shape via the shared public adapter."""

    return guidance_legacy_artifact(reproduce_guidance(CASE))


def main() -> None:
    print(json.dumps(reproduce(), ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
