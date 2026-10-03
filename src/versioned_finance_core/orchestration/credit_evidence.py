"""Map public credit evidence to M3 limitation states, without inventing cash paths."""

from __future__ import annotations

import csv
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path

from versioned_finance_core.contracts import KnowledgeState
from versioned_finance_core.contracts.json_io import strict_json_loads
from versioned_finance_core.evidence import load_source_ledger
from versioned_finance_core.modules.m3.credit import (
    CovenantDirection,
    CovenantTestability,
    ObligorCashPosition,
    assess_covenant,
    evaluate_obligor_cash,
)
from versioned_finance_core.modules.m3.public_disclosures import (
    PublicCreditFact,
    audit_nominal_capacity,
    audit_public_credit_disclosures,
)

PUBLIC_TERM_COLUMNS = (
    "term_id", "instrument_id", "legal_entity_id", "term_type", "value", "currency", "unit",
    "as_of_date", "source_id", "snapshot_id", "content_sha256", "first_public_at",
    "retrieved_at", "verified_at", "source_location", "claim_tag", "limitation",
)
NUMERIC_TERM_TYPES = {
    "CAPACITY_EXPIRY_WITHIN_TWELVE_MONTHS", "CAPACITY_EXCEEDS_ELIGIBLE_RECEIVABLES",
    "ISSUER_REPORTED_AVAILABLE",
}
TEXT_TERM_TYPES = {"DRAW_CONDITION", "SUPPORT_AGREEMENT", "GUARANTEE", "RECOURSE"}


def _amount(value: str) -> Decimal | KnowledgeState:
    if not value:
        return KnowledgeState.UNKNOWN
    try:
        return KnowledgeState(value)
    except ValueError:
        try:
            result = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("Credit amount must be Decimal or explicit knowledge state") from exc
        if not result.is_finite():
            raise ValueError("Credit amount must be finite")
        return result


def _rows(path: Path, required: tuple[str, ...] = ()) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f"Invalid CSV header: {path}")
        if missing := set(required) - set(reader.fieldnames):
            raise ValueError(f"Missing credit CSV columns in {path}: {sorted(missing)}")
        try:
            rows = list(reader)
        except csv.Error as exc:
            raise ValueError(f"Malformed credit CSV: {path}") from exc
    if any(None in row or None in row.values() for row in rows):
        raise ValueError(f"Invalid CSV row width: {path}")
    return rows


