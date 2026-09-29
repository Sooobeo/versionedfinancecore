import json
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from versioned_finance_core.contracts import (
    FinancialVersion,
    KnowledgeState,
    MappingRule,
    MetricDefinition,
    RawFact,
    ScopeBridge,
    ScopeRef,
    SourceProvenance,
    decimal_value,
)
from versioned_finance_core.financial_core import (
    CashIdentitySpec,
    evaluate_cash_identity,
    normalize_actuals,
    project_cash_scenario,
)
from versioned_finance_core.financial_core.scenarios import ScenarioDriverOverride
from versioned_finance_core.reporting import (
    cash_identity_memo_field,
    scenario_cash_memo_field,
)

FIXTURE = (
    Path(__file__).parents[1] / "fixtures" / "synthetic_known_answers" / "normalization_cash.json"
)


def _records() -> tuple[dict, list[RawFact], list[MappingRule],
                        list[MetricDefinition], FinancialVersion, CashIdentitySpec]:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    facts = []
    mappings = []
    metrics = []
    roles = data["cash_identity"]
    for role in (
        "opening_cash", "operating_cash_flow", "investing_cash_flow",
        "financing_cash_flow", "fx_and_other", "closing_cash",
    ):
        instant = role in {"opening_cash", "closing_cash"}
        period_start = "2024-12-31" if role == "opening_cash" else (
            "2025-12-31" if role == "closing_cash" else "2025-01-01"
        )
        period_end = "2024-12-31" if role == "opening_cash" else "2025-12-31"
        row = {
            "fact_id": f"raw_{role}",
            "source_id": data["source_id"],
            "snapshot_id": data["snapshot_id"],
            "content_sha256": data["content_sha256"],
            "first_public_at": data["first_public_at"],
            "retrieved_at": data["retrieved_at"],
            "version_id": data["version_id"],
            "economic_scope_id": data["economic_scope_id"],
            "accounting_scope": data["accounting_scope"],
            "economic_legal_scope_bridge_id": "",
            "legal_entity_id": "",
            "instrument_id": "",
            "segment_id": "",
            "raw_account_id": role,
            "period_start": period_start,
            "period_end": period_end,
            "period_type": "INSTANT" if instant else "YEAR",
            "currency": data["currency"],
            "unit": data["unit"],
            "raw_value": roles[role],
            "mapping_version": f"map_{role}",
            "claim_tag": "F",
        }
        facts.append(RawFact.from_mapping(row))
        mappings.append(MappingRule.from_mapping({
            "mapping_id": f"map_{role}",
            "source_id": data["source_id"],
            "raw_account_id": role,
            "normalized_metric_id": role,
            "effective_from": "",
            "effective_to": "",
            "sign_multiplier": "1",
            "review_status": "APPROVED",
        }))
        metrics.append(MetricDefinition.from_mapping({
            "metric_id": role,
            "grain": "ECONOMIC_SCOPE",
            "period_type": "INSTANT" if instant else "YEAR",
            "currency_policy": "USD",
            "unit": "USD",
            "sign_convention": "SIGNED_CASH",
            "review_status": "APPROVED",
        }))
    version = FinancialVersion.from_mapping({
        "version_id": data["version_id"],
        "version_type": "PUBLIC_ACTUAL",
        "as_of_date": "2025-12-31",
        "publication_status": "FILED",
        "supersedes_version_id": "",
        "information_cutoff": data["information_cutoff"],
        "immutable": "true",
    })
    spec = CashIdentitySpec.from_mapping({
        "identity_id": roles["identity_id"],
        "version_id": data["version_id"],
        **{f"{role}_fact_id": f"raw_{role}" for role in (
            "opening_cash", "operating_cash_flow", "investing_cash_flow",
            "financing_cash_flow", "fx_and_other", "closing_cash",
        )},
    })
    return data, facts, mappings, metrics, version, spec


