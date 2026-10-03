"""Case-configured conditional consolidated forecast and valuation adapter.

The adapter owns orchestration only: a case configuration selects pinned facts
and declared assumptions, while ``financial_core`` and M1 retain all financial
and valuation arithmetic.  It is deliberately review-only and rejects a
configuration that attempts to promote the calculation to a publication.
"""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import fields
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from versioned_finance_core.contracts import (
    AccountingScope,
    KnowledgeState,
    ScenarioPurpose,
    VersionType,
)
from versioned_finance_core.contracts.json_io import strict_json_loads
from versioned_finance_core.financial_core import (
    ConsolidatedDriverInputs,
    ConsolidatedForecastSpec,
    aggregate_disclosed_opening_balance,
    audit_consolidated_cash_components,
    comparable_remaining_period_base,
    derive_consolidated_period,
    project_consolidated_free_cash_flow_path,
    project_consolidated_path,
    projected_fiscal_revenue_basis,
    reported_other_revenue,
    unlevered_cash_taxes_from_ebit,
)
from versioned_finance_core.financial_core.model_path import ModelInputEvidence
from versioned_finance_core.modules.m1.cost_of_capital import (
    BetaBasis,
    DebtValueBasis,
    SourcedValuationParameter,
    WaccInputs,
    calculate_wacc,
)
from versioned_finance_core.modules.m1.valuation import (
    CashFlowClaim,
    DatedClaimBalance,
    DiscountRateClaim,
    DiscountTiming,
    LeasePolicyEvidence,
    LeaseValuationTreatment,
    RateBasis,
    aggregate_dated_claim_balances,
    bridge_enterprise_to_equity_partial,
    dcf_inputs_from_core_cash_flows,
    terminal_operating_economics_from_forecast,
    value_perpetuity_dcf,
)
from versioned_finance_core.modules.m1.valuation_controls import (
    DatedStubEvidence,
    HistoricalLeaseCashTaxEvidence,
    HistoricalLeaseCashTaxModelPolicy,
    assess_dated_dcf_stub_boundary,
    diagnose_historical_lease_and_cash_tax,
)

NORMALIZED_ACTUALS_COLUMNS = frozenset(
    {
        "fact_id",
        "source_fact_id",
        "source_id",
        "snapshot_id",
        "content_sha256",
        "first_public_at",
        "retrieved_at",
        "case_id",
        "economic_scope_id",
        "accounting_scope",
        "economic_legal_scope_bridge_id",
        "legal_entity_id",
        "instrument_id",
        "segment_id",
        "metric_id",
        "period_start",
        "period_end",
        "period_type",
        "currency",
        "unit",
        "value",
        "version_id",
        "publication_status",
        "normalization_rule",
        "mapping_version",
        "claim_tag",
        "review_status",
    }
)
SOURCE_LEDGER_COLUMNS = frozenset(
    {
        "source_id",
        "first_public_at",
        "retrieved_at",
        "entity_scope",
        "transformation_right",
        "content_sha256",
        "cutoff_eligible",
        "snapshot_id",
    }
)
ASSUMPTION_EVIDENCE_COLUMNS = frozenset(
    {
        "evidence_id",
        "source_id",
        "first_public_at",
        "retrieved_at",
        "entity_scope",
        "period",
        "unit",
        "observed_value",
        "temporal_state",
        "rights_state",
    }
)

HISTORICAL_LEASE_CASH_TAX_VALUE_FIELDS = (
    "total_depreciation_and_amortization",
    "finance_lease_rou_amortization",
    "operating_lease_cost",
    "finance_lease_interest",
    "finance_lease_income_statement_interest",
    "operating_lease_cash_paid",
    "finance_lease_operating_cash_paid",
    "finance_lease_financing_cash_paid",
    "income_tax_provision",
    "cash_taxes_paid",
    "pretax_income",
)


def _read_csv(
    path: Path,
    *,
    required_columns: frozenset[str] = frozenset(),
    label: str,
) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, strict=True)
            header = reader.fieldnames
            if not header or None in header or len(header) != len(set(header)):
                raise ValueError(f"invalid CSV header for {label}: {path}")
            missing = required_columns - set(header)
            if missing:
                raise ValueError(
                    f"missing required CSV columns for {label}: {sorted(missing)}"
                )
            rows = [dict(row) for row in reader]
    except csv.Error as exc:
        raise ValueError(f"malformed CSV for {label}: {path}") from exc
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError(f"CSV row width does not match header for {label}: {path}")
    return rows


def _read_json_mapping(path: Path, label: str) -> dict[str, object]:
    try:
        value = strict_json_loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"malformed JSON for {label}: {path}") from exc
    return _mapping(value, label)


def _moment(value: str, label: str) -> datetime:
    try:
        moment = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid ISO timestamp for {label}: {value}") from exc
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(f"timestamp must include timezone for {label}: {value}")
    return moment


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record(obj: object) -> dict[str, str]:
    return {field.name: str(getattr(obj, field.name)) for field in fields(obj)}


def _mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"conditional adapter metadata must contain object: {label}")
    return value


def _sequence(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise TypeError(f"conditional adapter metadata must contain list: {label}")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"conditional adapter metadata must contain non-empty text: {label}")
    return value


def _texts(value: object, label: str) -> tuple[str, ...]:
    return tuple(_text(item, label) for item in _sequence(value, label))


def _bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"conditional adapter metadata must contain bool: {label}")
    return value


def _adapter_metadata(config: dict[str, object]) -> dict[str, object]:
    metadata = _mapping(config.get("adapter_metadata"), "adapter_metadata")
    schema_version = metadata.get("schema_version")
    if type(schema_version) is not int or schema_version != 2:
        raise ValueError(
            "conditional adapter requires metadata schema version 2; "
            "version 1 is a provenance snapshot only"
        )
    return metadata


def _revision_metadata(config: dict[str, object]) -> dict[str, str] | None:
    """Validate optional, explicit provenance when a scenario replaces its inputs."""

    value = config.get("revision")
    if value is None:
        return None
    revision = _mapping(value, "configuration revision")
    required = {
        "revision_id": _text(revision.get("revision_id"), "revision ID"),
        "revises_version_id": _text(
            revision.get("revises_version_id"), "revised version ID"
        ),
        "prior_config_sha256": _text(
            revision.get("prior_config_sha256"), "prior config SHA-256"
        ),
        "reason": _text(revision.get("reason"), "revision reason"),
    }
    if required["revises_version_id"] == _text(config.get("version_id"), "version ID"):
        raise ValueError("revised version ID must differ from current version ID")
    if len(required["prior_config_sha256"]) != 64 or any(
        character not in "0123456789abcdef" for character in required["prior_config_sha256"]
    ):
        raise ValueError("prior config SHA-256 must be lowercase hexadecimal")
    return required


def _locator_available_at(
    locator_rows: dict[str, dict[str, str]],
    evidence_ids: tuple[str, ...],
    *,
    cutoff: datetime,
    label: str,
) -> datetime:
    """Require dated, eligible locator receipts for a positive M1 assertion."""

    moments: list[datetime] = []
    for evidence_id in evidence_ids:
        row = locator_rows.get(evidence_id)
        if row is None:
            raise ValueError(f"missing assumption locator for {label}: {evidence_id}")
        first_public_at = row.get("first_public_at", "")
        if not first_public_at:
            raise ValueError(f"missing first_public_at for {label}: {evidence_id}")
        available_at = _moment(first_public_at, f"{label} first_public_at {evidence_id}")
        if available_at > cutoff:
            raise ValueError(f"{label} locator is after analysis cutoff: {evidence_id}")
        moments.append(available_at)
    if not moments:
        raise ValueError(f"{label} requires at least one assumption locator")
    return max(moments)


