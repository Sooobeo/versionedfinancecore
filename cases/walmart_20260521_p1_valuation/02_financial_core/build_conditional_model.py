"""Build this case's explicitly conditional Core and M1 review artifacts.

The calculation adapter lives in ``versioned_finance_core.orchestration``. This
case file supplies only its directory and default configuration path, preserving
the public command and function API used by the case handover and tests.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from versioned_finance_core.orchestration.conditional_model import (
    build_review_artifacts as _build_review_artifacts,
)
from versioned_finance_core.orchestration.conditional_model import review_csvs as _review_csvs

CASE = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = CASE / "02_financial_core" / "conditional_model_config.json"


def build_review_artifacts(
    *, normalized_actuals: Path, config_path: Path = DEFAULT_CONFIG
) -> dict[str, object]:
    """Return deterministic, review-only artifacts for the Walmart case."""
    return _build_review_artifacts(
        case_dir=CASE,
        normalized_actuals=normalized_actuals,
        config_path=config_path,
    )


def review_csvs(
    artifacts: dict[str, object], config_path: Path = DEFAULT_CONFIG
) -> dict[str, str]:
    """Format this case's review tables from canonical Core/M1 outputs."""
    return _review_csvs(artifacts, config_path=config_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--normalized-actuals", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--replace-staging", action="store_true")
    args = parser.parse_args()
    artifacts = build_review_artifacts(normalized_actuals=args.normalized_actuals)
    outputs = {
        "conditional_linked_forecast.json": artifacts["forecast"],
        "conditional_valuation_screen.json": artifacts["valuation"],
        "conditional_memo_fields.json": artifacts["memo_fields"],
    }
    csv_outputs = review_csvs(artifacts)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for filename in (*outputs, *csv_outputs):
        target = args.output_dir / filename
        if target.exists() and not args.replace_staging:
            parser.error(f"existing output requires --replace-staging: {target}")
    for filename, payload in outputs.items():
        (args.output_dir / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    for filename, payload in csv_outputs.items():
        (args.output_dir / filename).write_text(payload, encoding="utf-8")
    print(artifacts["forecast"]["core_path_sha256"])
    print(artifacts["valuation"]["dcf_screen"]["output_id"])


if __name__ == "__main__":
    main()
