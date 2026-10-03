"""Independent arithmetic check of the published DFS relative-period cash row.

This checks a rounded project-level forecast; it is not an as-of corporate
investment conclusion or a canonical option-world minus status-quo model.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parents[1]
MODEL = CASE_DIR / "04_m2_capital_allocation" / "dfs_project_model.csv"
OUTPUT = CASE_DIR / "04_m2_capital_allocation" / "dfs_reproduction.json"
REPOSITORY = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY / "src"))

from versioned_finance_core.financial_core import discount_relative_cash, implied_project_irr
from versioned_finance_core.orchestration.public_reproductions import (
    _load_dfs_rounded_cash,
    dfs_legacy_artifact,
    reproduce_dfs,
)


def load_rounded_cash(path: Path = MODEL) -> tuple[Decimal, ...]:
    """Compatibility wrapper around the shared, source-validated DFS loader."""

    if path.name != "dfs_project_model.csv" or path.parent.name != "04_m2_capital_allocation":
        raise ValueError("load_rounded_cash expects an M2 dfs_project_model.csv path")
    return _load_dfs_rounded_cash(path.parents[1])


def discounted_value(
    cash: tuple[Decimal, ...], annual_rate: Decimal, first_period_exponent: str
) -> Decimal:
    """Compatibility wrapper for the shared timing-hypothesis arithmetic."""

    return discount_relative_cash(cash, annual_rate, first_period_exponent)


def implied_irr(cash: tuple[Decimal, ...]) -> Decimal:
    """Compatibility wrapper for the shared project-IRR arithmetic."""

    return implied_project_irr(cash)


def reproduce() -> dict[str, str]:
    """Return the established artifact shape via the shared public adapter."""

    return dfs_legacy_artifact(reproduce_dfs(CASE_DIR))


def main() -> None:
    OUTPUT.write_text(
        json.dumps(reproduce(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(OUTPUT)


if __name__ == "__main__":
    main()