def _historical_locator_values(
    control: dict[str, object],
    locator_rows: dict[str, dict[str, str]],
    *,
    ledger_rows: list[dict[str, str]],
    expected_economic_scope: str,
    cutoff: datetime,
) -> tuple[dict[str, str], tuple[str, ...], datetime]:
    """Fail closed if a historical diagnostic value differs from its locator."""

    period_start = _text(control.get("period_start"), "historical diagnostic start")
    period_end = _text(control.get("period_end"), "historical diagnostic end")
    expected_period = f"{period_start}/{period_end}"
    expected_unit = _text(control.get("unit"), "historical diagnostic unit")
    receipt = _mapping(control.get("source_receipt"), "historical source receipt")
    expected_source_id = _text(receipt.get("source_id"), "historical source receipt ID")
    expected_locator_entity_scope = _text(
        receipt.get("locator_entity_scope"), "historical locator entity scope"
    )
    receipt_fields = {
        "snapshot_id": _text(receipt.get("snapshot_id"), "historical source snapshot ID"),
        "content_sha256": _text(
            receipt.get("content_sha256"), "historical source content SHA-256"
        ),
        "first_public_at": _text(
            receipt.get("first_public_at"), "historical source first_public_at"
        ),
        "retrieved_at": _text(receipt.get("retrieved_at"), "historical source retrieved_at"),
    }
    receipt_matches = [
        row
        for row in ledger_rows
        if row["source_id"] == expected_source_id
        and all(row[field] == expected for field, expected in receipt_fields.items())
    ]
    if len(receipt_matches) != 1:
        raise ValueError("historical source receipt mismatch")
    ledger_row = receipt_matches[0]
    if ledger_row["entity_scope"] != expected_economic_scope:
        raise ValueError("historical lease/cash-tax source scope mismatch")
    if ledger_row["cutoff_eligible"] != "YES":
        raise ValueError("historical lease/cash-tax source is not cutoff eligible")
    if ledger_row["transformation_right"] != "YES":
        raise ValueError("historical lease/cash-tax source lacks transformation right")
    if _moment(receipt_fields["first_public_at"], "historical source receipt first_public_at") > cutoff:
        raise ValueError("historical lease/cash-tax source is after analysis cutoff")
    receipt_public_at = _moment(
        receipt_fields["first_public_at"], "historical source receipt first_public_at"
    )
    receipt_retrieved_at = _moment(
        receipt_fields["retrieved_at"], "historical source receipt retrieved_at"
    )
    evidence_by_field = _mapping(
        control.get("evidence_by_field"), "historical lease/cash-tax evidence mapping"
    )
    if set(evidence_by_field) != set(HISTORICAL_LEASE_CASH_TAX_VALUE_FIELDS):
        raise ValueError("historical lease/cash-tax evidence mapping must cover exactly its values")
    evidence_ids: list[str] = []
    values: dict[str, str] = {}
    for field in HISTORICAL_LEASE_CASH_TAX_VALUE_FIELDS:
        evidence_id = _text(evidence_by_field.get(field), f"historical evidence ID {field}")
        row = locator_rows.get(evidence_id)
        if row is None:
            raise ValueError(f"missing assumption locator for historical {field}: {evidence_id}")
        if row["source_id"] != expected_source_id:
            raise ValueError(f"historical control source does not match locator: {field}")
        if row["entity_scope"] != expected_locator_entity_scope:
            raise ValueError(f"historical control scope does not match locator: {field}")
        if _moment(row["first_public_at"], f"historical locator first_public_at {field}") != receipt_public_at:
            raise ValueError(f"historical control publication time does not match locator: {field}")
        if _moment(row["retrieved_at"], f"historical locator retrieved_at {field}") != receipt_retrieved_at:
            raise ValueError(f"historical control retrieval time does not match locator: {field}")
        value = _text(control.get(field), f"historical value {field}")
        if row.get("observed_value") != value:
            raise ValueError(f"historical control value does not match locator: {field}")
        if row.get("unit") != expected_unit:
            raise ValueError(f"historical control unit does not match locator: {field}")
        if row.get("period") != expected_period:
            raise ValueError(f"historical control period does not match locator: {field}")
        values[field] = value
        evidence_ids.append(evidence_id)
    return values, tuple(evidence_ids), _locator_available_at(
        locator_rows,
        tuple(evidence_ids),
        cutoff=cutoff,
        label="historical lease/cash-tax diagnostic",
    )


def _source_version(
    source_versions: dict[str, object], source_key: str
) -> dict[str, object]:
    return _mapping(source_versions.get(source_key), f"source_versions.{source_key}")


def _validate_normalized_actuals(
    rows: list[dict[str, str]],
    *,
    charter: dict[str, object],
    contract: dict[str, object],
    cutoff: datetime,
) -> None:
    """Reject Core rows that cannot belong to this consolidated case contract."""

    if not rows:
        raise ValueError("normalized actuals must contain at least one fact")
    expected_case_id = _text(charter.get("case_id"), "case ID")
    expected_economic_scope = _text(
        charter.get("economic_scope_id"), "charter economic scope"
    )
    expected_legal_entity = _text(charter.get("legal_entity_id"), "charter legal entity")
    expected_accounting_scope = _text(contract.get("accounting_scope"), "accounting scope")
    expected_currency = _text(contract.get("currency"), "fact currency")
    expected_unit = _text(contract.get("unit"), "fact unit")
    for line_number, row in enumerate(rows, start=2):
        if row["case_id"] != expected_case_id:
            raise ValueError(
                f"normalized fact case_id mismatch at line {line_number}: "
                f"{row['case_id']} != {expected_case_id}"
            )
        if row["economic_scope_id"] != expected_economic_scope:
            raise ValueError(f"normalized fact economic scope mismatch at line {line_number}")
        if row["legal_entity_id"] != expected_legal_entity:
            raise ValueError(f"normalized fact legal entity mismatch at line {line_number}")
        if row["accounting_scope"] != expected_accounting_scope:
            raise ValueError(f"normalized fact accounting scope mismatch at line {line_number}")
        if row["currency"] != expected_currency or row["unit"] != expected_unit:
            raise ValueError(f"normalized fact currency or unit mismatch at line {line_number}")
        first_public_at = _moment(
            row["first_public_at"], f"normalized fact first_public_at at line {line_number}"
        )
        _moment(row["retrieved_at"], f"normalized fact retrieved_at at line {line_number}")
        if first_public_at > cutoff:
            raise ValueError(f"normalized fact is after analysis cutoff at line {line_number}")


def _validate_source_versions(
    source_versions: dict[str, object],
    ledger_rows: list[dict[str, str]],
    *,
    expected_economic_scope: str,
    cutoff: datetime,
) -> None:
    """Confirm pinned source versions are case-scoped and available at cutoff."""

    for source_key, version_obj in source_versions.items():
        version = _mapping(version_obj, f"source_versions.{source_key}")
        source_id = _text(version.get("source_id"), f"source ID for {source_key}")
        matching_rows = [row for row in ledger_rows if row["source_id"] == source_id]
        if not matching_rows:
            raise ValueError(f"configured source is absent from case source ledger: {source_id}")
        for row in matching_rows:
            if row["entity_scope"] != expected_economic_scope:
                raise ValueError(
                    f"case source scope mismatch for {source_id}: "
                    f"{row['entity_scope']} != {expected_economic_scope}"
                )
            if row["cutoff_eligible"] != "YES":
                raise ValueError(f"configured source is not cutoff eligible: {source_id}")
            if _moment(row["first_public_at"], f"source ledger first_public_at for {source_id}") > cutoff:
                raise ValueError(f"configured source is after analysis cutoff: {source_id}")


def _fact(
    rows: list[dict[str, str]],
    *,
    metric: str,
    end: str,
    version: dict[str, object],
    contract: dict[str, object],
    start: str | None = None,
) -> dict[str, str]:
    version_id = _text(version.get("version_id"), "source version ID")
    expected_source = _text(version.get("source_id"), "source ID")
    matches = [
        row
        for row in rows
        if row["metric_id"] == metric
        and row["period_end"] == end
        and row["version_id"] == version_id
        and (start is None or row["period_start"] == start)
    ]
    if len(matches) != 1:
        raise ValueError(
            f"expected one pinned fact for {metric}/{end}/{version_id}, found {len(matches)}"
        )
    row = matches[0]
    if row["currency"] != _text(contract.get("currency"), "fact currency"):
        raise ValueError(f"currency mismatch: {metric}")
    if row["unit"] != _text(contract.get("unit"), "fact unit"):
        raise ValueError(f"unit mismatch: {metric}")
    if row["accounting_scope"] != _text(contract.get("accounting_scope"), "accounting scope"):
        raise ValueError(f"scope mismatch: {metric}")
    if row["economic_scope_id"] != _text(contract.get("economic_scope_id"), "economic scope"):
        raise ValueError(f"economic scope mismatch: {metric}")
    if row["source_id"] != expected_source:
        raise ValueError(f"source/version mismatch: {metric}")
    if not row["first_public_at"]:
        raise ValueError(f"missing first_public_at: {metric}")
    return row


def _selected_fact(
    rows: list[dict[str, str]],
    selector: dict[str, object],
    *,
    source_versions: dict[str, object],
    contract: dict[str, object],
) -> dict[str, str]:
    source_key = _text(selector.get("source_version_key"), "selector source version key")
    return _fact(
        rows,
        metric=_text(selector.get("metric_id"), "selector metric ID"),
        start=selector.get("period_start") if isinstance(selector.get("period_start"), str) else None,
        end=_text(selector.get("period_end"), "selector period end"),
        version=_source_version(source_versions, source_key),
        contract=contract,
    )


def _value(row: dict[str, str]) -> Decimal:
    return Decimal(row["value"])


def _evidence(row: dict[str, str]) -> ModelInputEvidence:
    return ModelInputEvidence(row["fact_id"], datetime.fromisoformat(row["first_public_at"]))


