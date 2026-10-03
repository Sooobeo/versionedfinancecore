from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal

import pytest

from versioned_finance_core.contracts import (
    AccountingScope,
    ClaimTag,
    KnowledgeState,
    NormalizedFact,
    Period,
    PublicationStatus,
    ScopeRef,
    SourceProvenance,
)
from versioned_finance_core.financial_core import (
    evaluate_reported_balance_sheet_identity,
    evaluate_reported_operating_income_identity,
)

CUTOFF = datetime.fromisoformat("2026-05-21T23:59:59-04:00")
PUBLIC_AT = datetime.fromisoformat("2026-03-13T20:06:24+00:00")


def _fact(metric: str, value: str | KnowledgeState, *, instant: bool = False) -> NormalizedFact:
    return NormalizedFact(
        fact_id=f"nf_{metric}",
        source_fact_id=f"raw_{metric}",
        provenance=SourceProvenance(
            source_id="sec_10k",
            snapshot_id="snap_10k",
            content_sha256="a" * 64,
            first_public_at=PUBLIC_AT,
            retrieved_at=datetime.fromisoformat("2026-09-29T12:00:00+00:00"),
        ),
        case_id="case_1",
        scope=ScopeRef("group", AccountingScope.CONSOLIDATED, None, "issuer", None, None),
        metric_id=metric,
        period=(
            Period(date(2026, 1, 31), date(2026, 1, 31), "INSTANT")
            if instant else Period(date(2025, 2, 1), date(2026, 1, 31), "YEAR")
        ),
        currency="USD",
        unit="USD",
        value=value if isinstance(value, KnowledgeState) else Decimal(value),
        version_id="fy26_filed",
        publication_status=PublicationStatus.FILED,
        normalization_rule="mapping:source;sign:1",
        mapping_version="source",
        claim_tag=ClaimTag.DERIVED,
    )


def _income_facts() -> tuple[NormalizedFact, ...]:
    return (
        _fact("total_revenue", "713163000000"),
        _fact("cost_of_sales", "535395000000"),
        _fact("operating_sga", "147943000000"),
        _fact("operating_income", "29825000000"),
    )


def test_reported_annual_operating_income_known_answer_and_determinism() -> None:
    facts = _income_facts()
    result = evaluate_reported_operating_income_identity(*facts, analysis_cutoff=CUTOFF)
    assert result.calculated_amount == Decimal(29825000000)
    assert result.reported_amount == Decimal(29825000000)
    assert result.residual == 0
    assert result.reconciled is True
    assert result.normalized_fact_ids == tuple(fact.fact_id for fact in facts)
    assert result.output_id == evaluate_reported_operating_income_identity(
        *facts, analysis_cutoff=CUTOFF
    ).output_id
    assert result.as_dict()["source_content_sha256"] == ["a" * 64] * 4


def test_reported_balance_sheet_compares_published_totals_only() -> None:
    assets = _fact("assets", "284668000000", instant=True)
    total_liabilities_equity = _fact("liabilities_equity", "284668000000", instant=True)
    result = evaluate_reported_balance_sheet_identity(
        assets, total_liabilities_equity, analysis_cutoff=CUTOFF
    )
    assert result.residual == 0
    assert result.reconciled is True
    assert result.identity_kind == "BALANCE_SHEET"


def test_nonzero_residual_is_exposed_without_tolerance_or_plug() -> None:
    facts = _income_facts()
    shifted = replace(facts[-1], value=Decimal(29824999999))
    result = evaluate_reported_operating_income_identity(
        *facts[:-1], shifted, analysis_cutoff=CUTOFF
    )
    assert result.residual == Decimal(1)
    assert result.reconciled is False
    assert result.output_id != evaluate_reported_operating_income_identity(
        *facts, analysis_cutoff=CUTOFF
    ).output_id


