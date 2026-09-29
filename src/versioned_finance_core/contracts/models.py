from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from versioned_finance_core.contracts.enums import ModuleId, Perspective

SCHEMA_VERSION = 2
CASE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


@dataclass(frozen=True)
class CaseContract:
    """Minimal case contract shared by M1, M2 and M3."""

    schema_version: int
    program_id: str
    case_id: str
    status: str
    decision_question: str | None
    perspective_id: Perspective | None
    as_of_date: date | None
    analysis_cutoff: datetime | None
    horizon_end: date | None
    economic_scope_id: str | None
    legal_entity_id: str | None
    instrument_id: str | None
    jurisdiction: str | None
    functional_currency: str | None
    reporting_currency: str | None
    active_modules: tuple[ModuleId, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> CaseContract:
        missing = [key for key in ("program_id", "case_id", "status") if not value.get(key)]
        if missing:
            raise ValueError(f"Missing required case fields: {', '.join(missing)}")
        if value.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"case.json schema_version must be {SCHEMA_VERSION}")
        if not CASE_ID_PATTERN.fullmatch(str(value["case_id"])):
            raise ValueError("case_id must use lowercase letters, digits, underscores or hyphens")

        perspective_value = value.get("perspective_id")
        perspective = Perspective(perspective_value) if perspective_value else None
        modules = tuple(ModuleId(item) for item in value.get("active_modules", []))

        result = cls(
            schema_version=SCHEMA_VERSION,
            program_id=str(value["program_id"]),
            case_id=str(value["case_id"]),
            status=str(value["status"]),
            decision_question=_optional_text(value.get("decision_question")),
            perspective_id=perspective,
            as_of_date=_optional_date(value.get("as_of_date")),
            analysis_cutoff=_optional_datetime(value.get("analysis_cutoff")),
            horizon_end=_optional_date(value.get("horizon_end")),
            economic_scope_id=_optional_text(value.get("economic_scope_id")),
            legal_entity_id=_optional_text(value.get("legal_entity_id")),
            instrument_id=_optional_text(value.get("instrument_id")),
            jurisdiction=_optional_text(value.get("jurisdiction")),
            functional_currency=_optional_text(value.get("functional_currency")),
            reporting_currency=_optional_text(value.get("reporting_currency")),
            active_modules=modules,
        )
        if result.as_of_date and result.horizon_end and result.horizon_end < result.as_of_date:
            raise ValueError("horizon_end must not precede as_of_date")
        return result

    def release_readiness_issues(self) -> list[str]:
        checks = {
            "decision_question": self.decision_question,
            "perspective_id": self.perspective_id,
            "as_of_date": self.as_of_date,
            "analysis_cutoff": self.analysis_cutoff,
            "horizon_end": self.horizon_end,
            "economic_scope_id": self.economic_scope_id,
            "jurisdiction": self.jurisdiction,
            "functional_currency": self.functional_currency,
            "reporting_currency": self.reporting_currency,
            "active_modules": self.active_modules,
        }
        issues = [
            f"case.json field is not set: {name}" for name, value in checks.items() if not value
        ]
        if ModuleId.M3 in self.active_modules and not self.legal_entity_id:
            issues.append("case.json field is not set: legal_entity_id")
        if self.perspective_id is Perspective.INSTRUMENT_RECOVERY and not self.instrument_id:
            issues.append("case.json field is not set: instrument_id")
        return issues


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_date(value: Any) -> date | None:
    if not value:
        return None
    return date.fromisoformat(str(value))


def _optional_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        raise ValueError("analysis_cutoff must include a UTC offset or Z")
    return parsed