def _parameter(
    value: str,
    *,
    assumption_id: str,
    sources: tuple[str, ...],
    observation_date: str,
    available_at: datetime,
    rationale: str,
) -> SourcedValuationParameter:
    return SourcedValuationParameter(
        Decimal(value),
        assumption_id,
        sources,
        date.fromisoformat(observation_date),
        available_at,
        rationale,
    )


def _period_drivers(
    config: dict[str, object],
    period: dict[str, object],
    *,
    prior_sales: Decimal,
    prior_other: Decimal,
    prior_sales_evidence: ModelInputEvidence,
    prior_other_evidence: ModelInputEvidence,
    ytd_sales: Decimal,
    ytd_other: Decimal,
    ytd_capex: Decimal,
    ytd_evidence: dict[str, ModelInputEvidence],
    cutoff: datetime,
) -> tuple[ConsolidatedDriverInputs, dict[str, ModelInputEvidence]]:
    base = _mapping(config.get("base_drivers"), "base_drivers")
    entries = {name: _mapping(entry, f"base_drivers.{name}") for name, entry in base.items()}
    values = {name: Decimal(_text(entry.get("value"), f"base_drivers.{name}.value")) for name, entry in entries.items()}
    evidence = {
        name: ModelInputEvidence(_text(entry.get("id"), f"base_drivers.{name}.id"), cutoff)
        for name, entry in entries.items()
    }
    values.update(
        {
            "comparable_prior_net_sales": prior_sales,
            "comparable_prior_other_revenue": prior_other,
            "net_sales_growth_rate": Decimal(_text(period.get("net_sales_growth"), "net sales growth")),
            "other_revenue_growth_rate": Decimal(
                _text(period.get("other_revenue_growth"), "other revenue growth")
            ),
            "fiscal_year_net_sales_to_date": ytd_sales,
            "fiscal_year_other_revenue_to_date": ytd_other,
            "fiscal_year_capex_to_date": ytd_capex,
            "capex_rate_of_fiscal_net_sales": Decimal(_text(period.get("capex_rate"), "capex rate")),
            "interest_expense": Decimal(_text(period.get("interest_usd"), "interest")),
            "debt_issuance": Decimal(_text(period.get("debt_issuance_usd"), "debt issuance")),
            "debt_repayment": Decimal(_text(period.get("debt_repayment_usd"), "debt repayment")),
            "dividends_declared": Decimal(
                _text(period.get("dividends_declared_usd"), "dividends declared")
            ),
            "dividends_paid": Decimal(_text(period.get("dividends_paid_usd"), "dividends paid")),
        }
    )
    period_id = _text(period.get("period_id"), "forecast period ID")
    evidence.update(
        {
            "comparable_prior_net_sales": prior_sales_evidence,
            "comparable_prior_other_revenue": prior_other_evidence,
            "net_sales_growth_rate": ModelInputEvidence(
                f"A_{period_id}_NET_SALES_GROWTH", cutoff
            ),
            "other_revenue_growth_rate": ModelInputEvidence(
                f"A_{period_id}_OTHER_REVENUE_GROWTH", cutoff
            ),
            "fiscal_year_net_sales_to_date": ytd_evidence["sales"],
            "fiscal_year_other_revenue_to_date": ytd_evidence["other"],
            "fiscal_year_capex_to_date": ytd_evidence["capex"],
            "capex_rate_of_fiscal_net_sales": ModelInputEvidence(
                f"A_{period_id}_CAPEX_RATE", cutoff
            ),
            "interest_expense": ModelInputEvidence(
                f"A_{period_id}_NET_INTEREST_CASH_PROXY", cutoff
            ),
            "debt_issuance": ModelInputEvidence(f"A_{period_id}_DEBT_ISSUE", cutoff),
            "debt_repayment": ModelInputEvidence(f"A_{period_id}_DEBT_REPAY", cutoff),
            "dividends_declared": ModelInputEvidence(
                f"A_{period_id}_DIVIDENDS_DECLARED", cutoff
            ),
            "dividends_paid": ModelInputEvidence(f"A_{period_id}_DIVIDENDS_PAID", cutoff),
        }
    )
    return ConsolidatedDriverInputs(**values), evidence


def _aggregate_claim(
    *,
    rows: list[dict[str, str]],
    claim: dict[str, object],
    source_versions: dict[str, object],
    contract: dict[str, object],
    charter: dict[str, object],
    cutoff: datetime,
) -> object:
    source = _source_version(
        source_versions, _text(claim.get("source_version_key"), "claim source version key")
    )
    balance_date = _text(claim.get("balance_date"), "claim balance date")
    if balance_date != _text(source.get("period_end"), "claim source period end"):
        raise ValueError("claim balance date must match its selected source-version period end")
    scope = AccountingScope(_text(contract.get("accounting_scope"), "accounting scope"))
    leaves = []
    for metric in _texts(claim.get("metrics"), "claim metrics"):
        row = _fact(
            rows,
            metric=metric,
            end=balance_date,
            version=source,
            contract=contract,
        )
        leaves.append(
            DatedClaimBalance(
                _value(row),
                row["fact_id"],
                date.fromisoformat(balance_date),
                datetime.fromisoformat(row["first_public_at"]),
                scope,
                _text(charter.get("economic_scope_id"), "charter economic scope"),
                _text(charter.get("legal_entity_id"), "charter legal entity"),
                _text(contract.get("currency"), "fact currency"),
                _text(contract.get("unit"), "fact unit"),
            )
        )
    return aggregate_dated_claim_balances(
        tuple(leaves),
        aggregate_name=_text(claim.get("aggregate_name"), "claim aggregate name"),
        information_cutoff=cutoff,
    )