def test_reported_identity_preserves_cent_precision_beyond_default_context() -> None:
    huge = Decimal("1000000000000000000000000000000.01")
    assets = _fact("assets", "1", instant=True)
    total = _fact("liabilities_equity", "1", instant=True)
    result = evaluate_reported_balance_sheet_identity(
        replace(assets, value=huge), replace(total, value=huge), analysis_cutoff=CUTOFF
    )
    assert result.residual == 0
    facts = _income_facts()
    precise = evaluate_reported_operating_income_identity(
        replace(facts[0], value=huge),
        replace(facts[1], value=Decimal(1000000000000000000000000000000)),
        replace(facts[2], value=Decimal(0)),
        replace(facts[3], value=Decimal("0.01")),
        analysis_cutoff=CUTOFF,
    )
    assert precise.calculated_amount == Decimal("0.01")
    assert precise.residual == 0


def test_missing_amount_stays_explicitly_unknown() -> None:
    facts = _income_facts()
    unknown = replace(facts[2], value=KnowledgeState.UNKNOWN)
    result = evaluate_reported_operating_income_identity(
        facts[0], facts[1], unknown, facts[3], analysis_cutoff=CUTOFF
    )
    assert result.knowledge_state is KnowledgeState.UNKNOWN
    assert result.calculated_amount is None
    assert result.residual is None
    assert result.reconciled is None


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"version_id": "other"}, "version/period"),
        ({"period": Period(date(2024, 2, 1), date(2025, 1, 31), "YEAR")}, "version/period"),
        ({"currency": "EUR"}, "currency/unit"),
        ({"unit": "USD_MILLIONS"}, "currency/unit"),
        ({"scope": ScopeRef("other", AccountingScope.CONSOLIDATED, None, "issuer", None, None)},
         "scope"),
        ({"source_fact_id": "raw_total_revenue"}, "source fact IDs"),
    ],
)
def test_reported_identity_rejects_cross_grain_or_reused_fact(change: dict, message: str) -> None:
    facts = _income_facts()
    changed = replace(facts[2], **change)
    with pytest.raises(ValueError, match=message):
        evaluate_reported_operating_income_identity(
            facts[0], facts[1], changed, facts[3], analysis_cutoff=CUTOFF
        )


def test_reported_identity_rejects_later_disclosure_and_mixed_snapshot() -> None:
    facts = _income_facts()
    later = replace(
        facts[1],
        provenance=replace(
            facts[1].provenance,
            first_public_at=datetime.fromisoformat("2026-05-22T00:00:00-04:00"),
        ),
    )
    with pytest.raises(ValueError, match="first public"):
        evaluate_reported_operating_income_identity(
            facts[0], later, facts[2], facts[3], analysis_cutoff=CUTOFF
        )
    other_snapshot = replace(
        facts[1], provenance=replace(facts[1].provenance, snapshot_id="other")
    )
    with pytest.raises(ValueError, match="snapshot"):
        evaluate_reported_operating_income_identity(
            facts[0], other_snapshot, facts[2], facts[3], analysis_cutoff=CUTOFF
        )


def test_reported_identity_rejects_period_shape_and_float() -> None:
    assets = _fact("assets", "284668000000", instant=True)
    total = _fact("liabilities_equity", "284668000000", instant=True)
    with pytest.raises(ValueError, match="duration"):
        evaluate_reported_operating_income_identity(
            assets, total, replace(total, fact_id="other", source_fact_id="other"),
            replace(assets, fact_id="last", source_fact_id="last"),
            analysis_cutoff=CUTOFF,
        )
    with pytest.raises(ValueError, match="instant"):
        evaluate_reported_balance_sheet_identity(
            _income_facts()[0], _income_facts()[1], analysis_cutoff=CUTOFF
        )
    with pytest.raises(TypeError, match="finite Decimal"):
        evaluate_reported_balance_sheet_identity(
            replace(assets, value=1.0), total, analysis_cutoff=CUTOFF
        )
