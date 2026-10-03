from dataclasses import fields, replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from versioned_finance_core.contracts import AccountingScope
from versioned_finance_core.financial_core.linked_statements import (
    BalanceSheet,
    OperatingPeriodInputs,
)
from versioned_finance_core.financial_core.model_path import (
    ModelInputEvidence,
    ModelPathSpec,
    ModelPeriod,
    operating_baseline_ref,
    project_model_path,
)

KST = timezone(timedelta(hours=9))
AVAILABLE = datetime(2026, 1, 15, 12, tzinfo=KST)
CUTOFF = datetime(2026, 2, 1, 0, tzinfo=KST)


def d(value: str | int) -> Decimal:
    return Decimal(value)


def first_inputs() -> OperatingPeriodInputs:
    return OperatingPeriodInputs(
        d(10), d(20), d(8), d(40), d(10), d(5), d(13), d(10),
        d(25), d(35), d(30), d(20), d(15), d(5), d(10),
    )


def second_inputs() -> OperatingPeriodInputs:
    return OperatingPeriodInputs(
        d(8), d(25), d(9), d(50), d(8), d(6), d(12), d(15),
        d(30), d(32), d(28), d(30), d(0), d(20), d(5),
    )


def evidence() -> dict[str, ModelInputEvidence]:
    return {
        field.name: ModelInputEvidence(f"synthetic_assumption_{field.name}", AVAILABLE)
        for field in fields(OperatingPeriodInputs)
    }


def path_spec() -> ModelPathSpec:
    return ModelPathSpec(
        case_id="synthetic_case",
        version_id="forecast_v1",
        accounting_scope=AccountingScope.CONSOLIDATED,
        economic_scope_id="synthetic_parent",
        legal_entity_id="synthetic_issuer",
        currency="KRW",
        unit="KRW_million",
        opening_balance_date=date(2025, 12, 31),
        opening=BalanceSheet(
            d(100), d(20), d(30), d(150), d(25), d(5), d(100), d(170)
        ),
        opening_balance_evidence=ModelInputEvidence(
            "synthetic_opening_balance", datetime(2026, 1, 10, tzinfo=KST)
        ),
        information_cutoff=CUTOFF,
        periods=(
            ModelPeriod(
                "h1", date(2026, 1, 1), date(2026, 6, 30), first_inputs(), evidence()
            ),
            ModelPeriod(
                "h2", date(2026, 7, 1), date(2026, 12, 31), second_inputs(), evidence()
            ),
        ),
    )


def test_two_period_path_links_closing_to_next_opening_and_reconciles() -> None:
    result = project_model_path(path_spec())
    assert result.case_id == "synthetic_case"
    assert result.version_id == "forecast_v1"
    assert result.opening_balance_evidence.source_or_assumption_id == "synthetic_opening_balance"
    assert result.periods[0].input_evidence["selling_price"].source_or_assumption_id == (
        "synthetic_assumption_selling_price"
    )
    assert [period.result.closing.cash for period in result.periods] == [d(140), d(138)]
    assert [period.result.income.net_income for period in result.periods] == [d(52), d(52)]
    assert [period.result.cash_flow.operating for period in result.periods] == [d(60), d(53)]
    assert result.closing.ppe_net == d(182)
    assert result.closing.debt_face == d(90)
    assert result.closing.equity == d(259)
    assert all(
        period.result.balance_residual
        == period.result.cash_residual
        == period.result.debt_residual
        == d(0)
        for period in result.periods
    )


def test_hash_is_deterministic_and_sensitive_to_inputs_and_lineage() -> None:
    original = path_spec()
    first = project_model_path(original)
    assert len(first.content_sha256) == 64
    assert project_model_path(original).content_sha256 == first.content_sha256
    reordered = dict(reversed(list(evidence().items())))
    reordered_period = replace(original.periods[0], input_evidence=reordered)
    assert project_model_path(
        replace(original, periods=(reordered_period, original.periods[1]))
    ).content_sha256 == first.content_sha256
    assert project_model_path(
        replace(original, version_id="forecast_v2")
    ).content_sha256 != first.content_sha256

    altered_period = replace(
        original.periods[1], inputs=replace(second_inputs(), selling_price=d(26))
    )
    changed_value = replace(original, periods=(original.periods[0], altered_period))
    assert project_model_path(changed_value).content_sha256 != first.content_sha256

    changed_evidence = evidence()
    changed_evidence["selling_price"] = ModelInputEvidence("different_source", AVAILABLE)
    source_period = replace(original.periods[1], input_evidence=changed_evidence)
    changed_source = replace(original, periods=(original.periods[0], source_period))
    assert project_model_path(changed_source).content_sha256 != first.content_sha256