def review_credit_evidence(case_dir: Path, core_build: Path) -> dict[str, object]:
    """Preserve group cash as a reference; assess incomplete covenants using M3.

    This adapter supports the publicly incomplete evidence state. It refuses
    numeric covenant recalculation until a contract-specific component adapter
    exists. It never subtracts aggregate annual maturities from group liquidity.
    """
    charter = strict_json_loads((case_dir / "00_charter/case.json").read_text(encoding="utf-8"))
    core = strict_json_loads((core_build / "core_outputs.json").read_text(encoding="utf-8"))
    cutoff = datetime.fromisoformat(charter["analysis_cutoff"])
    if core["case_id"] != charter["case_id"] or datetime.fromisoformat(core["analysis_cutoff"]) != cutoff:
        raise ValueError("Credit evidence requires this case's Core and cutoff")
    spec = _rows(case_dir / "02_financial_core/cash_identity_checks.csv")
    if len(spec) != 1:
        raise ValueError("Credit evidence requires one pinned cash identity")
    normalized = _rows(core_build / "normalized_actuals.csv")
    matches = [row for row in normalized
               if row["source_fact_id"] == spec[0]["closing_cash_fact_id"]]
    if len(matches) != 1:
        raise ValueError("Credit evidence requires one normalized closing cash fact")
    closing = matches[0]
    if (closing["case_id"] != charter["case_id"]
            or closing["accounting_scope"] != "CONSOLIDATED"
            or closing["economic_scope_id"] != charter["economic_scope_id"]
            or closing["fact_id"] not in core["cash_identity"]["normalized_fact_ids"]):
        raise ValueError("Credit group cash scope or Core lineage mismatch")
    cash = evaluate_obligor_cash(ObligorCashPosition(
        legal_entity_id=charter["legal_entity_id"],
        group_cash=Decimal(closing["value"]),
        obligor_cash=KnowledgeState.UNKNOWN, unavailable_cash=KnowledgeState.UNKNOWN,
        group_source_id=closing["fact_id"],
    ))
    receipts = load_source_ledger(case_dir / "01_evidence_core")
    eligible_sources = {
        source.source_id for source in receipts
        if source.metadata.cutoff_eligible and source.first_public_at is not None
        and source.first_public_at <= cutoff and source.metadata.transformation_right
    }
    module_dir = case_dir / "05_m3_credit_liquidity_claims"
    def sourced_rows(filename: str, key: str, required: tuple[str, ...]):
        rows = _rows(module_dir / filename, (key, "source_id", *required))
        ids = [row[key] for row in rows]
        if len(set(ids)) != len(ids) or any(not item for item in ids):
            raise ValueError(f"Credit IDs must be nonempty and unique: {filename}")
        if any(row["source_id"] not in eligible_sources for row in rows):
            raise ValueError(f"Credit source unavailable at cutoff: {filename}")
        return rows

    entities = sourced_rows("entities_obligors.csv", "entity_id", ("legal_name", "entity_type"))
    entity_ids = {row["entity_id"] for row in entities}
    facilities = sourced_rows("debt_facilities.csv", "instrument_id", (
        "obligor_entity_id", "instrument_type", "currency", "commitment", "drawn",
        "nominal_undrawn", "closing_face", "carrying_amount", "drawability_state",
    ))
    for row in facilities:
        if row["obligor_entity_id"] and row["obligor_entity_id"] not in entity_ids:
            raise ValueError("Credit facility references unknown legal entity")
        if any(row[key] for key in ("closing_face", "carrying_amount", "commitment", "drawn",
                                    "nominal_undrawn")) and row.get("unit") not in {
            row["currency"], row["currency"] + "_MILLION", row["currency"] + "_BILLION",
        }:
            raise ValueError("Credit facility amount requires explicit currency-compatible unit")
        row["nominal_capacity_audit"] = audit_nominal_capacity(
            commitment=_amount(row["commitment"]), drawn=_amount(row["drawn"]),
            disclosed_undrawn=_amount(row["nominal_undrawn"]),
        )
        for field in ("closing_face", "carrying_amount", "commitment", "drawn", "nominal_undrawn"):
            amount = _amount(row[field])
            if isinstance(amount, Decimal) and amount < 0:
                raise ValueError("Credit debt/facility amounts cannot be negative")
            row[field] = str(amount)
        row["drawable_amount"] = "UNKNOWN"
    terms = []
    terms_path = module_dir / "public_terms.csv"
    if terms_path.exists():
        terms = sourced_rows("public_terms.csv", "term_id", PUBLIC_TERM_COLUMNS)
        by_snapshot = {receipt.snapshot_id: receipt for receipt in receipts}
        instruments = {row["instrument_id"]: row for row in facilities}
        for row in terms:
            receipt = by_snapshot.get(row["snapshot_id"])
            if (receipt is None or receipt.source_id != row["source_id"]
                    or receipt.content_sha256 != row["content_sha256"]
                    or datetime.fromisoformat(row["first_public_at"]) != receipt.first_public_at
                    or datetime.fromisoformat(row["retrieved_at"]) != receipt.metadata.retrieved_at):
                raise ValueError("Public credit term provenance mismatch")
            if (not receipt.metadata.cutoff_eligible or not receipt.metadata.transformation_right
                    or receipt.first_public_at is None or receipt.first_public_at > cutoff):
                raise ValueError("Public credit term receipt is not eligible at cutoff")
            if (row["instrument_id"] not in instruments or row["legal_entity_id"] not in entity_ids
                    or row["claim_tag"] != "F" or not row["value"]
                    or not row["source_location"] or not row["limitation"]):
                raise ValueError("Public credit term scope or claim mismatch")
            expected_entity = (instruments[row["instrument_id"]]["obligor_entity_id"]
                               or charter["economic_scope_id"])
            if row["legal_entity_id"] != expected_entity:
                raise ValueError("Public credit term entity does not match instrument scope")
            if date.fromisoformat(row["as_of_date"]) > cutoff.date():
                raise ValueError("Public credit term balance after cutoff")
            if row["term_type"] in NUMERIC_TERM_TYPES:
                value = _amount(row["value"])
                if (not isinstance(value, Decimal) or value < 0 or row["unit"] not in {
                    row["currency"], row["currency"] + "_MILLION", row["currency"] + "_BILLION",
                } or row["currency"] == "NOT_APPLICABLE"):
                    raise ValueError("Public credit numeric term needs amount/currency/unit")
            elif row["term_type"] == "FACILITY_MATURITY_YEAR":
                if (not row["value"].isdigit() or len(row["value"]) != 4
                        or row["unit"] != "YEAR" or row["currency"] != "NOT_APPLICABLE"):
                    raise ValueError("Public credit maturity term requires a year bucket")
            elif row["term_type"] in TEXT_TERM_TYPES:
                if row["unit"] != "TEXT" or row["currency"] != "NOT_APPLICABLE":
                    raise ValueError("Public credit text term requires TEXT/NOT_APPLICABLE")
            else:
                raise ValueError("Unknown public credit term type")
            verified = datetime.fromisoformat(row["verified_at"])
            if verified.utcoffset() is None or verified < receipt.metadata.retrieved_at:
                raise ValueError("Public credit term verification timestamp is invalid")
    facts = []
    for row in normalized:
        if (row["case_id"] != charter["case_id"]
                or row["economic_scope_id"] != charter["economic_scope_id"]
                or row["source_id"] not in eligible_sources
                or datetime.fromisoformat(row["first_public_at"]) > cutoff):
            raise ValueError("Normalized credit fact scope or cutoff mismatch")
        facts.append(PublicCreditFact(
            fact_id=row["fact_id"], metric_id=row["metric_id"], value=_amount(row["value"]),
            currency=row["currency"], unit=row["unit"],
            scope_key=tuple(row[key] for key in (
                "case_id", "economic_scope_id", "legal_entity_id", "accounting_scope",
                "version_id", "segment_id",
            )), period_start=date.fromisoformat(row["period_start"]),
            period_end=date.fromisoformat(row["period_end"]), period_type=row["period_type"],
        ))
    audits = audit_public_credit_disclosures(facts, balance_date=date.fromisoformat(
        closing["period_end"]))
    maturity_buckets = [{key: row[key] for key in (
        "fact_id", "metric_id", "instrument_id", "period_start", "period_end", "value",
        "currency", "unit", "source_id", "snapshot_id",
    )} | {"payment_date": "UNKNOWN", "meaning": "DISCLOSED_BUCKET_NOT_PAYMENT_EVENT"}
        for row in normalized if row["period_type"] == "MATURITY_BUCKET"]
    covenant_rows = _rows(case_dir / "05_m3_credit_liquidity_claims/covenants.csv", (
        "covenant_id", "instrument_id", "test_date", "testability_state",
        "direction", "source_id", "threshold",
    ))
    identifiers = [row["covenant_id"] for row in covenant_rows]
    if len(identifiers) != len(set(identifiers)) or any(not item for item in identifiers):
        raise ValueError("Covenant IDs must be nonempty and unique")
    covenants = []
    for row in covenant_rows:
        if row["instrument_id"] not in {facility["instrument_id"] for facility in facilities}:
            raise ValueError("Covenant references unknown instrument")
        if row["source_id"] not in eligible_sources:
            raise ValueError(f"Covenant source unavailable at cutoff: {row['covenant_id']}")
        if row["test_date"] and date.fromisoformat(row["test_date"]) > cutoff.date():
            raise ValueError("Credit evidence adapter does not infer future covenant tests")
        testability = CovenantTestability(row["testability_state"])
        if testability is CovenantTestability.PUBLIC_RECALCULATION:
            raise ValueError("Public covenant recalculation needs a contract-specific component adapter")
        result = assess_covenant(
            testability=testability, actual=KnowledgeState.UNKNOWN,
            threshold=KnowledgeState.UNKNOWN, direction=CovenantDirection(row["direction"]),
            definition_source_id=row["source_id"],
        )
        covenants.append({
            "covenant_id": row["covenant_id"], "instrument_id": row["instrument_id"],
            "test_date": row["test_date"], "testability": result.testability.value,
            "headroom": str(result.headroom),
            "mathematical_threshold_crossed": str(result.mathematical_threshold_crossed),
            "definition_source_id": result.definition_source_id,
            "disclosed_threshold_label": row["threshold"],
        })
    payload = {
        "schema_version": 1, "case_id": charter["case_id"],
        "analysis_cutoff": charter["analysis_cutoff"],
        "core_output_id": core["cash_identity"]["output_id"],
        "legal_entity_id": cash.legal_entity_id,
        "group_cash_reference": {
            "value": str(cash.group_cash_reference), "currency": closing["currency"],
            "unit": closing["unit"], "balance_date": closing["period_end"],
            "accounting_scope": closing["accounting_scope"],
            "normalized_fact_id": closing["fact_id"],
            "meaning": "Reported cash identity balance; may include restricted cash.",
        },
        "obligor_cash": str(cash.obligor_cash),
        "unavailable_cash": str(cash.unavailable_cash),
        "accessible_cash": str(cash.accessible_cash),
        "covenants": covenants,
        "entities": entities,
        "debt_and_facilities": facilities,
        "disclosure_audits": audits,
        "disclosed_maturity_buckets": maturity_buckets,
        "public_terms": terms,
        "recovery_state": "STRUCTURE_ONLY",
        "recovery_value": "NOT_TESTABLE_FROM_PUBLIC_DATA",
        "market_signal": "NO_PUBLIC_MARKET_SIGNAL_IN_REGISTERED_EVIDENCE",
        "evidence_gaps": [
            {"requirement": "OBLIGOR_CASH_ACCESS", "state": "UNKNOWN",
             "needed": "Parent-only cash accounts and legally transferable subsidiary cash."},
            {"requirement": "DATED_CASH_PATH", "state": "NOT_TESTABLE_FROM_PUBLIC_DATA",
             "needed": "Collections, originations, contractual payment dates and cash floor."},
            {"requirement": "COMMITTED_DRAWABILITY", "state": "UNKNOWN",
             "needed": "Borrower-level eligible assets, hedges, draw conditions and exact expiry."},
            {"requirement": "COVENANT_RECALCULATION", "state": "NOT_TESTABLE_FROM_PUBLIC_DATA",
             "needed": "Exact contract definitions, testing components, cure and waiver terms."},
            {"requirement": "RECOVERY", "state": "STRUCTURE_ONLY",
             "needed": "Entity value pools, allowed claims, lien rank and enforcement evidence."},
        ],
        "refinancing_gap": "NOT_TESTABLE_FROM_PUBLIC_DATA",
        "first_failure_date": None,
        "release_status": "WITHHELD",
        "limitations": [
            "Group cash is not legally accessible obligor cash.",
            "No dated CFADS, debt-service or committed-funding path is inferred from annual buckets.",
            "Covenant headroom needs complete definitions and sourced components.",
            "Reported liquidity and nominal undrawn capacity are not verified drawable cash.",
        ] + ([("Supplementary terms retain source-vintage limitations and do not establish "
               "verified drawability or historical byte identity.")] if terms else [])
          + [f"Disclosure audit {audit['audit_id']}: {audit['state']}" for audit in audits
             if audit["state"] != "PASS"]
          + [f"Nominal capacity audit {row['instrument_id']}: FAIL" for row in facilities
             if row["nominal_capacity_audit"]["state"] == "FAIL"],
    }
    digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"output_id": f"m3_evidence_{digest}", **payload}