def _normalize(data, facts, mappings, metrics, version):
    return normalize_actuals(
        data["case_id"], facts, mappings, metrics, [version],
        datetime.fromisoformat(data["information_cutoff"]),
    )


def test_synthetic_known_answer_cash_lineage_and_identity() -> None:
    data, facts, mappings, metrics, version, spec = _records()
    normalized = _normalize(data, facts, mappings, metrics, version)
    assert len(normalized) == 6
    assert all(fact.provenance.snapshot_id == data["snapshot_id"] for fact in normalized)
    result = evaluate_cash_identity(spec, normalized)
    assert result.residual == Decimal(data["cash_identity"]["expected_residual"])
    assert result.calculated_closing_cash == Decimal(130)
    assert result.knowledge_state is KnowledgeState.KNOWN
    assert len(result.normalized_fact_ids) == 6
    assert evaluate_cash_identity(spec, normalized).output_id == result.output_id


def test_cutoff_excludes_later_fact_and_restated_version() -> None:
    data, facts, mappings, metrics, version, _ = _records()
    before = datetime.fromisoformat("2026-02-14T23:59:59+00:00")
    assert normalize_actuals(data["case_id"], facts, mappings, metrics, [version], before) == ()
    revised = replace(
        facts[0],
        fact_id="raw_opening_cash_restated",
        version_id="actual_restated_v2",
        value=Decimal(105),
        provenance=SourceProvenance(
            source_id=data["source_id"],
            snapshot_id="synthetic_receipt_2",
            content_sha256="b" * 64,
            first_public_at=datetime.fromisoformat("2026-04-01T09:00:00+00:00"),
            retrieved_at=datetime.fromisoformat("2026-04-02T09:00:00+00:00"),
        ),
    )
    restated_version = FinancialVersion.from_mapping({
        "version_id": "actual_restated_v2",
        "version_type": "PUBLIC_ACTUAL",
        "as_of_date": "2025-12-31",
        "publication_status": "RESTATED",
        "supersedes_version_id": data["version_id"],
        "information_cutoff": "2026-04-02T00:00:00+00:00",
        "immutable": "true",
    })
    cutoff = datetime.fromisoformat(data["information_cutoff"])
    eligible = normalize_actuals(
        data["case_id"], [facts[0], revised], mappings, metrics,
        [version, restated_version], cutoff,
    )
    assert len(eligible) == 1
    assert eligible[0].version_id == data["version_id"]
    assert eligible[0].value == Decimal(100)


def test_duplicate_normalized_grain_and_unit_mismatch_fail() -> None:
    data, facts, mappings, metrics, version, _ = _records()
    with pytest.raises(ValueError, match="Duplicate raw fact_id"):
        _normalize(data, [*facts, facts[0]], mappings, metrics, version)
    wrong_metric = MetricDefinition.from_mapping({
        "metric_id": "opening_cash", "grain": "ECONOMIC_SCOPE",
        "period_type": "INSTANT", "currency_policy": "USD", "unit": "THOUSAND_USD",
        "sign_convention": "SIGNED_CASH", "review_status": "APPROVED",
    })
    with pytest.raises(ValueError, match="Unit mismatch"):
        _normalize(data, [facts[0]], mappings, [wrong_metric], version)


def test_missing_value_is_not_zero_and_float_is_rejected() -> None:
    data, facts, mappings, metrics, version, spec = _records()
    unknown = RawFact.from_mapping({
        "fact_id": "raw_opening_cash",
        "source_id": data["source_id"],
        "snapshot_id": data["snapshot_id"],
        "content_sha256": data["content_sha256"],
        "first_public_at": data["first_public_at"],
        "retrieved_at": data["retrieved_at"],
        "version_id": data["version_id"],
        "economic_scope_id": data["economic_scope_id"],
        "accounting_scope": data["accounting_scope"],
        "raw_account_id": "opening_cash",
        "period_start": "2024-12-31",
        "period_end": "2024-12-31",
        "period_type": "INSTANT",
        "currency": "USD", "unit": "USD",
        "raw_value": "UNKNOWN",
        "mapping_version": "map_opening_cash", "claim_tag": "F",
    })
    normalized = _normalize(data, [unknown, *facts[1:]], mappings, metrics, version)
    result = evaluate_cash_identity(spec, normalized)
    assert result.knowledge_state is KnowledgeState.UNKNOWN
    assert result.residual is None
    with pytest.raises(TypeError):
        decimal_value(1.2)