def build_review_artifacts(
    *,
    case_dir: Path,
    normalized_actuals: Path,
    config_path: Path,
) -> dict[str, object]:
    """Build deterministic review artifacts from a case's pinned config and facts.

    This function does not fetch data, write outputs, or promote a publication.
    ``case_dir`` is explicit so source, charter, and evidence paths cannot be
    silently inherited from a company-specific module constant.
    """
    case_dir = Path(case_dir)
    normalized_actuals = Path(normalized_actuals)
    config_path = Path(config_path)
    config = _read_json_mapping(config_path, "configuration")
    adapter = _adapter_metadata(config)
    revision = _revision_metadata(config)
    charter = _read_json_mapping(case_dir / "00_charter" / "case.json", "case charter")
    case_id = _text(charter.get("case_id"), "case ID")
    if case_id != case_dir.name:
        raise ValueError("case charter case_id must match the case directory")
    cutoff = _moment(_text(charter.get("analysis_cutoff"), "analysis cutoff"), "analysis cutoff")
    contract = _mapping(adapter.get("fact_contract"), "fact contract")
    if _text(contract.get("economic_scope_id"), "fact economic scope") != _text(
        charter.get("economic_scope_id"), "charter economic scope"
    ):
        raise ValueError("conditional fact contract and charter economic scope differ")
    rows = _read_csv(
        normalized_actuals,
        required_columns=NORMALIZED_ACTUALS_COLUMNS,
        label="normalized actuals",
    )
    _validate_normalized_actuals(rows, charter=charter, contract=contract, cutoff=cutoff)
    evidence_path = case_dir / _text(
        adapter.get("assumption_evidence_path"), "assumption evidence path"
    )
    locator_entries = _read_csv(
        evidence_path,
        required_columns=ASSUMPTION_EVIDENCE_COLUMNS,
        label="assumption evidence",
    )
    locator_rows = {row["evidence_id"]: row for row in locator_entries}
    if len(locator_rows) != len(locator_entries):
        raise ValueError("assumption evidence contains duplicate evidence_id")
    review_status = _text(adapter.get("review_status"), "review status")
    if (
        type(config.get("schema_version")) is not int
        or config.get("schema_version") != 1
        or config.get("source_availability_review") != "WITHHELD"
        or review_status != "WITHHELD"
    ):
        raise ValueError("conditional configuration must remain review-only")

    source_versions = _mapping(adapter.get("source_versions"), "source versions")
    ledger_path = case_dir / _text(adapter.get("source_ledger_path"), "source ledger path")
    ledger_rows = _read_csv(
        ledger_path,
        required_columns=SOURCE_LEDGER_COLUMNS,
        label="case source ledger",
    )
    _validate_source_versions(
        source_versions,
        ledger_rows,
        expected_economic_scope=_text(
            charter.get("economic_scope_id"), "charter economic scope"
        ),
        cutoff=cutoff,
    )
    opening_meta = _mapping(adapter.get("opening_balance"), "opening balance")
    opening_source = _source_version(
        source_versions,
        _text(opening_meta.get("source_version_key"), "opening source version key"),
    )
    opening_date = _text(config.get("opening_date"), "opening date")
    if _text(opening_source.get("period_end"), "opening source period end") != opening_date:
        raise ValueError("opening source period end must match conditional opening date")

    opening_groups_config = _mapping(config.get("opening_groups"), "opening groups")
    opening_groups = {
        name: _texts(metrics, f"opening_groups.{name}")
        for name, metrics in opening_groups_config.items()
    }
    opening_metrics = set().union(*opening_groups.values()) | {
        _text(opening_meta.get("asset_total_metric_id"), "asset total metric"),
        _text(
            opening_meta.get("liabilities_equity_total_metric_id"),
            "liabilities and equity total metric",
        ),
    }
    opening_facts = {
        metric: _fact(
            rows,
            metric=metric,
            end=opening_date,
            version=opening_source,
            contract=contract,
        )
        for metric in opening_metrics
    }
    opening = aggregate_disclosed_opening_balance(
        {metric: _value(row) for metric, row in opening_facts.items()},
        opening_groups,
        {metric: _evidence(row) for metric, row in opening_facts.items()},
        asset_total_metric_id=_text(opening_meta.get("asset_total_metric_id"), "asset total metric"),
        liabilities_equity_total_metric_id=_text(
            opening_meta.get("liabilities_equity_total_metric_id"),
            "liabilities and equity total metric",
        ),
        information_cutoff=cutoff,
    )

    selectors = _mapping(adapter.get("historical_fact_selectors"), "historical fact selectors")

    def selected(name: str) -> dict[str, str]:
        return _selected_fact(
            rows,
            _mapping(selectors.get(name), f"historical selector {name}"),
            source_versions=source_versions,
            contract=contract,
        )

    full_year_sales = selected("full_year_net_sales")
    full_year_total = selected("full_year_total_revenue")
    prior_quarter_sales = selected("prior_quarter_net_sales")
    prior_quarter_other = selected("prior_quarter_other_revenue")
    current_quarter_sales = selected("current_quarter_net_sales")
    current_quarter_other = selected("current_quarter_other_revenue")
    current_quarter_capex = selected("current_quarter_capex")
    prior_other = reported_other_revenue(_value(full_year_total), _value(full_year_sales))
    prior_sales = comparable_remaining_period_base(
        _value(full_year_sales), _value(prior_quarter_sales)
    )
    prior_other = comparable_remaining_period_base(prior_other, _value(prior_quarter_other))
    if _value(current_quarter_capex) <= 0:
        raise ValueError("normalized partial-period capex must be a positive outflow magnitude")
    historical_source = _source_version(
        source_versions,
        _text(adapter.get("historical_source_version_key"), "historical source version key"),
    )
    original_source_ids = tuple(sorted({row["source_id"] for row in opening_facts.values()}))

    period_configs = [
        _mapping(period, "forecast period") for period in _sequence(config.get("forecast_periods"), "forecast periods")
    ]
    periods = []
    for index, period in enumerate(period_configs):
        if index == 0:
            prior_sales_ev = ModelInputEvidence(
                f"D_{full_year_sales['fact_id']}_{prior_quarter_sales['fact_id']}", cutoff
            )
            prior_other_ev = ModelInputEvidence(
                f"D_{full_year_total['fact_id']}_{full_year_sales['fact_id']}_"
                f"{prior_quarter_other['fact_id']}",
                cutoff,
            )
            ytd_sales = _value(current_quarter_sales)
            ytd_other = _value(current_quarter_other)
            ytd_capex = _value(current_quarter_capex)
            ytd_ev = {
                "sales": _evidence(current_quarter_sales),
                "other": _evidence(current_quarter_other),
                "capex": _evidence(current_quarter_capex),
            }
        else:
            prior_sales, prior_other = projected_fiscal_revenue_basis(periods[-1])
            prior_sales_ev = ModelInputEvidence(
                f"D_{periods[-1].period_id}_FISCAL_SALES", cutoff
            )
            prior_other_ev = ModelInputEvidence(
                f"D_{periods[-1].period_id}_FISCAL_OTHER_REVENUE", cutoff
            )
            ytd_sales = ytd_other = ytd_capex = Decimal(0)
            zero_ev = ModelInputEvidence(
                f"A_{_text(period.get('period_id'), 'forecast period ID')}_FULL_YEAR_NO_PRIOR_YTD",
                cutoff,
            )
            ytd_ev = {"sales": zero_ev, "other": zero_ev, "capex": zero_ev}
        drivers, driver_evidence = _period_drivers(
            config,
            period,
            prior_sales=prior_sales,
            prior_other=prior_other,
            prior_sales_evidence=prior_sales_ev,
            prior_other_evidence=prior_other_ev,
            ytd_sales=ytd_sales,
            ytd_other=ytd_other,
            ytd_capex=ytd_capex,
            ytd_evidence=ytd_ev,
            cutoff=cutoff,
        )
        periods.append(
            derive_consolidated_period(
                period_id=_text(period.get("period_id"), "forecast period ID"),
                period_start=date.fromisoformat(_text(period.get("start"), "forecast start")),
                period_end=date.fromisoformat(_text(period.get("end"), "forecast end")),
                drivers=drivers,
                driver_evidence=driver_evidence,
            )
        )

    accounting_scope = AccountingScope(_text(contract.get("accounting_scope"), "accounting scope"))
    spec = ConsolidatedForecastSpec(
        case_id=_text(charter.get("case_id"), "case ID"),
        version_id=_text(config.get("version_id"), "version ID"),
        version_type=VersionType(_text(adapter.get("version_type"), "forecast version type")),
        scenario_id=_text(config.get("scenario_id"), "scenario ID"),
        scenario_purpose=ScenarioPurpose(
            _text(adapter.get("scenario_purpose"), "scenario purpose")
        ),
        accounting_scope=accounting_scope,
        economic_scope_id=_text(charter.get("economic_scope_id"), "charter economic scope"),
        legal_entity_id=_text(charter.get("legal_entity_id"), "charter legal entity"),
        currency=_text(contract.get("currency"), "fact currency"),
        unit=_text(contract.get("unit"), "fact unit"),
        opening_balance_date=date.fromisoformat(opening_date),
        opening=opening.opening,
        opening_evidence=opening.opening_evidence,
        information_cutoff=cutoff,
        periods=tuple(periods),
    )
    path = project_consolidated_path(spec)
    cash_tax_meta = _mapping(adapter.get("unlevered_cash_tax"), "unlevered cash tax metadata")
    unlevered_taxes = unlevered_cash_taxes_from_ebit(
        path,
        tax_rate=Decimal(_text(config.get("unlevered_cash_tax_rate"), "unlevered cash tax")),
        evidence=ModelInputEvidence(
            _text(cash_tax_meta.get("assumption_id"), "cash tax assumption ID"), cutoff
        ),
        method_id=_text(cash_tax_meta.get("method_id"), "cash tax method ID"),
    )
    cash_flows = project_consolidated_free_cash_flow_path(
        path, unlevered_cash_taxes=unlevered_taxes
    )
    audits = audit_consolidated_cash_components(path, cash_flows)

    claims_meta = _mapping(adapter.get("claim_aggregates"), "claim aggregates")
    debt_claim = _aggregate_claim(
        rows=rows,
        claim=_mapping(claims_meta.get("debt"), "debt claim"),
        source_versions=source_versions,
        contract=contract,
        charter=charter,
        cutoff=cutoff,
    )
    minority_claim = _aggregate_claim(
        rows=rows,
        claim=_mapping(claims_meta.get("minority"), "minority claim"),
        source_versions=source_versions,
        contract=contract,
        charter=charter,
        cutoff=cutoff,
    )

    wacc_meta = _mapping(adapter.get("wacc"), "WACC metadata")
    debt_value_field = _text(wacc_meta.get("debt_value_field"), "WACC debt value field")
    wacc_screen = _mapping(config.get("wacc_screen"), "WACC screen")
    if debt_claim.amount != Decimal(_text(wacc_screen.get(debt_value_field), debt_value_field)):
        raise ValueError("WACC debt proxy does not match pinned debt and finance leases")

    lease_meta = _mapping(adapter.get("lease_policy"), "lease policy")
    lease_evidence_ids = _texts(lease_meta.get("evidence_ids"), "lease evidence IDs")
    lease_source_ids = tuple(
        _text(_source_version(source_versions, key).get("source_id"), "lease source ID")
        for key in _texts(lease_meta.get("source_version_keys"), "lease source version keys")
    ) + lease_evidence_ids
    lease_policy = LeasePolicyEvidence(
        LeaseValuationTreatment(_text(lease_meta.get("treatment"), "lease treatment")),
        _text(lease_meta.get("assumption_id"), "lease assumption ID"),
        lease_source_ids,
        _locator_available_at(
            locator_rows, lease_evidence_ids, cutoff=cutoff, label="lease policy"
        ),
        _bool(lease_meta.get("lease_cost_in_fcff"), "lease_cost_in_fcff"),
        _bool(
            lease_meta.get("lease_liability_in_debt_like_claims"),
            "lease_liability_in_debt_like_claims",
        ),
        _bool(lease_meta.get("lease_financing_in_wacc"), "lease_financing_in_wacc"),
    )
    parameter_meta = _mapping(wacc_meta.get("parameters"), "WACC parameters")
    allowed_reference_ids = (
        set(locator_rows)
        | {
            _text(_mapping(version, "source version").get("source_id"), "source ID")
            for version in source_versions.values()
        }
        | {debt_claim.source_id}
    )

    def wp(field: str) -> SourcedValuationParameter:
        metadata = _mapping(parameter_meta.get(field), f"WACC parameter {field}")
        if field == debt_value_field:
            source_ids = (debt_claim.source_id,)
        else:
            source_ids = _texts(metadata.get("source_ids"), f"WACC sources for {field}")
        missing = set(source_ids) - allowed_reference_ids
        if missing:
            raise ValueError(f"missing assumption locators: {sorted(missing)}")
        available_at = (
            _moment(
                _text(metadata.get("available_at"), f"WACC available_at {field}"),
                f"WACC available_at {field}",
            )
            if "available_at" in metadata
            else cutoff
        )
        if available_at > cutoff:
            raise ValueError(f"WACC parameter is after analysis cutoff: {field}")
        return _parameter(
            _text(wacc_screen.get(field), f"WACC value {field}"),
            assumption_id=_text(metadata.get("assumption_id"), f"WACC assumption ID {field}"),
            sources=source_ids,
            observation_date=_text(
                metadata.get("observation_date"), f"WACC observation date {field}"
            ),
            available_at=available_at,
            rationale=_text(metadata.get("rationale"), f"WACC rationale {field}"),
        )

    debt_input = _mapping(wacc_meta.get("marginal_debt_input"), "WACC marginal debt input")
    debt_input_kind = _text(debt_input.get("kind"), "WACC marginal debt input kind")
    debt_input_field = _text(debt_input.get("field"), "WACC marginal debt input field")
    if debt_input_field == debt_value_field:
        raise ValueError("WACC marginal debt input cannot be the debt value field")
    if debt_input_kind == "PRE_TAX_DEBT_RATE":
        debt_rate_kwargs = {"marginal_pre_tax_debt_rate": wp(debt_input_field)}
    elif debt_input_kind == "DEBT_SPREAD":
        debt_rate_kwargs = {"marginal_debt_spread": wp(debt_input_field)}
    else:
        raise ValueError("unsupported WACC marginal debt input kind")

    wacc = calculate_wacc(
        WaccInputs(
            case_id=_text(charter.get("case_id"), "case ID"),
            assumption_id=_text(wacc_meta.get("assumption_id"), "WACC assumption ID"),
            valuation_date=date.fromisoformat(_text(charter.get("as_of_date"), "valuation date")),
            information_cutoff=cutoff,
            accounting_scope=accounting_scope,
            economic_scope_id=_text(charter.get("economic_scope_id"), "charter economic scope"),
            currency=_text(contract.get("currency"), "fact currency"),
            rate_basis=RateBasis(_text(wacc_meta.get("rate_basis"), "WACC rate basis")),
            risk_free_rate=wp("risk_free_rate"),
            levered_beta=wp("beta"),
            equity_risk_premium=wp("erp"),
            marginal_tax_rate=wp("marginal_tax_rate"),
            share_price=wp("share_price_usd"),
            shares_outstanding=wp("shares_outstanding"),
            debt_value=wp(debt_value_field),
            beta_basis=BetaBasis(_text(wacc_meta.get("beta_basis"), "beta basis")),
            debt_value_basis=DebtValueBasis(
                _text(wacc_meta.get("debt_value_basis"), "debt value basis")
            ),
            lease_policy=lease_policy,
            **debt_rate_kwargs,
        )
    )

    terminal_config = _mapping(config.get("terminal"), "terminal configuration")
    terminal_meta = _mapping(adapter.get("terminal"), "terminal metadata")
    terminal = terminal_operating_economics_from_forecast(
        cash_flows,
        sustainable_ebit_growth=Decimal(
            _text(terminal_config.get("ebit_growth"), "terminal EBIT growth")
        ),
        terminal_growth_rate=Decimal(_text(terminal_config.get("growth"), "terminal growth")),
        unlevered_cash_tax_rate=Decimal(
            _text(terminal_config.get("cash_tax_rate"), "terminal cash tax rate")
        ),
        sustainable_roic=Decimal(
            _text(terminal_config.get("sustainable_roic"), "terminal ROIC")
        ),
        assumption_id=_text(terminal_meta.get("assumption_id"), "terminal assumption ID"),
        ebit_growth_assumption_id=_text(
            terminal_meta.get("ebit_growth_assumption_id"), "terminal EBIT growth assumption ID"
        ),
        cash_tax_rate_assumption_id=_text(
            terminal_meta.get("cash_tax_rate_assumption_id"),
            "terminal cash tax assumption ID",
        ),
        roic_assumption_id=_text(
            terminal_meta.get("roic_assumption_id"), "terminal ROIC assumption ID"
        ),
        growth_assumption_id=_text(
            terminal_meta.get("growth_assumption_id"), "terminal growth assumption ID"
        ),
        basis_source_ids=_texts(terminal_meta.get("basis_source_ids"), "terminal basis sources"),
        available_at=cutoff,
        rationale=_text(terminal_config.get("rationale"), "terminal rationale"),
    )
    dcf_meta = _mapping(adapter.get("dcf"), "DCF metadata")
    dcf = value_perpetuity_dcf(
        dcf_inputs_from_core_cash_flows(
            cash_flows,
            case_id=_text(charter.get("case_id"), "case ID"),
            forecast_version_id=_text(config.get("version_id"), "version ID"),
            accounting_scope=accounting_scope,
            economic_scope_id=_text(charter.get("economic_scope_id"), "charter economic scope"),
            legal_entity_id=_text(charter.get("legal_entity_id"), "charter legal entity"),
            currency=_text(contract.get("currency"), "fact currency"),
            unit=_text(contract.get("unit"), "fact unit"),
            cash_flow_claim=CashFlowClaim(_text(dcf_meta.get("cash_flow_claim"), "cash flow claim")),
            discount_rate_claim=DiscountRateClaim(
                _text(dcf_meta.get("discount_rate_claim"), "discount rate claim")
            ),
            rate_basis=RateBasis(_text(dcf_meta.get("rate_basis"), "DCF rate basis")),
            annual_discount_rate=wacc.wacc,
            discount_rate_assumption_id=wacc.output_id,
            discount_rate_available_at=cutoff,
            terminal_next_cash_flow=terminal.next_year_fcff,
            terminal_growth_rate=terminal.growth_rate,
            terminal_state_assumption_id=terminal.assumption_id,
            terminal_state_available_at=cutoff,
            discount_timing=DiscountTiming(
                _text(dcf_meta.get("discount_timing"), "discount timing")
            ),
            discount_rate_basis_source_ids=(wacc.output_id,),
            terminal_state_basis_source_ids=terminal.basis_source_ids,
            valuation_date=date.fromisoformat(
                _text(charter.get("as_of_date"), "valuation date")
            ),
            discount_rate_rationale=_text(
                dcf_meta.get("discount_rate_rationale"), "discount rate rationale"
            ),
            terminal_cash_flow_rationale=_text(
                terminal_config.get("rationale"), "terminal rationale"
            ),
            terminal_economics=terminal,
        )
    )
    controls = _mapping(adapter.get("valuation_controls"), "valuation controls")
    historical_control = _mapping(
        controls.get("historical_lease_cash_tax"), "historical lease/cash-tax control"
    )
    historical_values, historical_evidence_ids, historical_available_at = _historical_locator_values(
        historical_control,
        locator_rows,
        ledger_rows=ledger_rows,
        expected_economic_scope=_text(
            charter.get("economic_scope_id"), "charter economic scope"
        ),
        cutoff=cutoff,
    )
    historical_diagnostic = diagnose_historical_lease_and_cash_tax(
        HistoricalLeaseCashTaxEvidence(
            period_start=date.fromisoformat(
                _text(historical_control.get("period_start"), "historical diagnostic start")
            ),
            period_end=date.fromisoformat(
                _text(historical_control.get("period_end"), "historical diagnostic end")
            ),
            available_at=historical_available_at,
            source_ids=historical_evidence_ids,
            unit=_text(historical_control.get("unit"), "historical diagnostic unit"),
            total_depreciation_and_amortization=Decimal(
                historical_values["total_depreciation_and_amortization"]
            ),
            finance_lease_rou_amortization=Decimal(
                historical_values["finance_lease_rou_amortization"]
            ),
            operating_lease_cost=Decimal(
                historical_values["operating_lease_cost"]
            ),
            finance_lease_interest=Decimal(
                historical_values["finance_lease_interest"]
            ),
            finance_lease_income_statement_interest=Decimal(
                historical_values["finance_lease_income_statement_interest"]
            ),
            operating_lease_cash_paid=Decimal(
                historical_values["operating_lease_cash_paid"]
            ),
            finance_lease_operating_cash_paid=Decimal(
                historical_values["finance_lease_operating_cash_paid"]
            ),
            finance_lease_financing_cash_paid=Decimal(
                historical_values["finance_lease_financing_cash_paid"]
            ),
            income_tax_provision=Decimal(
                historical_values["income_tax_provision"]
            ),
            cash_taxes_paid=Decimal(
                historical_values["cash_taxes_paid"]
            ),
            pretax_income=Decimal(
                historical_values["pretax_income"]
            ),
        ),
        HistoricalLeaseCashTaxModelPolicy(
            total_da_booked_to_ppe_depreciation=_bool(
                _mapping(historical_control.get("model_policy"), "historical model policy").get(
                    "total_da_booked_to_ppe_depreciation"
                ),
                "historical total_da_booked_to_ppe_depreciation",
            ),
            cash_tax_rate_equals_tax_expense_rate=_bool(
                _mapping(historical_control.get("model_policy"), "historical model policy").get(
                    "cash_tax_rate_equals_tax_expense_rate"
                ),
                "historical cash_tax_rate_equals_tax_expense_rate",
            ),
        ),
    )
    stub_control = _mapping(controls.get("dated_stub"), "dated DCF stub control")
    stub_source_ids = _texts(stub_control.get("source_ids"), "dated DCF stub source IDs")
    has_stub_amount = "realized_prevaluation_cash_flow" in stub_control
    has_stub_state = "realized_prevaluation_cash_flow_state" in stub_control
    if has_stub_amount == has_stub_state:
        raise ValueError("dated DCF stub must contain exactly one cash-flow amount or state")
    if has_stub_amount:
        realized_stub_cash_flow: Decimal | KnowledgeState = Decimal(
            _text(
                stub_control.get("realized_prevaluation_cash_flow"),
                "dated DCF realized stub cash flow",
            )
        )
        realized_stub_start = date.fromisoformat(
            _text(
                stub_control.get("realized_prevaluation_period_start"),
                "dated DCF realized stub start",
            )
        )
        realized_stub_end = date.fromisoformat(
            _text(
                stub_control.get("realized_prevaluation_period_end"),
                "dated DCF realized stub end",
            )
        )
    else:
        realized_stub_cash_flow = KnowledgeState(
            _text(
                stub_control.get("realized_prevaluation_cash_flow_state"),
                "dated DCF realized stub state",
            )
        )
        realized_stub_start = realized_stub_end = None
    first_core_period = path.periods[0]
    dated_stub_boundary = assess_dated_dcf_stub_boundary(
        dcf,
        first_core_period_id=first_core_period.period_id,
        first_core_period_start=first_core_period.period_start,
        first_core_period_end=first_core_period.period_end,
        evidence=DatedStubEvidence(
            evidence_id=_text(stub_control.get("evidence_id"), "dated DCF stub evidence ID"),
            source_ids=stub_source_ids,
            available_at=_locator_available_at(
                locator_rows,
                stub_source_ids,
                cutoff=cutoff,
                label="dated DCF stub",
            ),
            last_disclosed_period_end=date.fromisoformat(
                _text(
                    stub_control.get("last_disclosed_period_end"),
                    "dated DCF last disclosed period end",
                )
            ),
            realized_prevaluation_cash_flow=realized_stub_cash_flow,
            realized_prevaluation_period_start=realized_stub_start,
            realized_prevaluation_period_end=realized_stub_end,
        ),
    )
    bridge = bridge_enterprise_to_equity_partial(
        dcf,
        excess_cash=KnowledgeState.UNKNOWN,
        nonoperating_assets=KnowledgeState.UNKNOWN,
        debt_like_claims=debt_claim,
        minority_interest=minority_claim,
        other_senior_claims=KnowledgeState.UNKNOWN,
        lease_policy=lease_policy,
    )

    forecast_periods = []
    for forecast, flow, audit in zip(path.periods, cash_flows.periods, audits, strict=True):
        period_index = len(forecast_periods)
        forecast_periods.append(
            {
                "period_id": forecast.period_id,
                "period_start": forecast.period_start.isoformat(),
                "period_end": forecast.period_end.isoformat(),
                "drivers": _record(spec.periods[period_index].driver_inputs),
                "driver_evidence": {
                    name: item.source_or_assumption_id
                    for name, item in spec.periods[period_index].driver_evidence.items()
                },
                "income_statement": _record(forecast.result.income),
                "balance_sheet": _record(forecast.result.closing),
                "total_assets": str(forecast.result.closing.assets),
                "total_liabilities_and_equity": str(
                    forecast.result.closing.liabilities_and_equity
                ),
                "cash_flow_statement": _record(forecast.result.cash_flow),
                "fcff": str(flow.fcff),
                "fcfe": str(flow.fcfe),
                "fcff_output_id": flow.fcff_output_id,
                "fcfe_output_id": flow.fcfe_output_id,
                "cash_component_audit_id": audit.output_id,
                "identity_residuals": {
                    "balance": str(forecast.result.balance_residual),
                    "cash": str(forecast.result.cash_residual),
                    "debt": str(forecast.result.debt_residual),
                    "tax": str(forecast.result.tax_residual),
                    "ppe": str(forecast.result.ppe_residual),
                    "dividends_payable": str(forecast.result.dividend_payable_residual),
                },
            }
        )

    artifact_meta = _mapping(adapter.get("artifacts"), "artifact metadata")
    source_ids = tuple(dict.fromkeys((*original_source_ids, _text(historical_source.get("source_id"), "historical source ID"))))
    common = {
        "schema_version": 1,
        "case_id": _text(charter.get("case_id"), "case ID"),
        "forecast_version_id": _text(config.get("version_id"), "version ID"),
        "scenario_id": _text(config.get("scenario_id"), "scenario ID"),
        "model_origin": _text(config.get("model_origin"), "model origin"),
        "revision": revision,
        "information_cutoff": _text(charter.get("analysis_cutoff"), "analysis cutoff"),
        "source_availability_review": config["source_availability_review"],
        "assumption_available_at_semantics": _text(
            artifact_meta.get("assumption_available_at_semantics"),
            "assumption availability semantics",
        ),
        "normalized_actuals_sha256": _digest(normalized_actuals),
        "config_sha256": _digest(config_path),
        "source_ids": list(source_ids),
        "limitations": config["limitations"],
    }
    amount_suffix = _text(artifact_meta.get("amount_suffix"), "artifact amount suffix")
    market_input_ids = _texts(
        artifact_meta.get("market_input_evidence_ids"), "market input evidence IDs"
    )
    forecast_artifact = {
        **common,
        "output_id": cash_flows.baseline.output_id,
        "opening_aggregation_id": opening.output_id,
        "opening_balance_sheet": _record(opening.opening),
        "opening_groups": config["opening_groups"],
        "core_path_sha256": path.content_sha256,
        "baseline_output_id": cash_flows.baseline.output_id,
        "cash_flow_path_output_id": cash_flows.output_id,
        "periods": forecast_periods,
        "cash_component_audits": [audit.as_dict() for audit in audits],
        "review_status": review_status,
    }
    valuation_artifact = {
        **common,
        "cash_flow_path_output_id": cash_flows.output_id,
        "wacc": {
            "output_id": wacc.output_id,
            "risk_free_rate": str(wacc.risk_free_rate),
            "cost_of_equity": str(wacc.cost_of_equity),
            "pre_tax_cost_of_debt": str(wacc.pre_tax_cost_of_debt),
            "after_tax_cost_of_debt": str(wacc.after_tax_cost_of_debt),
            f"market_equity_proxy_{amount_suffix}": str(wacc.market_equity_value),
            f"debt_book_proxy_{amount_suffix}": str(wacc.debt_value),
            "equity_weight": str(wacc.equity_weight),
            "debt_weight": str(wacc.debt_weight),
            "conditional_rate": str(wacc.wacc),
            "failed_structural_checks": wacc.failed_structural_checks,
            "eligibility_status": wacc.eligibility_status.value,
            "input_lineage": wacc.input_lineage,
        },
        "market_input_review": {
            evidence_id: {
                "source_id": item["source_id"],
                "observed_value": item["observed_value"],
                "event_at": item["event_at"] or None,
                "first_public_at": item["first_public_at"] or None,
                "temporal_state": item["temporal_state"],
                "rights_state": item["rights_state"],
            }
            for evidence_id, item in sorted(locator_rows.items())
            if evidence_id in market_input_ids
        },
        "terminal": {
            "assumption_id": terminal.assumption_id,
            "final_core_fcff_output_id": terminal.final_core_fcff_output_id,
            "final_core_fcff": str(terminal.final_core_fcff),
            "next_year_ebit": str(terminal.next_year_ebit),
            "next_year_unlevered_nopat": str(terminal.next_year_unlevered_nopat),
            "growth_rate": str(terminal.growth_rate),
            "sustainable_roic": str(terminal.sustainable_roic),
            "reinvestment_rate": str(terminal.reinvestment_rate),
            "next_year_fcff": str(terminal.next_year_fcff),
            "transition_difference": str(terminal.transition_difference),
            "transition_ratio": str(terminal.transition_ratio),
            "rationale": terminal.rationale,
        },
        "dcf_screen": {
            "output_id": dcf.output_id,
            "value_claim": dcf.value_claim,
            "discount_timing": dcf.discount_timing.value,
            "valuation_date": dcf.valuation_date.isoformat(),
            "first_forecast_period_start": dcf.first_forecast_period_start.isoformat(),
            "period_year_fractions": [str(item) for item in dcf.period_year_fractions],
            f"explicit_period_value_{amount_suffix}": str(dcf.explicit_period_value),
            f"terminal_value_at_horizon_{amount_suffix}": str(dcf.terminal_value_at_horizon),
            f"present_terminal_value_{amount_suffix}": str(dcf.present_terminal_value),
            f"conditional_enterprise_value_{amount_suffix}": str(dcf.total_value),
            "conditional_arithmetic_only": True,
            f"release_consumable_enterprise_value_{amount_suffix}": None,
            "eligibility_status": review_status,
        },
        "historical_lease_cash_tax_diagnostic": historical_diagnostic.as_dict(),
        "dated_stub_boundary": dated_stub_boundary.as_dict(),
        "partial_equity_bridge": {
            "output_id": bridge.output_id,
            f"known_subtotal_{amount_suffix}": str(bridge.known_subtotal),
            "unknown_components": bridge.unknown_components,
            "failed_structural_checks": bridge.failed_structural_checks,
            "equity_value": None,
            "known_claims": {
                f"debt_and_finance_leases_{amount_suffix}": str(debt_claim.amount),
                "debt_claim_source_id": debt_claim.source_id,
                "debt_component_source_ids": debt_claim.component_source_ids,
                f"redeemable_and_nonredeemable_nci_{amount_suffix}": str(minority_claim.amount),
                "minority_claim_source_id": minority_claim.source_id,
                "minority_component_source_ids": minority_claim.component_source_ids,
            },
            "eligibility_status": bridge.eligibility_status.value,
        },
        "release_status": review_status,
    }
    output_ids = {
        "baseline": cash_flows.baseline.output_id,
        "dcf": dcf.output_id,
        "dated_stub_boundary": dated_stub_boundary.output_id,
        "bridge": bridge.output_id,
    }
    memo_fields = {
        "schema_version": 1,
        "case_id": _text(charter.get("case_id"), "case ID"),
        "fields": [
            {
                "name": _text(_mapping(template, "memo field").get("name"), "memo field name"),
                "value": _text(_mapping(template, "memo field").get("value"), "memo field value"),
                "output_id": output_ids[
                    _text(_mapping(template, "memo field").get("output_ref"), "memo output ref")
                ],
            }
            for template in _sequence(artifact_meta.get("memo_fields"), "memo fields")
        ],
    }
    return {"forecast": forecast_artifact, "valuation": valuation_artifact, "memo_fields": memo_fields}


