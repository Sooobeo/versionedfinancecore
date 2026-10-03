"""Print the fail-closed public M2 evidence-completeness output for Jincheon."""

from __future__ import annotations

import json
from pathlib import Path

from versioned_finance_core.orchestration.public_reproductions import reproduce_m2_evidence

CASE_DIR = Path(__file__).parents[1]


def reproduce() -> dict[str, object]:
    """Return the source-linked evidence assessment without writing an artifact."""

    return reproduce_m2_evidence(CASE_DIR)


if __name__ == "__main__":
    print(json.dumps(reproduce(), ensure_ascii=False, indent=2, sort_keys=True))