def test_synthetic_scenario_and_memo_keep_canonical_output_ids() -> None:
    data, facts, mappings, metrics, version, spec = _records()
    normalized = _normalize(data, facts, mappings, metrics, version)
    scenario_data = data["scenario"]
    override = ScenarioDriverOverride.from_mapping({
        "scenario_id": scenario_data["scenario_id"],
        "scenario_purpose": "EVIDENCE_DOWNSIDE",
        "version_id": scenario_data["scenario_version_id"],
        "driver_id": "operating_cash_flow",
        "period_start": "2025-01-01",
        "period_end": "2025-12-31",
        "input_value": scenario_data["operating_cash_flow_override"],
        "input_unit": "USD",
        "evidence_or_assumption_id": scenario_data["assumption_id"],
        "mechanism": "ABSOLUTE_OVERRIDE",
        "review_status": "APPROVED",
    })
    identity = evaluate_cash_identity(spec, normalized)
    scenario = project_cash_scenario(spec, normalized, [override])
    assert scenario.projected_closing_cash == Decimal(scenario_data["expected_closing_cash"])
    assert scenario.baseline_output_id == identity.output_id
    assert cash_identity_memo_field(identity).output_id == identity.output_id
    memo = scenario_cash_memo_field(scenario)
    assert memo.output_id == scenario.output_id
    assert memo.value == scenario_data["expected_closing_cash"]
    assert _normalize(data, facts, mappings, metrics, version) == normalized


def test_scope_bridge_requires_matching_public_approved_relation() -> None:
    data, facts, mappings, metrics, version, _ = _records()
    scoped = replace(facts[0], scope=ScopeRef(
        economic_scope_id=data["economic_scope_id"],
        accounting_scope=facts[0].scope.accounting_scope,
        economic_legal_scope_bridge_id="bridge_1",
        legal_entity_id="issuer_1",
        instrument_id=None,
        segment_id=None,
    ))
    bridge = ScopeBridge.from_mapping({
        "bridge_id": "bridge_1",
        "economic_scope_id": data["economic_scope_id"],
        "legal_entity_id": "issuer_1",
        "relation": "ISSUER_OF_GROUP",
        "source_id": data["source_id"],
        "snapshot_id": data["snapshot_id"],
        "content_sha256": data["content_sha256"],
        "first_public_at": data["first_public_at"],
        "retrieved_at": data["retrieved_at"],
        "review_status": "APPROVED",
    })
    cutoff = datetime.fromisoformat(data["information_cutoff"])
    with pytest.raises(ValueError, match="Unknown scope bridge"):
        normalize_actuals(data["case_id"], [scoped], mappings, metrics, [version], cutoff)
    result = normalize_actuals(
        data["case_id"], [scoped], mappings, metrics, [version], cutoff, [bridge]
    )
    assert result[0].scope.legal_entity_id == "issuer_1"
    with pytest.raises(ValueError, match="Scope bridge mismatch"):
        normalize_actuals(data["case_id"], [scoped], mappings, metrics, [version], cutoff,
                          [replace(bridge, legal_entity_id="other_issuer")])
    future_provenance = replace(
        bridge.provenance,
        first_public_at=datetime.fromisoformat("2026-04-01T09:00:00+00:00"),
        retrieved_at=datetime.fromisoformat("2026-04-02T09:00:00+00:00"),
    )
    with pytest.raises(ValueError, match="Scope bridge was not public"):
        normalize_actuals(data["case_id"], [scoped], mappings, metrics, [version], cutoff,
                          [replace(bridge, provenance=future_provenance)])