def _csv_text(columns: tuple[str, ...], rows: list[dict[str, str]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def review_csvs(artifacts: dict[str, object], *, config_path: Path) -> dict[str, str]:
    """Format case tables from canonical Core/M1 outputs without recalculation."""
    config = _read_json_mapping(Path(config_path), "configuration")
    adapter = _adapter_metadata(config)
    review_meta = _mapping(adapter.get("review_csv"), "review CSV metadata")
    contract = _mapping(adapter.get("fact_contract"), "fact contract")
    source_versions = _mapping(adapter.get("source_versions"), "source versions")
    forecast = _mapping(artifacts.get("forecast"), "forecast artifact")
    valuation = _mapping(artifacts.get("valuation"), "valuation artifact")
    scenario_id = _text(config.get("scenario_id"), "scenario ID")
    version_id = _text(config.get("version_id"), "version ID")
    scope = _text(contract.get("economic_scope_id"), "economic scope")
    currency = _text(contract.get("currency"), "currency")
    unit = _text(contract.get("unit"), "unit")
    review_status = _text(adapter.get("review_status"), "review status")
    forecast_rows: list[dict[str, str]] = []
    for period_obj in _sequence(forecast.get("periods"), "forecast periods"):
        period = _mapping(period_obj, "forecast period")
        income = _mapping(period.get("income_statement"), "forecast income statement")
        cash_flow = _mapping(period.get("cash_flow_statement"), "forecast cash flow")
        metrics = {
            "net_sales": _text(income.get("net_sales"), "net sales"),
            "other_revenue": _text(income.get("other_revenue"), "other revenue"),
            "operating_income": _text(income.get("operating_income"), "operating income"),
            "net_income": _text(income.get("net_income"), "net income"),
            "cash_from_operations": _text(cash_flow.get("operating"), "operating cash flow"),
            "cash_from_investing": _text(cash_flow.get("investing"), "investing cash flow"),
            "cash_from_financing": _text(cash_flow.get("financing"), "financing cash flow"),
            "closing_cash_and_equivalents": _text(cash_flow.get("closing_cash"), "closing cash"),
            "total_assets": _text(period.get("total_assets"), "total assets"),
            "total_liabilities_and_equity": _text(
                period.get("total_liabilities_and_equity"), "total liabilities and equity"
            ),
            "fcff_conditional": _text(period.get("fcff"), "FCFF"),
            "fcfe_conditional": _text(period.get("fcfe"), "FCFE"),
        }
        for metric_id, value in metrics.items():
            forecast_rows.append(
                {
                    "version_id": version_id,
                    "scenario_id": scenario_id,
                    "metric_id": metric_id,
                    "period_start": _text(period.get("period_start"), "period start"),
                    "period_end": _text(period.get("period_end"), "period end"),
                    "economic_scope_id": scope,
                    "segment_id": "",
                    "currency": currency,
                    "unit": unit,
                    "value": value,
                    "driver_or_assumption_id": (
                        _text(period.get("fcff_output_id"), "FCFF output ID")
                        if metric_id == "fcff_conditional"
                        else _text(period.get("fcfe_output_id"), "FCFE output ID")
                        if metric_id == "fcfe_conditional"
                        else _text(forecast.get("core_path_sha256"), "Core path hash")
                    ),
                    "created_at": "",
                    "review_status": review_status,
                }
            )
    forecast_columns = (
        "version_id",
        "scenario_id",
        "metric_id",
        "period_start",
        "period_end",
        "economic_scope_id",
        "segment_id",
        "currency",
        "unit",
        "value",
        "driver_or_assumption_id",
        "created_at",
        "review_status",
    )
    scenario_columns = (
        "scenario_id",
        "scenario_purpose",
        "version_id",
        "driver_id",
        "period_start",
        "period_end",
        "input_value",
        "input_unit",
        "evidence_or_assumption_id",
        "mechanism",
        "dependency_group",
        "review_status",
        "baseline_version_id",
    )
    usd_driver_names = set(_texts(review_meta.get("currency_driver_names"), "currency driver names"))
    baseline_source = _source_version(
        source_versions,
        _text(review_meta.get("baseline_source_version_key"), "baseline source version key"),
    )
    scenario_rows = [
        {
            "scenario_id": scenario_id,
            "scenario_purpose": _text(adapter.get("scenario_purpose"), "scenario purpose"),
            "version_id": version_id,
            "driver_id": name,
            "period_start": _text(period.get("period_start"), "period start"),
            "period_end": _text(period.get("period_end"), "period end"),
            "input_value": value,
            "input_unit": currency
            if name.endswith("_income") or name in usd_driver_names
            else "DECIMAL_RATE",
            "evidence_or_assumption_id": _text(
                _mapping(period.get("driver_evidence"), "driver evidence").get(name),
                f"driver evidence {name}",
            ),
            "mechanism": _text(review_meta.get("driver_mechanism"), "driver mechanism"),
            "dependency_group": _text(
                review_meta.get("driver_dependency_group"), "driver dependency group"
            ),
            "review_status": review_status,
            "baseline_version_id": _text(baseline_source.get("version_id"), "baseline version ID"),
        }
        for period_obj in _sequence(forecast.get("periods"), "forecast periods")
        for period in [_mapping(period_obj, "forecast period")]
        for name, value in sorted(
            _mapping(period.get("drivers"), "forecast drivers").items()
        )
    ]
    valuation_columns = (
        "valuation_run_id",
        "as_of_date",
        "method",
        "eligibility_state",
        "scenario_id",
        "value_basis",
        "discount_rate_basis",
        "terminal_basis",
        "enterprise_value",
        "equity_value",
        "currency",
        "range_low",
        "range_high",
        "thesis_break",
        "limitations",
        "review_status",
    )
    dcf_screen = _mapping(valuation.get("dcf_screen"), "DCF screen")
    wacc = _mapping(valuation.get("wacc"), "WACC artifact")
    terminal = _mapping(valuation.get("terminal"), "terminal artifact")
    valuation_rows = [
        {
            "valuation_run_id": _text(dcf_screen.get("output_id"), "DCF output ID"),
            "as_of_date": _text(dcf_screen.get("valuation_date"), "valuation date"),
            "method": _text(review_meta.get("valuation_method"), "valuation method"),
            "eligibility_state": review_status,
            "scenario_id": scenario_id,
            "value_basis": _text(valuation.get("cash_flow_path_output_id"), "cash flow output ID"),
            "discount_rate_basis": _text(wacc.get("output_id"), "WACC output ID"),
            "terminal_basis": _text(terminal.get("assumption_id"), "terminal assumption ID"),
            "enterprise_value": "",
            "equity_value": "",
            "currency": currency,
            "range_low": "",
            "range_high": "",
            "thesis_break": _text(review_meta.get("thesis_break"), "thesis break"),
            "limitations": _text(review_meta.get("valuation_limitation"), "valuation limitation"),
            "review_status": review_status,
        }
    ]
    assumption_columns = (
        "assumption_id",
        "variable",
        "scenario_id",
        "value",
        "unit",
        "basis",
        "source_id",
        "mechanism",
        "range_low",
        "range_high",
        "dependency",
        "owner",
        "reviewer",
        "expires_at",
        "trigger",
        "claim_tag",
        "status",
    )
    assumption_rows: list[dict[str, str]] = []

    def add_assumption(
        assumption_id: str,
        variable: str,
        value: str,
        unit_value: str,
        sources: tuple[str, ...],
        basis: str,
        dependency: str = "",
    ) -> None:
        assumption_rows.append(
            {
                "assumption_id": assumption_id,
                "variable": variable,
                "scenario_id": scenario_id,
                "value": value,
                "unit": unit_value,
                "basis": basis,
                "source_id": ";".join(sources),
                "mechanism": _text(review_meta.get("assumption_mechanism"), "assumption mechanism"),
                "range_low": "",
                "range_high": "",
                "dependency": dependency,
                "owner": _text(review_meta.get("assumption_owner"), "assumption owner"),
                "reviewer": "",
                "expires_at": "",
                "trigger": _text(review_meta.get("assumption_trigger"), "assumption trigger"),
                "claim_tag": "A",
                "status": review_status,
            }
        )

    base_drivers = _mapping(config.get("base_drivers"), "base drivers")
    for name, entry_obj in sorted(base_drivers.items()):
        entry = _mapping(entry_obj, f"base driver {name}")
        add_assumption(
            _text(entry.get("id"), f"base driver ID {name}"),
            name,
            _text(entry.get("value"), f"base driver value {name}"),
            "DECIMAL_RATE" if "rate" in name or "margin" in name else currency,
            _texts(entry.get("sources"), f"base driver sources {name}"),
            _text(entry.get("note"), f"base driver note {name}"),
        )
    driver_assumptions = _mapping(
        review_meta.get("driver_assumptions"), "driver assumption metadata"
    )
    period_configs = {
        _text(period.get("period_id"), "forecast period ID"): period
        for period in (
            _mapping(item, "forecast period")
            for item in _sequence(config.get("forecast_periods"), "forecast periods")
        )
    }
    for period_obj in _sequence(forecast.get("periods"), "forecast periods"):
        period = _mapping(period_obj, "forecast period")
        period_id = _text(period.get("period_id"), "forecast period ID")
        period_config = period_configs[period_id]
        driver_evidence = _mapping(period.get("driver_evidence"), "driver evidence")
        for driver_name, details_obj in driver_assumptions.items():
            details = _mapping(details_obj, f"driver assumption {driver_name}")
            field_name = _text(details.get("period_field"), f"period field {driver_name}")
            add_assumption(
                _text(driver_evidence.get(driver_name), f"driver evidence {driver_name}"),
                driver_name,
                _text(period_config.get(field_name), field_name),
                _text(details.get("unit"), f"driver unit {driver_name}"),
                _texts(details.get("source_ids"), f"driver sources {driver_name}"),
                _text(details.get("basis"), f"driver basis {driver_name}"),
                period_id,
            )
        if not bool(period_config.get("partial_fiscal_period")):
            full_year_meta = _mapping(
                review_meta.get("full_year_no_prior_ytd"), "full-year YTD assumption metadata"
            )
            add_assumption(
                _text(full_year_meta.get("assumption_id_template"), "full-year YTD assumption ID").format(
                    period_id=period_id
                ),
                _text(full_year_meta.get("variable"), "full-year YTD variable"),
                _text(full_year_meta.get("value"), "full-year YTD value"),
                _text(full_year_meta.get("unit"), "full-year YTD unit"),
                _texts(full_year_meta.get("source_ids"), "full-year YTD sources"),
                _text(full_year_meta.get("basis"), "full-year YTD basis"),
                period_id,
            )
    wacc_meta = _mapping(adapter.get("wacc"), "WACC metadata")
    wacc_parameters = _mapping(wacc_meta.get("parameters"), "WACC parameter metadata")
    wacc_screen = _mapping(config.get("wacc_screen"), "WACC screen")
    debt_value_field = _text(wacc_meta.get("debt_value_field"), "WACC debt value field")
    bridge = _mapping(valuation.get("partial_equity_bridge"), "partial equity bridge")
    known_claims = _mapping(bridge.get("known_claims"), "known claims")
    for name, value_obj in sorted(wacc_screen.items()):
        value = _text(value_obj, f"WACC value {name}")
        metadata = _mapping(wacc_parameters.get(name), f"WACC parameter {name}")
        source_ids = (
            (_text(known_claims.get("debt_claim_source_id"), "debt claim source ID"),)
            if name == debt_value_field
            else _texts(metadata.get("source_ids"), f"WACC sources {name}")
        )
        add_assumption(
            _text(metadata.get("assumption_id"), f"WACC assumption ID {name}"),
            name,
            value,
            _text(metadata.get("unit"), f"WACC unit {name}"),
            source_ids,
            _text(review_meta.get("wacc_assumption_basis"), "WACC assumption basis"),
            _text(wacc.get("output_id"), "WACC output ID"),
        )
    terminal_meta = _mapping(adapter.get("terminal"), "terminal metadata")
    terminal_config = _mapping(config.get("terminal"), "terminal configuration")
    terminal_units = _mapping(terminal_meta.get("units"), "terminal units")
    terminal_ids = {
        "ebit_growth": _text(
            terminal_meta.get("ebit_growth_assumption_id"), "terminal EBIT growth assumption ID"
        ),
        "growth": _text(terminal_meta.get("growth_assumption_id"), "terminal growth assumption ID"),
        "cash_tax_rate": _text(
            terminal_meta.get("cash_tax_rate_assumption_id"), "terminal cash tax assumption ID"
        ),
        "sustainable_roic": _text(
            terminal_meta.get("roic_assumption_id"), "terminal ROIC assumption ID"
        ),
    }
    for name, assumption_id in terminal_ids.items():
        add_assumption(
            assumption_id,
            name,
            _text(terminal_config.get(name), f"terminal value {name}"),
            _text(terminal_units.get(name), f"terminal unit {name}"),
            _texts(terminal_meta.get("basis_source_ids"), "terminal basis sources"),
            _text(terminal_config.get("rationale"), "terminal rationale"),
            _text(terminal.get("assumption_id"), "terminal output ID"),
        )
    cash_tax_meta = _mapping(adapter.get("unlevered_cash_tax"), "unlevered cash tax metadata")
    add_assumption(
        _text(cash_tax_meta.get("assumption_id"), "cash tax assumption ID"),
        "unlevered_cash_tax_rate",
        _text(config.get("unlevered_cash_tax_rate"), "unlevered cash tax rate"),
        _text(cash_tax_meta.get("unit"), "cash tax unit"),
        _texts(cash_tax_meta.get("source_ids"), "cash tax source IDs"),
        _text(cash_tax_meta.get("rationale"), "cash tax rationale"),
        _text(valuation.get("cash_flow_path_output_id"), "cash flow output ID"),
    )
    return {
        "forecast_versions.csv": _csv_text(forecast_columns, forecast_rows),
        "valuation_runs.csv": _csv_text(valuation_columns, valuation_rows),
        "conditional_scenario_drivers.csv": _csv_text(scenario_columns, scenario_rows),
        "assumptions.csv": _csv_text(assumption_columns, assumption_rows),
    }