def test_operating_baseline_ref_pins_core_path_and_period_boundaries() -> None:
    spec = path_spec()
    path = project_model_path(spec)
    baseline = operating_baseline_ref(path)
    assert baseline.case_id == path.case_id
    assert baseline.version_id == path.version_id
    assert baseline.accounting_scope is AccountingScope.CONSOLIDATED
    assert baseline.economic_scope_id == path.economic_scope_id
    assert baseline.legal_entity_id == path.legal_entity_id
    assert baseline.currency == path.currency
    assert baseline.unit == path.unit
    assert baseline.information_cutoff == CUTOFF
    assert baseline.model_path_sha256 == path.content_sha256
    assert [period.period_id for period in baseline.periods] == ["h1", "h2"]
    assert [(period.period_start, period.period_end) for period in baseline.periods] == [
        (date(2026, 1, 1), date(2026, 6, 30)),
        (date(2026, 7, 1), date(2026, 12, 31)),
    ]
    assert baseline.output_id.startswith("operating_baseline_")
    assert operating_baseline_ref(project_model_path(spec)).output_id == baseline.output_id
    assert operating_baseline_ref(
        replace(path, information_cutoff=CUTOFF.astimezone(UTC))
    ).output_id == baseline.output_id

    changed_source = evidence()
    changed_source["selling_price"] = ModelInputEvidence("revised_source", AVAILABLE)
    changed_period = replace(spec.periods[0], input_evidence=changed_source)
    changed_path = project_model_path(replace(spec, periods=(changed_period, spec.periods[1])))
    assert operating_baseline_ref(changed_path).output_id != baseline.output_id

    changed_scope = project_model_path(replace(spec, economic_scope_id="other_scope"))
    assert operating_baseline_ref(changed_scope).output_id != baseline.output_id

    earlier_end = replace(spec.periods[0], period_end=date(2026, 6, 29))
    earlier_start = replace(spec.periods[1], period_start=date(2026, 6, 30))
    changed_boundaries = project_model_path(replace(spec, periods=(earlier_end, earlier_start)))
    assert operating_baseline_ref(changed_boundaries).output_id != baseline.output_id


def test_operating_baseline_ref_rejects_unreconciled_or_invalid_path() -> None:
    path = project_model_path(path_spec())
    with pytest.raises(ValueError, match="SHA-256"):
        operating_baseline_ref(replace(path, content_sha256="unverified"))
    broken_period = replace(
        path.periods[0],
        result=replace(path.periods[0].result, cash_residual=d(1)),
    )
    with pytest.raises(ValueError, match="do not reconcile"):
        operating_baseline_ref(replace(path, periods=(broken_period, path.periods[1])))
    with pytest.raises(ValueError, match="contiguous"):
        operating_baseline_ref(
            replace(
                path,
                periods=(
                    path.periods[0],
                    replace(path.periods[1], period_start=date(2026, 7, 2)),
                ),
            )
        )
    changed_evidence = dict(path.periods[0].input_evidence)
    changed_evidence["cash_opex"] = ModelInputEvidence("unhashed_source", AVAILABLE)
    with pytest.raises(ValueError, match="does not reproduce"):
        operating_baseline_ref(replace(
            path,
            periods=(
                replace(path.periods[0], input_evidence=changed_evidence),
                path.periods[1],
            ),
        ))


def test_missing_material_driver_evidence_fails_closed() -> None:
    rows = evidence()
    rows.pop("cash_taxes_paid")
    with pytest.raises(ValueError, match="cash_taxes_paid"):
        ModelPeriod("h1", date(2026, 1, 1), date(2026, 6, 30), first_inputs(), rows)


def test_late_driver_or_opening_source_cannot_enter_cutoff() -> None:
    spec = path_spec()
    late_evidence = evidence()
    late_evidence["capex"] = ModelInputEvidence(
        "post_cutoff_capex", datetime(2026, 2, 2, tzinfo=KST)
    )
    late_period = replace(spec.periods[0], input_evidence=late_evidence)
    with pytest.raises(ValueError, match="capex"):
        project_model_path(replace(spec, periods=(late_period, spec.periods[1])))
    with pytest.raises(ValueError, match="opening balance evidence"):
        project_model_path(
            replace(
                spec,
                opening_balance_evidence=ModelInputEvidence(
                    "late_opening", datetime(2026, 2, 2, tzinfo=KST)
                ),
            )
        )


def test_noncontiguous_or_duplicate_period_is_rejected() -> None:
    spec = path_spec()
    delayed = replace(spec.periods[1], period_start=date(2026, 7, 2))
    with pytest.raises(ValueError, match="not contiguous"):
        project_model_path(replace(spec, periods=(spec.periods[0], delayed)))
    repeated = replace(spec.periods[1], period_id="h1")
    with pytest.raises(ValueError, match="duplicate period_id"):
        project_model_path(replace(spec, periods=(spec.periods[0], repeated)))


def test_source_mapping_is_defensively_frozen() -> None:
    records = evidence()
    period = ModelPeriod(
        "h1", date(2026, 1, 1), date(2026, 6, 30), first_inputs(), records
    )
    records["selling_price"] = ModelInputEvidence("changed", AVAILABLE)
    assert period.input_evidence["selling_price"].source_or_assumption_id == (
        "synthetic_assumption_selling_price"
    )
    with pytest.raises(TypeError):
        period.input_evidence["selling_price"] = ModelInputEvidence(  # type: ignore[index]
            "changed", AVAILABLE
        )
