import json
from pathlib import Path

import pytest

from versioned_finance_core.contracts import SCHEMA_VERSION, CaseContract

TEMPLATE_CASE = (
    Path(__file__).parents[2] / "cases" / "_template" / "00_charter" / "case.json"
)


def test_template_case_parses_at_current_schema_and_stays_unready() -> None:
    case = CaseContract.from_mapping(json.loads(TEMPLATE_CASE.read_text(encoding="utf-8")))
    assert case.schema_version == SCHEMA_VERSION
    assert "case.json field is not set: economic_scope_id" in case.release_readiness_issues()


def test_case_rejects_stale_schema_and_reverse_horizon() -> None:
    row = json.loads(TEMPLATE_CASE.read_text(encoding="utf-8"))
    row["schema_version"] = SCHEMA_VERSION - 1
    with pytest.raises(ValueError, match="schema_version"):
        CaseContract.from_mapping(row)
    row["schema_version"] = SCHEMA_VERSION
    row["as_of_date"] = "2026-01-01"
    row["horizon_end"] = "2025-12-31"
    with pytest.raises(ValueError, match="horizon_end"):
        CaseContract.from_mapping(row)


def test_credit_perspective_requires_legal_and_instrument_scope() -> None:
    row = json.loads(TEMPLATE_CASE.read_text(encoding="utf-8"))
    row["active_modules"] = ["M3"]
    row["perspective_id"] = "INSTRUMENT_RECOVERY"
    issues = CaseContract.from_mapping(row).release_readiness_issues()
    assert "case.json field is not set: legal_entity_id" in issues
    assert "case.json field is not set: instrument_id" in issues
