"""Point-in-time, scope-preserving historical normalization.

This module is pure: callers load CSV and snapshots, then pass frozen records in.
It never guesses a missing value, FX rate, unit conversion or mapping.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal

from versioned_finance_core.contracts import (
    ClaimTag,
    FinancialVersion,
    MappingRule,
    MetricDefinition,
    NormalizedFact,
    RawFact,
    ScopeBridge,
    VersionType,
)
from versioned_finance_core.contracts.enums import KnowledgeState
from versioned_finance_core.evidence.cutoff import known_at_cutoff


def _unique_by_id(items: Iterable[object], field: str) -> dict[str, object]:
    result: dict[str, object] = {}
    for item in items:
        identifier = getattr(item, field)
        if identifier in result:
            raise ValueError(f"Duplicate {field}: {identifier}")
        result[identifier] = item
    return result


def normalize_actuals(
    case_id: str,
    raw_facts: Iterable[RawFact],
    mappings: Iterable[MappingRule],
    metric_definitions: Iterable[MetricDefinition],
    versions: Iterable[FinancialVersion],
    analysis_cutoff: datetime,
    scope_bridges: Iterable[ScopeBridge] = (),
) -> tuple[NormalizedFact, ...]:
    """Normalize eligible filed facts into immutable version-pinned long records.

    Every input fact must identify one mapping and one actual version. Facts
    disclosed after the requested cutoff remain in storage but are excluded.
    Multiple sources for the same normalized key require explicit adjudication
    upstream, rather than a silent last-write-wins rule.
    """

    if not case_id:
        raise ValueError("case_id is required")
    if analysis_cutoff.tzinfo is None or analysis_cutoff.utcoffset() is None:
        raise ValueError("analysis_cutoff must include a UTC offset")
    mapping_by_id = _unique_by_id(mappings, "mapping_id")
    metric_by_id = _unique_by_id(metric_definitions, "metric_id")
    version_by_id = _unique_by_id(versions, "version_id")
    bridge_by_id = _unique_by_id(scope_bridges, "bridge_id")
    raw_ids: set[str] = set()
    normalized_keys: set[tuple[str, ...]] = set()
    result: list[NormalizedFact] = []

    for fact in raw_facts:
        if fact.fact_id in raw_ids:
            raise ValueError(f"Duplicate raw fact_id: {fact.fact_id}")
        raw_ids.add(fact.fact_id)
        if not known_at_cutoff(fact.provenance.first_public_at, analysis_cutoff):
            continue

        bridge_id = fact.scope.economic_legal_scope_bridge_id
        if bridge_id:
            bridge = bridge_by_id.get(bridge_id)
            if bridge is None or not isinstance(bridge, ScopeBridge):
                raise ValueError(f"Unknown scope bridge: {bridge_id}")
            if (
                bridge.economic_scope_id != fact.scope.economic_scope_id
                or bridge.legal_entity_id != fact.scope.legal_entity_id
            ):
                raise ValueError(f"Scope bridge mismatch for fact: {fact.fact_id}")
            if bridge.review_status != "APPROVED":
                raise ValueError(f"Scope bridge is not approved: {bridge_id}")
            if not known_at_cutoff(bridge.provenance.first_public_at, analysis_cutoff):
                raise ValueError(f"Scope bridge was not public at cutoff: {bridge_id}")

        version = version_by_id.get(fact.version_id)
        if version is None or not isinstance(version, FinancialVersion):
            raise ValueError(f"Unknown version_id: {fact.version_id}")
        if version.version_type is not VersionType.PUBLIC_ACTUAL:
            raise ValueError("historical normalization requires PUBLIC_ACTUAL version")
        if not version.immutable:
            raise ValueError(f"Historical version must be immutable: {version.version_id}")
        if version.information_cutoff > analysis_cutoff:
            raise ValueError(f"Version cutoff exceeds analysis cutoff: {version.version_id}")
        if fact.provenance.first_public_at > version.information_cutoff:
            raise ValueError(f"Fact was not public at version cutoff: {fact.fact_id}")

        mapping = mapping_by_id.get(fact.mapping_version)
        if mapping is None or not isinstance(mapping, MappingRule) or not mapping.applies_to(fact):
            raise ValueError(f"No applicable mapping for fact: {fact.fact_id}")
        if mapping.review_status != "APPROVED":
            raise ValueError(f"Mapping is not approved: {mapping.mapping_id}")
        metric = metric_by_id.get(mapping.normalized_metric_id)
        if metric is None or not isinstance(metric, MetricDefinition):
            raise ValueError(f"Unknown normalized metric: {mapping.normalized_metric_id}")
        if metric.review_status != "APPROVED":
            raise ValueError(f"Metric definition is not approved: {metric.metric_id}")
        if fact.period.period_type != metric.period_type:
            raise ValueError(f"Period type mismatch for fact: {fact.fact_id}")
        if fact.unit != metric.unit:
            raise ValueError(f"Unit mismatch for fact: {fact.fact_id}")
        if metric.currency_policy != "SOURCE" and fact.currency != metric.currency_policy:
            raise ValueError(f"Currency mismatch for fact: {fact.fact_id}")

        value = (
            fact.value * mapping.sign_multiplier
            if isinstance(fact.value, Decimal)
            else fact.value
        )
        if isinstance(value, KnowledgeState) and value is KnowledgeState.KNOWN:
            raise ValueError("KNOWN requires a decimal value")
        identity = {
            "case_id": case_id,
            "source_fact_id": fact.fact_id,
            "snapshot_id": fact.provenance.snapshot_id,
            "source_content_sha256": fact.provenance.content_sha256,
            "mapping_id": mapping.mapping_id,
            "metric_id": metric.metric_id,
            "version_id": version.version_id,
            "publication_status": version.publication_status.value,
            "scope": fact.scope.key(),
            "period": fact.period.key(),
            "currency": fact.currency,
            "unit": fact.unit,
            "value": str(value),
        }
        digest = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        normalized = NormalizedFact(
            fact_id=f"nf_{digest}",
            source_fact_id=fact.fact_id,
            provenance=fact.provenance,
            case_id=case_id,
            scope=fact.scope,
            metric_id=metric.metric_id,
            period=fact.period,
            currency=fact.currency,
            unit=fact.unit,
            value=value,
            version_id=version.version_id,
            publication_status=version.publication_status,
            normalization_rule=f"mapping:{mapping.mapping_id};sign:{mapping.sign_multiplier}",
            mapping_version=mapping.mapping_id,
            claim_tag=ClaimTag.DERIVED,
        )
        if normalized.key() in normalized_keys:
            raise ValueError(f"Duplicate normalized grain: {normalized.key()}")
        normalized_keys.add(normalized.key())
        result.append(normalized)

    return tuple(sorted(result, key=NormalizedFact.key))
