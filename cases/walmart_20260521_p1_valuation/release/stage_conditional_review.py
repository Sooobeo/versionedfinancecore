"""Stage this case's withheld P1 artifacts with explicit output identities."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from versioned_finance_core.orchestration.release import stage_release

CASE = Path(__file__).resolve().parents[1]
CORE_OUTPUTS = (
    "normalized_actuals.csv", "core_outputs.json", "memo_fields.json",
    "build_metadata.json",
)
CONDITIONAL_OUTPUTS = (
    "02_financial_core/conditional_linked_forecast.json",
    "02_financial_core/conditional_scenario_drivers.csv",
    "03_m1_operating_forecast_valuation/conditional_valuation_screen.json",
    "03_m1_operating_forecast_valuation/conditional_memo_fields.json",
    "03_m1_operating_forecast_valuation/forecast_versions.csv",
    "03_m1_operating_forecast_valuation/valuation_runs.csv",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-build", type=Path, required=True)
    parser.add_argument("--stage-root", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(
        (CASE / "02_financial_core" / "conditional_model_config.json").read_text(
            encoding="utf-8"
        )
    )
    external = {f"outputs/{name}": args.core_build / name for name in CORE_OUTPUTS}
    reproduction = (
        "Set PYTHONPATH=src; run `python -m versioned_finance_core build-core "
        "cases/walmart_20260521_p1_valuation --build-root <fresh-root>`; "
        "then `python cases/walmart_20260521_p1_valuation/02_financial_core/"
        "build_conditional_model.py --normalized-actuals <core-build>/"
        "normalized_actuals.csv --output-dir <fresh-output>`; "
        "see 07_validation_governance/handover.md"
    )
    staged = stage_release(
        CASE,
        args.stage_root,
        external_outputs=external,
        output_paths=(*external, *CONDITIONAL_OUTPUTS),
        memo_paths=(
            "outputs/memo_fields.json",
            "03_m1_operating_forecast_valuation/conditional_memo_fields.json",
        ),
        reproduction_command=reproduction,
        known_limitations=tuple(config["limitations"]),
    )
    print(staged)


if __name__ == "__main__":
    main()
