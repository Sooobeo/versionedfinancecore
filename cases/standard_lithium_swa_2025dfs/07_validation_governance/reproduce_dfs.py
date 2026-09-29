"""Independent arithmetic check of the published DFS relative-period cash row.

This checks a rounded project-level forecast; it is not an as-of corporate
investment conclusion or a canonical option-world minus status-quo model.
"""

from __future__ import annotations

import csv
import json
from decimal import Decimal, getcontext
from pathlib import Path

getcontext().prec = 34

CASE_DIR = Path(__file__).resolve().parents[1]
MODEL = CASE_DIR / "04_m2_capital_allocation" / "dfs_project_model.csv"
OUTPUT = CASE_DIR / "04_m2_capital_allocation" / "dfs_reproduction.json"
PERIODS = ("-4", "-3", "-2", "-1", *(str(year) for year in range(1, 21)))
RATE = Decimal("0.08")
REPORTED_TOTAL = Decimal("4701.5")
REPORTED_NPV = Decimal("1275.0")
REPORTED_IRR = Decimal("0.182")


def load_rounded_cash(path: Path = MODEL) -> tuple[Decimal, ...]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if tuple(row["relative_period"] for row in rows) != PERIODS:
        raise ValueError("DFS relative-period labels changed")
    if rows[0]["knowledge_state"] != "UNKNOWN" or rows[0]["reported_post_tax_unlevered_fcff"]:
        raise ValueError("The disclosed -4 dash must remain unknown, not zero")
    for row in rows[1:]:
        if (
            row["knowledge_state"] != "KNOWN"
            or row["model_version_id"] != "swa_dfs_model_20251014"
            or row["currency"] != "USD"
            or row["unit"] != "real_2025_USD_million"
            or row["economic_scope_id"] != "swa_project_100pct_unlevered"
            or row["source_id"] != "sec_sli_swa_dfs_20251014"
        ):
            raise ValueError("DFS model value or scope metadata changed")
    return tuple(Decimal(row["reported_post_tax_unlevered_fcff"]) for row in rows[1:])


def discounted_value(
    cash: tuple[Decimal, ...], annual_rate: Decimal, first_period_exponent: str
) -> Decimal:
    """Check start-, middle-, or end-period conventions on relative years."""

    if annual_rate <= Decimal(-1):
        raise ValueError("annual rate must exceed -100%")
    factor = Decimal(1) + annual_rate
    if first_period_exponent == "0":
        offset = Decimal(1)
    elif first_period_exponent == "0.5":
        offset = factor.sqrt()
    elif first_period_exponent == "1":
        offset = factor
    else:
        raise ValueError("first_period_exponent must be 0, 0.5 or 1")
    return sum(value / (factor ** index * offset) for index, value in enumerate(cash))


def implied_irr(cash: tuple[Decimal, ...]) -> Decimal:
    """Bracket a sign-changing project rate; uniform timing offset does not alter IRR."""

    lower, upper = Decimal(0), Decimal(1)
    if discounted_value(cash, lower, "0.5") <= 0:
        raise ValueError("Expected positive NPV at a zero rate")
    if discounted_value(cash, upper, "0.5") >= 0:
        raise ValueError("IRR is not bracketed below 100%")
    for _ in range(160):
        middle = (lower + upper) / 2
        if discounted_value(cash, middle, "0.5") > 0:
            lower = middle
        else:
            upper = middle
    return (lower + upper) / 2


def reproduce() -> dict[str, str]:
    cash = load_rounded_cash()
    total = sum(cash)
    if total != REPORTED_TOTAL:
        raise ValueError("Rounded annual project FCFF does not sum to the published total")
    start_npv = discounted_value(cash, RATE, "0")
    middle_npv = discounted_value(cash, RATE, "0.5")
    end_npv = discounted_value(cash, RATE, "1")
    factor = Decimal(1) + RATE
    rounding_bound = Decimal("0.05") * sum(
        1 / (factor ** index * factor.sqrt()) for index in range(len(cash))
    )
    irr = implied_irr(cash)
    return {
        "model_version_id": "swa_dfs_model_20251014",
        "economic_scope_id": "swa_project_100pct_unlevered",
        "basis": "real_2025_USD_million",
        "relative_periods": "-4,-3,-2,-1,1..20",
        "excluded_dash_period": "-4",
        "published_total_fcff_F": str(REPORTED_TOTAL),
        "sum_of_rounded_annual_fcff_D": str(total),
        "published_npv_8pct_F": str(REPORTED_NPV),
        "npv_start_year_D": str(start_npv),
        "npv_mid_year_hypothesis_D": str(middle_npv),
        "npv_end_year_D": str(end_npv),
        "mid_year_difference_from_published_D": str(middle_npv - REPORTED_NPV),
        "maximum_annual_row_rounding_effect_D": str(rounding_bound),
        "published_irr_F": str(REPORTED_IRR),
        "irr_from_rounded_annual_fcff_D": str(irr),
        "timing_state": "MID_YEAR_IS_AN_INFERENCE_NOT_A_DISCLOSED_CONVENTION",
        "decision_state": "FEASIBILITY_ONLY",
    }


def main() -> None:
    OUTPUT.write_text(
        json.dumps(reproduce(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(OUTPUT)


if __name__ == "__main__":
    main()
