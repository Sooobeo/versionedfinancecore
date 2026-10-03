"""Source-pinned, plug-free consolidated three-statement forecast.

This model has a deliberately explicit accounting boundary. A period supplies
revenue and operating expense forecasts, working-capital closing balances, and
cash/noncash changes in other long-lived assets and liabilities. It does not
silently infer lease additions, restricted-cash movements, FX, acquisitions,
or a financing transaction from a balance-sheet residual. Those effects need
their own evidenced inputs; unmatched noncash changes fail the balance check.

The cash scope is balance-sheet cash and equivalents. A case with material
restricted cash must establish its treatment before using the projected cash
flow statement as a reported cash-flow reproduction.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType

from versioned_finance_core.contracts import (
    AccountingScope,
    KnowledgeState,
    ScenarioPurpose,
    VersionType,
)
from versioned_finance_core.financial_core.cash_components import CashView
from versioned_finance_core.financial_core.free_cash_flow import (
    FREE_CASH_FLOW_SCHEMA_VERSION,
    FreeCashFlowPathResult,
    FreeCashFlowPeriod,
    UnleveredCashTaxInput,
)
from versioned_finance_core.financial_core.identities import (
    _exact_product,
    _exact_sum,
    cash_rollforward_residual,
    projected_closing_cash,
)
from versioned_finance_core.financial_core.model_path import (
    ModelInputEvidence,
    OperatingBaselinePeriodRef,
    OperatingBaselineRef,
)

CONSOLIDATED_FORECAST_SCHEMA_VERSION = 1
CONSOLIDATED_CASH_FLOW_SCHEMA_VERSION = 1


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be an offset-aware datetime")
    return value


def _date(value: date, name: str) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TypeError(f"{name} must be a date")
    return value


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _hash(prefix: str, payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()}"


def _decimal_record(record: object) -> dict[str, str]:
    return {field.name: str(getattr(record, field.name)) for field in fields(record)}


def _evidence_record(record: ModelInputEvidence) -> dict[str, str]:
    return {
        "source_or_assumption_id": record.source_or_assumption_id,
        "available_at": _utc(record.available_at),
    }


def _validate_decimals(record: object, *, signed: frozenset[str] = frozenset()) -> None:
    for field in fields(record):
        value = getattr(record, field.name)
        if not isinstance(value, Decimal) or not value.is_finite():
            raise ValueError(f"{field.name} must be a finite Decimal")
        if field.name not in signed and value < 0:
            raise ValueError(f"{field.name} must be nonnegative")


@dataclass(frozen=True, slots=True)
class ConsolidatedBalanceSheet:
    """One currency and scope, with independently sourced opening categories.

    ``other_long_lived_assets`` can include disclosed lease right-of-use assets,
    goodwill and other long-term assets. ``other_liabilities`` retains disclosed
    leases, deferred taxes and other claims. Their changes are classified by
    explicit period inputs; the opening grouping alone makes no cash-flow claim.
    """

    cash: Decimal
    receivables: Decimal
    inventory: Decimal
    other_operating_assets: Decimal
    ppe_net: Decimal
    other_long_lived_assets: Decimal
    payables: Decimal
    accrued_operating_liabilities: Decimal
    tax_payable: Decimal
    debt_carrying: Decimal
    dividends_payable: Decimal
    other_liabilities: Decimal
    equity: Decimal

    def __post_init__(self) -> None:
        _validate_decimals(self, signed=frozenset({"cash", "equity"}))

    @property
    def assets(self) -> Decimal:
        return _exact_sum((
            self.cash, self.receivables, self.inventory,
            self.other_operating_assets, self.ppe_net,
            self.other_long_lived_assets,
        ))

    @property
    def liabilities_and_equity(self) -> Decimal:
        return _exact_sum((
            self.payables, self.accrued_operating_liabilities,
            self.tax_payable, self.debt_carrying, self.dividends_payable,
            self.other_liabilities, self.equity,
        ))

    @property
    def residual(self) -> Decimal:
        return _exact_sum((self.assets, self.liabilities_and_equity.copy_negate()))


@dataclass(frozen=True, slots=True)
class ConsolidatedPeriodInputs:
    """Explicit period flows and closing operating balances.

    All cash purchases, debt proceeds, payments and expenses are positive
    magnitudes. Signed change fields preserve direction: a positive asset cash
    change consumes cash; a positive liability cash change provides cash.
    ``depreciation`` is the modeled depreciation/amortization that reduces the
    modeled PPE balance. A case with material amortization of another asset
    must use the noncash schedules and reconcile that separately.
    """

    net_sales: Decimal
    other_revenue: Decimal
    cash_operating_expense: Decimal
    depreciation: Decimal
    interest_expense: Decimal
    cash_other_income: Decimal
    tax_expense: Decimal
    cash_taxes_paid: Decimal
    closing_receivables: Decimal
    closing_inventory: Decimal
    closing_other_operating_assets: Decimal
    closing_payables: Decimal
    closing_accrued_operating_liabilities: Decimal
    capex: Decimal
    ppe_noncash_change: Decimal
    other_long_lived_assets_investing_cash_change: Decimal
    other_long_lived_assets_noncash_change: Decimal
    debt_issuance: Decimal
    debt_repayment: Decimal
    debt_carrying_noncash_change: Decimal
    other_liabilities_operating_cash_change: Decimal
    other_liabilities_financing_cash_change: Decimal
    other_liabilities_noncash_change: Decimal
    dividends_declared: Decimal
    dividends_paid: Decimal
    share_issuance: Decimal
    share_repurchases: Decimal
    other_comprehensive_income: Decimal

    def __post_init__(self) -> None:
        _validate_decimals(self, signed=frozenset({
            "cash_other_income", "tax_expense", "ppe_noncash_change",
            "other_long_lived_assets_investing_cash_change",
            "other_long_lived_assets_noncash_change",
            "debt_carrying_noncash_change",
            "other_liabilities_operating_cash_change",
            "other_liabilities_financing_cash_change",
            "other_liabilities_noncash_change", "other_comprehensive_income",
        }))


OPENING_FIELDS = frozenset(field.name for field in fields(ConsolidatedBalanceSheet))
PERIOD_FIELDS = frozenset(field.name for field in fields(ConsolidatedPeriodInputs))


@dataclass(frozen=True, slots=True)
class ConsolidatedOpeningAggregation:
    opening: ConsolidatedBalanceSheet
    opening_evidence: Mapping[str, ModelInputEvidence]
    groups: Mapping[str, tuple[str, ...]]
    source_evidence: Mapping[str, ModelInputEvidence]
    reported_total_assets: Decimal
    reported_total_liabilities_equity: Decimal
    output_id: str

    def as_dict(self) -> dict[str, object]:
        return {
            "opening": _decimal_record(self.opening),
            "opening_evidence": {
                name: _evidence_record(record)
                for name, record in sorted(self.opening_evidence.items())
            },
            "groups": {name: list(ids) for name, ids in sorted(self.groups.items())},
            "source_evidence": {
                name: _evidence_record(record)
                for name, record in sorted(self.source_evidence.items())
            },
            "reported_total_assets": str(self.reported_total_assets),
            "reported_total_liabilities_equity": str(
                self.reported_total_liabilities_equity
            ),
            "output_id": self.output_id,
        }


def aggregate_disclosed_opening_balance(
    disclosed_amounts: Mapping[str, Decimal],
    groups: Mapping[str, tuple[str, ...]],
    source_evidence: Mapping[str, ModelInputEvidence],
    *,
    asset_total_metric_id: str,
    liabilities_equity_total_metric_id: str,
    information_cutoff: datetime,
) -> ConsolidatedOpeningAggregation:
    """Group every disclosed balance once and check both reported BS totals.

    The caller must supply every detailed line, both reported totals and each
    line's source/assumption ID plus availability time. An unassigned line,
    duplicate use, missing category or post-cutoff fact fails closed. No
    subtraction from a reported total creates an unexplained other account.
    """

    _aware(information_cutoff, "information_cutoff")
    _required(asset_total_metric_id, "asset_total_metric_id")
    _required(liabilities_equity_total_metric_id, "liabilities_equity_total_metric_id")
    if asset_total_metric_id == liabilities_equity_total_metric_id:
        raise ValueError("reported asset and liability/equity totals need distinct IDs")
    if not isinstance(disclosed_amounts, Mapping) or not isinstance(groups, Mapping):
        raise TypeError("disclosed_amounts and groups must be mappings")
    if not isinstance(source_evidence, Mapping):
        raise TypeError("source_evidence must be a mapping")
    amounts = dict(disclosed_amounts)
    evidence = dict(source_evidence)
    missing_evidence = amounts.keys() - evidence.keys()
    extra_evidence = evidence.keys() - amounts.keys()
    if missing_evidence or extra_evidence:
        raise ValueError(
            "source_evidence must match every disclosed metric; "
            f"missing={sorted(missing_evidence)}, extra={sorted(extra_evidence)}"
        )
    for name, value in amounts.items():
        _required(name, "disclosed metric ID")
        if not isinstance(value, Decimal) or not value.is_finite():
            raise ValueError(f"{name} amount must be a finite Decimal")
        if not isinstance(evidence[name], ModelInputEvidence):
            raise TypeError(f"{name} evidence must be ModelInputEvidence")
        if evidence[name].available_at > information_cutoff:
            raise ValueError(f"{name} evidence unavailable at cutoff")
    for total_id in (asset_total_metric_id, liabilities_equity_total_metric_id):
        if total_id not in amounts:
            raise ValueError(f"missing reported balance-sheet total: {total_id}")
    if set(groups) != OPENING_FIELDS:
        raise ValueError(
            "groups must match every opening balance field; "
            f"missing={sorted(OPENING_FIELDS - groups.keys())}, "
            f"extra={sorted(groups.keys() - OPENING_FIELDS)}"
        )
    group_members: list[str] = []
    frozen_groups: dict[str, tuple[str, ...]] = {}
    for field_name, raw_ids in groups.items():
        if not isinstance(raw_ids, tuple) or not raw_ids:
            raise ValueError(f"{field_name} needs a nonempty tuple of disclosed metric IDs")
        if any(not isinstance(raw_id, str) or not raw_id.strip() for raw_id in raw_ids):
            raise ValueError(f"{field_name} has an invalid disclosed metric ID")
        frozen_groups[field_name] = raw_ids
        group_members.extend(raw_ids)
    if len(group_members) != len(set(group_members)):
        raise ValueError("disclosed balance metric reused across opening groups")
    total_ids = {asset_total_metric_id, liabilities_equity_total_metric_id}
    if total_ids & set(group_members):
        raise ValueError("reported totals cannot be used as opening line amounts")
    expected_members = set(amounts) - total_ids
    if set(group_members) != expected_members:
        raise ValueError(
            "every disclosed detailed balance must be assigned exactly once; "
            f"missing={sorted(expected_members - set(group_members))}, "
            f"unknown={sorted(set(group_members) - expected_members)}"
        )

    grouped_amounts = {
        name: _exact_sum(amounts[raw_id] for raw_id in ids)
        for name, ids in frozen_groups.items()
    }
    opening = ConsolidatedBalanceSheet(**grouped_amounts)
    if opening.assets != amounts[asset_total_metric_id]:
        raise ValueError("opening grouped assets do not match reported total assets")
    if opening.liabilities_and_equity != amounts[liabilities_equity_total_metric_id]:
        raise ValueError("opening grouped liabilities/equity do not match reported total")
    if opening.residual != 0:
        raise ValueError("reported opening balance sheet does not reconcile")
    opening_evidence: dict[str, ModelInputEvidence] = {}
    for name, ids in frozen_groups.items():
        if len(ids) == 1:
            opening_evidence[name] = evidence[ids[0]]
        else:
            opening_evidence[name] = ModelInputEvidence(
                source_or_assumption_id=_hash("grouped_opening", {
                    "field": name,
                    "members": [
                        {
                            "metric_id": raw_id,
                            "amount": str(amounts[raw_id]),
                            "evidence": _evidence_record(evidence[raw_id]),
                        }
                        for raw_id in ids
                    ],
                }),
                available_at=max(evidence[raw_id].available_at for raw_id in ids),
            )
    payload: dict[str, object] = {
        "schema_version": CONSOLIDATED_FORECAST_SCHEMA_VERSION,
        "disclosed_amounts": {name: str(amounts[name]) for name in sorted(amounts)},
        "groups": {name: list(ids) for name, ids in sorted(frozen_groups.items())},
        "source_evidence": {
            name: _evidence_record(evidence[name]) for name in sorted(evidence)
        },
        "asset_total_metric_id": asset_total_metric_id,
        "liabilities_equity_total_metric_id": liabilities_equity_total_metric_id,
        "information_cutoff": _utc(information_cutoff),
    }
    return ConsolidatedOpeningAggregation(
        opening=opening,
        opening_evidence=MappingProxyType(opening_evidence),
        groups=MappingProxyType(frozen_groups),
        source_evidence=MappingProxyType(evidence),
        reported_total_assets=amounts[asset_total_metric_id],
        reported_total_liabilities_equity=amounts[liabilities_equity_total_metric_id],
        output_id=_hash("core_grouped_opening", payload),
    )


@dataclass(frozen=True, slots=True)
class ConsolidatedDriverInputs:
    """Comparable-period growth and fiscal-year-end operating-balance drivers.

    For an incomplete fiscal-year forecast, ``fiscal_year_net_sales_to_date``,
    ``fiscal_year_other_revenue_to_date`` and ``fiscal_year_capex_to_date``
    are actual amounts before this period.
    They give annual sales for end-balance ratios and annual capex guidance
    without annualizing a stub's flow arbitrarily. Full-year periods explicitly
    supply zero for both fields. All rates and historical comparison amounts
    require their own provenance through ``derive_consolidated_period``.
    """

    comparable_prior_net_sales: Decimal
    comparable_prior_other_revenue: Decimal
    net_sales_growth_rate: Decimal
    other_revenue_growth_rate: Decimal
    fiscal_year_net_sales_to_date: Decimal
    fiscal_year_other_revenue_to_date: Decimal
    fiscal_year_capex_to_date: Decimal
    operating_margin_of_total_revenue: Decimal
    depreciation_rate_of_total_revenue: Decimal
    capex_rate_of_fiscal_net_sales: Decimal
    receivables_rate_of_fiscal_net_sales: Decimal
    inventory_rate_of_fiscal_net_sales: Decimal
    other_operating_assets_rate_of_fiscal_net_sales: Decimal
    payables_rate_of_fiscal_net_sales: Decimal
    accrued_operating_liabilities_rate_of_fiscal_net_sales: Decimal
    interest_expense: Decimal
    cash_other_income: Decimal
    tax_rate_on_pretax_income: Decimal
    cash_tax_rate_on_pretax_income: Decimal
    ppe_noncash_change: Decimal
    other_long_lived_assets_investing_cash_change: Decimal
    other_long_lived_assets_noncash_change: Decimal
    debt_issuance: Decimal
    debt_repayment: Decimal
    debt_carrying_noncash_change: Decimal
    other_liabilities_operating_cash_change: Decimal
    other_liabilities_financing_cash_change: Decimal
    other_liabilities_noncash_change: Decimal
    dividends_declared: Decimal
    dividends_paid: Decimal
    share_issuance: Decimal
    share_repurchases: Decimal
    other_comprehensive_income: Decimal

    def __post_init__(self) -> None:
        _validate_decimals(self, signed=frozenset({
            "net_sales_growth_rate", "other_revenue_growth_rate",
            "operating_margin_of_total_revenue", "cash_other_income",
            "ppe_noncash_change",
            "other_long_lived_assets_investing_cash_change",
            "other_long_lived_assets_noncash_change",
            "debt_carrying_noncash_change",
            "other_liabilities_operating_cash_change",
            "other_liabilities_financing_cash_change",
            "other_liabilities_noncash_change", "other_comprehensive_income",
        }))
        if self.net_sales_growth_rate < -1 or self.other_revenue_growth_rate < -1:
            raise ValueError("revenue growth rates cannot be below -100%")


DRIVER_FIELDS = frozenset(field.name for field in fields(ConsolidatedDriverInputs))


def comparable_remaining_period_base(
    prior_fiscal_year_amount: Decimal, prior_elapsed_amount: Decimal
) -> Decimal:
    """Subtract a reported comparative YTD flow from a reported fiscal flow."""

    for name, value in (
        ("prior_fiscal_year_amount", prior_fiscal_year_amount),
        ("prior_elapsed_amount", prior_elapsed_amount),
    ):
        if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
            raise ValueError(f"{name} must be a nonnegative finite Decimal")
    if prior_elapsed_amount > prior_fiscal_year_amount:
        raise ValueError("elapsed comparative amount exceeds reported fiscal amount")
    return _exact_sum((prior_fiscal_year_amount, prior_elapsed_amount.copy_negate()))


def reported_other_revenue(
    reported_total_revenue: Decimal, reported_net_sales: Decimal
) -> Decimal:
    """Derive disclosed other revenue from a same-scope total and net sales."""

    for name, value in (
        ("reported_total_revenue", reported_total_revenue),
        ("reported_net_sales", reported_net_sales),
    ):
        if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
            raise ValueError(f"{name} must be a nonnegative finite Decimal")
    if reported_net_sales > reported_total_revenue:
        raise ValueError("reported net sales exceed reported total revenue")
    return _exact_sum((reported_total_revenue, reported_net_sales.copy_negate()))


def derive_consolidated_inputs(drivers: ConsolidatedDriverInputs) -> ConsolidatedPeriodInputs:
    """Turn a sourced growth/margin/reinvestment policy into direct Core inputs."""

    if not isinstance(drivers, ConsolidatedDriverInputs):
        raise TypeError("drivers must be ConsolidatedDriverInputs")
    net_sales = _exact_product(
        drivers.comparable_prior_net_sales,
        _exact_sum((Decimal(1), drivers.net_sales_growth_rate)),
    )
    other_revenue = _exact_product(
        drivers.comparable_prior_other_revenue,
        _exact_sum((Decimal(1), drivers.other_revenue_growth_rate)),
    )
    total_revenue = _exact_sum((net_sales, other_revenue))
    fiscal_net_sales = _exact_sum((drivers.fiscal_year_net_sales_to_date, net_sales))
    depreciation = _exact_product(
        total_revenue, drivers.depreciation_rate_of_total_revenue
    )
    operating_income = _exact_product(
        total_revenue, drivers.operating_margin_of_total_revenue
    )
    cash_operating_expense = _exact_sum((
        total_revenue, operating_income.copy_negate(), depreciation.copy_negate()
    ))
    if cash_operating_expense < 0:
        raise ValueError("operating margin and depreciation imply negative cash costs")
    pretax_income = _exact_sum((
        operating_income, drivers.interest_expense.copy_negate(),
        drivers.cash_other_income,
    ))
    tax_expense = _exact_product(pretax_income, drivers.tax_rate_on_pretax_income)
    cash_taxes_paid = _exact_product(
        pretax_income, drivers.cash_tax_rate_on_pretax_income
    )
    if cash_taxes_paid < 0:
        raise ValueError("a loss period needs an explicit nonnegative cash tax policy")
    capex = _exact_sum((
        _exact_product(fiscal_net_sales, drivers.capex_rate_of_fiscal_net_sales),
        drivers.fiscal_year_capex_to_date.copy_negate(),
    ))
    if capex < 0:
        raise ValueError("fiscal capex policy is below actual capex already incurred")
    return ConsolidatedPeriodInputs(
        net_sales=net_sales,
        other_revenue=other_revenue,
        cash_operating_expense=cash_operating_expense,
        depreciation=depreciation,
        interest_expense=drivers.interest_expense,
        cash_other_income=drivers.cash_other_income,
        tax_expense=tax_expense,
        cash_taxes_paid=cash_taxes_paid,
        closing_receivables=_exact_product(
            fiscal_net_sales, drivers.receivables_rate_of_fiscal_net_sales
        ),
        closing_inventory=_exact_product(
            fiscal_net_sales, drivers.inventory_rate_of_fiscal_net_sales
        ),
        closing_other_operating_assets=_exact_product(
            fiscal_net_sales, drivers.other_operating_assets_rate_of_fiscal_net_sales
        ),
        closing_payables=_exact_product(
            fiscal_net_sales, drivers.payables_rate_of_fiscal_net_sales
        ),
        closing_accrued_operating_liabilities=_exact_product(
            fiscal_net_sales,
            drivers.accrued_operating_liabilities_rate_of_fiscal_net_sales,
        ),
        capex=capex,
        ppe_noncash_change=drivers.ppe_noncash_change,
        other_long_lived_assets_investing_cash_change=(
            drivers.other_long_lived_assets_investing_cash_change
        ),
        other_long_lived_assets_noncash_change=(
            drivers.other_long_lived_assets_noncash_change
        ),
        debt_issuance=drivers.debt_issuance,
        debt_repayment=drivers.debt_repayment,
        debt_carrying_noncash_change=drivers.debt_carrying_noncash_change,
        other_liabilities_operating_cash_change=(
            drivers.other_liabilities_operating_cash_change
        ),
        other_liabilities_financing_cash_change=(
            drivers.other_liabilities_financing_cash_change
        ),
        other_liabilities_noncash_change=drivers.other_liabilities_noncash_change,
        dividends_declared=drivers.dividends_declared,
        dividends_paid=drivers.dividends_paid,
        share_issuance=drivers.share_issuance,
        share_repurchases=drivers.share_repurchases,
        other_comprehensive_income=drivers.other_comprehensive_income,
    )


def _validated_evidence(
    mapping: Mapping[str, ModelInputEvidence], expected: frozenset[str], name: str
) -> Mapping[str, ModelInputEvidence]:
    if not isinstance(mapping, Mapping):
        raise TypeError(f"{name} must be a mapping")
    evidence = dict(mapping)
    missing = expected - evidence.keys()
    extra = evidence.keys() - expected
    if missing or extra:
        raise ValueError(
            f"{name} must match every field; missing={sorted(missing)}, extra={sorted(extra)}"
        )
    for field_name, record in evidence.items():
        if not isinstance(record, ModelInputEvidence):
            raise TypeError(f"{field_name} evidence must be ModelInputEvidence")
    return MappingProxyType(evidence)


_NET_SALES_DRIVERS = ("comparable_prior_net_sales", "net_sales_growth_rate")
_OTHER_REVENUE_DRIVERS = (
    "comparable_prior_other_revenue", "other_revenue_growth_rate"
)
_FISCAL_SALES_DRIVERS = (
    *_NET_SALES_DRIVERS, "fiscal_year_net_sales_to_date"
)
_TOTAL_REVENUE_DRIVERS = (*_NET_SALES_DRIVERS, *_OTHER_REVENUE_DRIVERS)
_OPERATING_DRIVERS = (
    *_TOTAL_REVENUE_DRIVERS, "operating_margin_of_total_revenue",
    "depreciation_rate_of_total_revenue",
)
_PRETAX_DRIVERS = (
    *_TOTAL_REVENUE_DRIVERS, "operating_margin_of_total_revenue",
    "interest_expense", "cash_other_income",
)
_DERIVED_INPUT_DRIVERS: Mapping[str, tuple[str, ...]] = {
    "net_sales": _NET_SALES_DRIVERS,
    "other_revenue": _OTHER_REVENUE_DRIVERS,
    "cash_operating_expense": _OPERATING_DRIVERS,
    "depreciation": (*_TOTAL_REVENUE_DRIVERS, "depreciation_rate_of_total_revenue"),
    "tax_expense": (*_PRETAX_DRIVERS, "tax_rate_on_pretax_income"),
    "cash_taxes_paid": (*_PRETAX_DRIVERS, "cash_tax_rate_on_pretax_income"),
    "closing_receivables": (
        *_FISCAL_SALES_DRIVERS, "receivables_rate_of_fiscal_net_sales"
    ),
    "closing_inventory": (
        *_FISCAL_SALES_DRIVERS, "inventory_rate_of_fiscal_net_sales"
    ),
    "closing_other_operating_assets": (
        *_FISCAL_SALES_DRIVERS, "other_operating_assets_rate_of_fiscal_net_sales"
    ),
    "closing_payables": (
        *_FISCAL_SALES_DRIVERS, "payables_rate_of_fiscal_net_sales"
    ),
    "closing_accrued_operating_liabilities": (
        *_FISCAL_SALES_DRIVERS,
        "accrued_operating_liabilities_rate_of_fiscal_net_sales",
    ),
    "capex": (
        *_FISCAL_SALES_DRIVERS, "fiscal_year_capex_to_date",
        "capex_rate_of_fiscal_net_sales",
    ),
}


def _derived_input_evidence(
    driver_evidence: Mapping[str, ModelInputEvidence]
) -> dict[str, ModelInputEvidence]:
    direct: dict[str, ModelInputEvidence] = {}
    for name in PERIOD_FIELDS:
        dependencies = _DERIVED_INPUT_DRIVERS.get(name)
        if dependencies is None:
            direct[name] = driver_evidence[name]
            continue
        records = {driver: driver_evidence[driver] for driver in dependencies}
        direct[name] = ModelInputEvidence(
            source_or_assumption_id=_hash("driver_lineage", {
                "input_field": name,
                "drivers": {
                    driver: _evidence_record(record)
                    for driver, record in sorted(records.items())
                },
            }),
            available_at=max(record.available_at for record in records.values()),
        )
    return direct


@dataclass(frozen=True, slots=True)
class ConsolidatedForecastPeriod:
    period_id: str
    period_start: date
    period_end: date
    inputs: ConsolidatedPeriodInputs
    input_evidence: Mapping[str, ModelInputEvidence]
    driver_inputs: ConsolidatedDriverInputs | None = None
    driver_evidence: Mapping[str, ModelInputEvidence] | None = None

    def __post_init__(self) -> None:
        _required(self.period_id, "period_id")
        _date(self.period_start, "period_start")
        _date(self.period_end, "period_end")
        if self.period_end < self.period_start:
            raise ValueError("period_end must not precede period_start")
        if not isinstance(self.inputs, ConsolidatedPeriodInputs):
            raise TypeError("inputs must be ConsolidatedPeriodInputs")
        object.__setattr__(
            self, "input_evidence",
            _validated_evidence(self.input_evidence, PERIOD_FIELDS, "input_evidence"),
        )
        if (self.driver_inputs is None) != (self.driver_evidence is None):
            raise ValueError("driver_inputs and driver_evidence must be supplied together")
        if self.driver_inputs is not None:
            if not isinstance(self.driver_inputs, ConsolidatedDriverInputs):
                raise TypeError("driver_inputs must be ConsolidatedDriverInputs")
            driver_evidence = _validated_evidence(
                self.driver_evidence, DRIVER_FIELDS, "driver_evidence"
            )
            object.__setattr__(self, "driver_evidence", driver_evidence)
            if derive_consolidated_inputs(self.driver_inputs) != self.inputs:
                raise ValueError("direct inputs do not reproduce from retained drivers")
            if _derived_input_evidence(driver_evidence) != self.input_evidence:
                raise ValueError("direct input evidence does not match driver lineage")


def derive_consolidated_period(
    *,
    period_id: str,
    period_start: date,
    period_end: date,
    drivers: ConsolidatedDriverInputs,
    driver_evidence: Mapping[str, ModelInputEvidence],
) -> ConsolidatedForecastPeriod:
    """Freeze each driver, its evidence, and all Core-derived direct inputs."""

    retained = _validated_evidence(driver_evidence, DRIVER_FIELDS, "driver_evidence")
    return ConsolidatedForecastPeriod(
        period_id=period_id,
        period_start=period_start,
        period_end=period_end,
        inputs=derive_consolidated_inputs(drivers),
        input_evidence=_derived_input_evidence(retained),
        driver_inputs=drivers,
        driver_evidence=retained,
    )


def projected_fiscal_revenue_basis(
    period: ConsolidatedForecastPeriod,
) -> tuple[Decimal, Decimal]:
    """Return modeled fiscal net sales/other revenue, including actual YTD.

    The pair can seed the following full-year comparable growth driver. It is
    calculated in Core so orchestration need not duplicate the fiscal-stub
    bridge or silently omit actual revenue preceding the forecast period.
    """

    if not isinstance(period, ConsolidatedForecastPeriod):
        raise TypeError("period must be ConsolidatedForecastPeriod")
    if period.driver_inputs is None:
        raise ValueError("period must retain sourced driver inputs")
    return (
        _exact_sum((
            period.driver_inputs.fiscal_year_net_sales_to_date,
            period.inputs.net_sales,
        )),
        _exact_sum((
            period.driver_inputs.fiscal_year_other_revenue_to_date,
            period.inputs.other_revenue,
        )),
    )


@dataclass(frozen=True, slots=True)
class ConsolidatedForecastSpec:
    case_id: str
    version_id: str
    version_type: VersionType
    scenario_id: str
    scenario_purpose: ScenarioPurpose
    accounting_scope: AccountingScope
    economic_scope_id: str
    legal_entity_id: str | None
    currency: str
    unit: str
    opening_balance_date: date
    opening: ConsolidatedBalanceSheet
    opening_evidence: Mapping[str, ModelInputEvidence]
    information_cutoff: datetime
    periods: tuple[ConsolidatedForecastPeriod, ...]

    def __post_init__(self) -> None:
        for name in (
            "case_id", "version_id", "scenario_id", "economic_scope_id",
            "currency", "unit",
        ):
            _required(getattr(self, name), name)
        if self.legal_entity_id is not None:
            _required(self.legal_entity_id, "legal_entity_id")
        if not isinstance(self.version_type, VersionType) or self.version_type not in {
            VersionType.ANALYST_PLAN, VersionType.ANALYST_FORECAST, VersionType.SCENARIO
        }:
            raise ValueError("version_type must be an analyst plan, forecast or scenario")
        if not isinstance(self.scenario_purpose, ScenarioPurpose):
            raise TypeError("scenario_purpose must be ScenarioPurpose")
        if not isinstance(self.accounting_scope, AccountingScope):
            raise TypeError("accounting_scope must be AccountingScope")
        _date(self.opening_balance_date, "opening_balance_date")
        if not isinstance(self.opening, ConsolidatedBalanceSheet):
            raise TypeError("opening must be ConsolidatedBalanceSheet")
        object.__setattr__(
            self, "opening_evidence",
            _validated_evidence(self.opening_evidence, OPENING_FIELDS, "opening_evidence"),
        )
        _aware(self.information_cutoff, "information_cutoff")
        if not isinstance(self.periods, tuple) or not self.periods:
            raise ValueError("periods must be a nonempty tuple")
        if any(not isinstance(period, ConsolidatedForecastPeriod) for period in self.periods):
            raise TypeError("periods must contain only ConsolidatedForecastPeriod")


@dataclass(frozen=True, slots=True)
class ConsolidatedIncomeStatement:
    net_sales: Decimal
    other_revenue: Decimal
    total_revenue: Decimal
    cash_operating_expense: Decimal
    depreciation: Decimal
    operating_income: Decimal
    interest_expense: Decimal
    cash_other_income: Decimal
    tax_expense: Decimal
    net_income: Decimal


@dataclass(frozen=True, slots=True)
class ConsolidatedCashFlowStatement:
    opening_cash: Decimal
    operating: Decimal
    investing: Decimal
    financing: Decimal
    closing_cash: Decimal


@dataclass(frozen=True, slots=True)
class ConsolidatedStatementResult:
    income: ConsolidatedIncomeStatement
    cash_flow: ConsolidatedCashFlowStatement
    closing: ConsolidatedBalanceSheet
    balance_residual: Decimal
    cash_residual: Decimal
    debt_residual: Decimal
    tax_residual: Decimal
    ppe_residual: Decimal
    dividend_payable_residual: Decimal


def project_consolidated_statements(
    opening: ConsolidatedBalanceSheet, inputs: ConsolidatedPeriodInputs
) -> ConsolidatedStatementResult:
    """Project a period; all noncash effects must balance without a cash plug."""

    if opening.residual != 0:
        raise ValueError("opening balance sheet does not reconcile")
    if opening.cash < 0:
        raise ValueError("opening cash must be nonnegative")
    if inputs.depreciation > _exact_sum((
        opening.ppe_net, inputs.capex, inputs.ppe_noncash_change
    )):
        raise ValueError("depreciation exceeds available modeled PPE")
    debt_available = _exact_sum((
        opening.debt_carrying, inputs.debt_issuance,
        inputs.debt_carrying_noncash_change,
    ))
    if inputs.debt_repayment > debt_available:
        raise ValueError("debt repayment exceeds available carrying balance")
    if inputs.dividends_paid > _exact_sum((
        opening.dividends_payable, inputs.dividends_declared
    )):
        raise ValueError("dividends paid exceed payable and declared amount")

    total_revenue = _exact_sum((inputs.net_sales, inputs.other_revenue))
    operating_income = _exact_sum((
        total_revenue, inputs.cash_operating_expense.copy_negate(),
        inputs.depreciation.copy_negate(),
    ))
    net_income = _exact_sum((
        operating_income, inputs.interest_expense.copy_negate(),
        inputs.cash_other_income, inputs.tax_expense.copy_negate(),
    ))
    income = ConsolidatedIncomeStatement(
        net_sales=inputs.net_sales,
        other_revenue=inputs.other_revenue,
        total_revenue=total_revenue,
        cash_operating_expense=inputs.cash_operating_expense,
        depreciation=inputs.depreciation,
        operating_income=operating_income,
        interest_expense=inputs.interest_expense,
        cash_other_income=inputs.cash_other_income,
        tax_expense=inputs.tax_expense,
        net_income=net_income,
    )

    tax_payable = _exact_sum((
        opening.tax_payable, inputs.tax_expense,
        inputs.cash_taxes_paid.copy_negate(),
    ))
    if tax_payable < 0:
        raise ValueError("cash taxes exceed modeled tax payable and expense")
    debt_carrying = _exact_sum((
        opening.debt_carrying, inputs.debt_issuance,
        inputs.debt_repayment.copy_negate(), inputs.debt_carrying_noncash_change,
    ))
    dividends_payable = _exact_sum((
        opening.dividends_payable, inputs.dividends_declared,
        inputs.dividends_paid.copy_negate(),
    ))

    operating = _exact_sum((
        net_income, inputs.depreciation,
        opening.receivables, inputs.closing_receivables.copy_negate(),
        opening.inventory, inputs.closing_inventory.copy_negate(),
        opening.other_operating_assets,
        inputs.closing_other_operating_assets.copy_negate(),
        inputs.closing_payables, opening.payables.copy_negate(),
        inputs.closing_accrued_operating_liabilities,
        opening.accrued_operating_liabilities.copy_negate(),
        tax_payable, opening.tax_payable.copy_negate(),
        inputs.other_liabilities_operating_cash_change,
    ))
    investing = _exact_sum((
        inputs.capex.copy_negate(),
        inputs.other_long_lived_assets_investing_cash_change.copy_negate(),
    ))
    financing = _exact_sum((
        inputs.debt_issuance, inputs.debt_repayment.copy_negate(),
        inputs.other_liabilities_financing_cash_change,
        inputs.dividends_paid.copy_negate(),
        inputs.share_issuance, inputs.share_repurchases.copy_negate(),
    ))
    cash = projected_closing_cash(
        opening.cash, operating, investing, financing, Decimal(0)
    )
    closing = ConsolidatedBalanceSheet(
        cash=cash,
        receivables=inputs.closing_receivables,
        inventory=inputs.closing_inventory,
        other_operating_assets=inputs.closing_other_operating_assets,
        ppe_net=_exact_sum((
            opening.ppe_net, inputs.capex, inputs.depreciation.copy_negate(),
            inputs.ppe_noncash_change,
        )),
        other_long_lived_assets=_exact_sum((
            opening.other_long_lived_assets,
            inputs.other_long_lived_assets_investing_cash_change,
            inputs.other_long_lived_assets_noncash_change,
        )),
        payables=inputs.closing_payables,
        accrued_operating_liabilities=inputs.closing_accrued_operating_liabilities,
        tax_payable=tax_payable,
        debt_carrying=debt_carrying,
        dividends_payable=dividends_payable,
        other_liabilities=_exact_sum((
            opening.other_liabilities,
            inputs.other_liabilities_operating_cash_change,
            inputs.other_liabilities_financing_cash_change,
            inputs.other_liabilities_noncash_change,
        )),
        equity=_exact_sum((
            opening.equity, net_income, inputs.other_comprehensive_income,
            inputs.share_issuance, inputs.share_repurchases.copy_negate(),
            inputs.dividends_declared.copy_negate(),
        )),
    )
    cash_flow = ConsolidatedCashFlowStatement(
        opening_cash=opening.cash, operating=operating, investing=investing,
        financing=financing, closing_cash=cash,
    )
    return ConsolidatedStatementResult(
        income=income,
        cash_flow=cash_flow,
        closing=closing,
        balance_residual=closing.residual,
        cash_residual=cash_rollforward_residual(
            opening.cash, operating, investing, financing, Decimal(0), cash
        ),
        debt_residual=_exact_sum((
            opening.debt_carrying, inputs.debt_issuance,
            inputs.debt_repayment.copy_negate(),
            inputs.debt_carrying_noncash_change, debt_carrying.copy_negate(),
        )),
        tax_residual=_exact_sum((
            opening.tax_payable, inputs.tax_expense,
            inputs.cash_taxes_paid.copy_negate(), tax_payable.copy_negate(),
        )),
        ppe_residual=_exact_sum((
            opening.ppe_net, inputs.capex, inputs.depreciation.copy_negate(),
            inputs.ppe_noncash_change, closing.ppe_net.copy_negate(),
        )),
        dividend_payable_residual=_exact_sum((
            opening.dividends_payable, inputs.dividends_declared,
            inputs.dividends_paid.copy_negate(), dividends_payable.copy_negate(),
        )),
    )


@dataclass(frozen=True, slots=True)
class ConsolidatedForecastPeriodResult:
    period_id: str
    period_start: date
    period_end: date
    inputs: ConsolidatedPeriodInputs
    input_evidence: Mapping[str, ModelInputEvidence]
    result: ConsolidatedStatementResult


@dataclass(frozen=True, slots=True)
class ConsolidatedForecastPathResult:
    spec: ConsolidatedForecastSpec
    periods: tuple[ConsolidatedForecastPeriodResult, ...]
    content_sha256: str

    @property
    def closing(self) -> ConsolidatedBalanceSheet:
        return self.periods[-1].result.closing


def project_consolidated_path(
    spec: ConsolidatedForecastSpec,
) -> ConsolidatedForecastPathResult:
    """Project contiguous periods using only inputs known at the cutoff."""

    if not isinstance(spec, ConsolidatedForecastSpec):
        raise TypeError("spec must be ConsolidatedForecastSpec")
    if spec.opening.residual != 0:
        raise ValueError("opening balance sheet does not reconcile")
    late_opening = sorted(
        name for name, evidence in spec.opening_evidence.items()
        if evidence.available_at > spec.information_cutoff
    )
    if late_opening:
        raise ValueError(f"opening evidence unavailable at cutoff: {late_opening}")
    opening = spec.opening
    expected_start = spec.opening_balance_date + timedelta(days=1)
    seen: set[str] = set()
    projected: list[ConsolidatedForecastPeriodResult] = []
    for index, period in enumerate(spec.periods):
        if period.period_id in seen:
            raise ValueError(f"duplicate period_id: {period.period_id}")
        seen.add(period.period_id)
        if period.period_start != expected_start:
            raise ValueError(f"period {period.period_id} is not contiguous")
        full_fiscal_year = (period.period_end - period.period_start).days + 1 >= 360
        if full_fiscal_year and period.driver_inputs is not None and any((
            period.driver_inputs.fiscal_year_net_sales_to_date,
            period.driver_inputs.fiscal_year_other_revenue_to_date,
            period.driver_inputs.fiscal_year_capex_to_date,
        )):
            raise ValueError(
                f"period {period.period_id} full fiscal year cannot include prior YTD flows"
            )
        # A full subsequent fiscal year must use the immediately preceding
        # modeled fiscal year, including any actual YTD before a modeled stub,
        # as its comparable growth base. This prevents a hand-entered FY28
        # base from drifting away from the FY27 linked forecast.
        if (
            index > 0
            and period.driver_inputs is not None
            and spec.periods[index - 1].driver_inputs is not None
            and full_fiscal_year
        ):
            previous = spec.periods[index - 1]
            expected_net_sales, expected_other_revenue = projected_fiscal_revenue_basis(
                previous
            )
            if period.driver_inputs.comparable_prior_net_sales != expected_net_sales:
                raise ValueError(
                    f"period {period.period_id} comparable prior net sales do not "
                    "match the prior linked fiscal year"
                )
            if period.driver_inputs.comparable_prior_other_revenue != expected_other_revenue:
                raise ValueError(
                    f"period {period.period_id} comparable prior other revenue do not "
                    "match the prior linked fiscal year"
                )
        late = sorted(
            name for name, evidence in period.input_evidence.items()
            if evidence.available_at > spec.information_cutoff
        )
        if period.driver_evidence is not None:
            late.extend(
                f"driver:{name}" for name, evidence in period.driver_evidence.items()
                if evidence.available_at > spec.information_cutoff
            )
        if late:
            raise ValueError(f"period {period.period_id} input unavailable at cutoff: {late}")
        result = project_consolidated_statements(opening, period.inputs)
        if any((
            result.balance_residual, result.cash_residual, result.debt_residual,
            result.tax_residual, result.ppe_residual, result.dividend_payable_residual,
        )):
            raise ValueError(f"period {period.period_id} financial identities do not reconcile")
        projected.append(ConsolidatedForecastPeriodResult(
            period.period_id, period.period_start, period.period_end,
            period.inputs, period.input_evidence, result,
        ))
        opening = result.closing
        expected_start = period.period_end + timedelta(days=1)

    payload: dict[str, object] = {
        "schema_version": CONSOLIDATED_FORECAST_SCHEMA_VERSION,
        "case_id": spec.case_id,
        "version_id": spec.version_id,
        "version_type": spec.version_type.value,
        "scenario_id": spec.scenario_id,
        "scenario_purpose": spec.scenario_purpose.value,
        "accounting_scope": spec.accounting_scope.value,
        "economic_scope_id": spec.economic_scope_id,
        "legal_entity_id": spec.legal_entity_id,
        "currency": spec.currency,
        "unit": spec.unit,
        "opening_balance_date": spec.opening_balance_date.isoformat(),
        "opening": _decimal_record(spec.opening),
        "opening_evidence": {
            name: _evidence_record(spec.opening_evidence[name])
            for name in sorted(OPENING_FIELDS)
        },
        "information_cutoff": _utc(spec.information_cutoff),
        "periods": [
            {
                "period_id": period.period_id,
                "period_start": period.period_start.isoformat(),
                "period_end": period.period_end.isoformat(),
                "inputs": _decimal_record(period.inputs),
                "input_evidence": {
                    name: _evidence_record(period.input_evidence[name])
                    for name in sorted(PERIOD_FIELDS)
                },
                "driver_inputs": (
                    _decimal_record(period.driver_inputs)
                    if period.driver_inputs is not None else None
                ),
                "driver_evidence": (
                    {
                        name: _evidence_record(period.driver_evidence[name])
                        for name in sorted(DRIVER_FIELDS)
                    }
                    if period.driver_evidence is not None else None
                ),
                "income": _decimal_record(output.result.income),
                "cash_flow": _decimal_record(output.result.cash_flow),
                "closing": _decimal_record(output.result.closing),
                "residuals": {
                    "balance": str(output.result.balance_residual),
                    "cash": str(output.result.cash_residual),
                    "debt": str(output.result.debt_residual),
                    "tax": str(output.result.tax_residual),
                    "ppe": str(output.result.ppe_residual),
                    "dividends_payable": str(output.result.dividend_payable_residual),
                },
            }
            for period, output in zip(spec.periods, projected, strict=True)
        ],
    }
    digest = _hash("core_consolidated_path", payload).split("_", 3)[-1]
    return ConsolidatedForecastPathResult(spec, tuple(projected), digest)


def _baseline_ref(path: ConsolidatedForecastPathResult) -> OperatingBaselineRef:
    reproduced = project_consolidated_path(path.spec)
    if reproduced.content_sha256 != path.content_sha256 or reproduced.periods != path.periods:
        raise ValueError("consolidated path does not reproduce from retained Core inputs")
    spec = path.spec
    periods = tuple(
        OperatingBaselinePeriodRef(period.period_id, period.period_start, period.period_end)
        for period in path.periods
    )
    payload: dict[str, object] = {
        "schema_version": CONSOLIDATED_FORECAST_SCHEMA_VERSION,
        "case_id": spec.case_id,
        "version_id": spec.version_id,
        "scenario_id": spec.scenario_id,
        "accounting_scope": spec.accounting_scope.value,
        "economic_scope_id": spec.economic_scope_id,
        "legal_entity_id": spec.legal_entity_id,
        "currency": spec.currency,
        "unit": spec.unit,
        "information_cutoff": _utc(spec.information_cutoff),
        "model_path_sha256": path.content_sha256,
        "periods": [
            (period.period_id, period.period_start.isoformat(), period.period_end.isoformat())
            for period in periods
        ],
    }
    return OperatingBaselineRef(
        case_id=spec.case_id,
        version_id=spec.version_id,
        accounting_scope=spec.accounting_scope,
        economic_scope_id=spec.economic_scope_id,
        legal_entity_id=spec.legal_entity_id,
        currency=spec.currency,
        unit=spec.unit,
        information_cutoff=spec.information_cutoff,
        model_path_sha256=path.content_sha256,
        periods=periods,
        output_id=_hash("operating_baseline", payload),
    )


def unlevered_cash_taxes_from_ebit(
    path: ConsolidatedForecastPathResult,
    *,
    tax_rate: Decimal,
    evidence: ModelInputEvidence,
    method_id: str,
) -> tuple[UnleveredCashTaxInput, ...]:
    """An analyst EBIT×rate cash-tax proxy for positive-EBIT periods.

    This is a valuation assumption, never a reported cash-tax fact. It omits
    temporary differences, tax attributes and jurisdictional rate mix; a case
    must record those limitations and support the selected rate. Negative EBIT
    needs a separate tax-loss method rather than an automatic cash benefit.
    """

    _baseline_ref(path)
    if not isinstance(tax_rate, Decimal) or not tax_rate.is_finite():
        raise ValueError("tax_rate must be a finite Decimal")
    if not Decimal(0) <= tax_rate <= Decimal(1):
        raise ValueError("tax_rate must lie between zero and one")
    if not isinstance(evidence, ModelInputEvidence):
        raise TypeError("evidence must be ModelInputEvidence")
    if evidence.available_at > path.spec.information_cutoff:
        raise ValueError("tax-rate evidence unavailable at cutoff")
    _required(method_id, "method_id")
    taxes: list[UnleveredCashTaxInput] = []
    for period in path.periods:
        ebit = period.result.income.operating_income
        if ebit < 0:
            raise ValueError(
                f"negative EBIT needs a separate unlevered tax method: {period.period_id}"
            )
        taxes.append(UnleveredCashTaxInput(
            period_id=period.period_id,
            amount=_exact_product(ebit, tax_rate),
            tax_method_id=method_id,
            evidence=evidence,
        ))
    return tuple(taxes)


@dataclass(frozen=True, slots=True)
class ForecastCashComponent:
    """One signed amount with six explicit cash-view inclusion flags."""

    component_id: str
    amount: Decimal | KnowledgeState
    included_in_fcff: bool
    included_in_fcfe: bool
    included_in_cfads: bool
    included_in_debt_service: bool
    included_in_liquidity: bool
    included_in_sources_uses: bool

    def __post_init__(self) -> None:
        _required(self.component_id, "component_id")
        if isinstance(self.amount, Decimal):
            if not self.amount.is_finite():
                raise ValueError("cash component amount must be finite")
        elif self.amount is not KnowledgeState.UNKNOWN:
            raise ValueError("cash component amount must be Decimal or UNKNOWN")
        for name in (
            "included_in_fcff", "included_in_fcfe", "included_in_cfads",
            "included_in_debt_service", "included_in_liquidity",
            "included_in_sources_uses",
        ):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be a boolean")
        if self.included_in_cfads and self.included_in_debt_service:
            raise ValueError("one component cannot be CFADS and debt service")

    def includes(self, view: CashView) -> bool:
        return {
            CashView.FCFF: self.included_in_fcff,
            CashView.FCFE: self.included_in_fcfe,
            CashView.CFADS: self.included_in_cfads,
            CashView.DEBT_SERVICE: self.included_in_debt_service,
            CashView.LIQUIDITY: self.included_in_liquidity,
            CashView.SOURCES_USES: self.included_in_sources_uses,
        }[view]

    def as_dict(self) -> dict[str, object]:
        return {
            "component_id": self.component_id,
            "amount": (
                self.amount.value if isinstance(self.amount, KnowledgeState)
                else str(self.amount)
            ),
            "included_in_fcff": self.included_in_fcff,
            "included_in_fcfe": self.included_in_fcfe,
            "included_in_cfads": self.included_in_cfads,
            "included_in_debt_service": self.included_in_debt_service,
            "included_in_liquidity": self.included_in_liquidity,
            "included_in_sources_uses": self.included_in_sources_uses,
        }


@dataclass(frozen=True, slots=True)
class ForecastCashComponentAudit:
    period_id: str
    baseline_output_id: str
    fcff_output_id: str | None
    fcfe_output_id: str
    components: tuple[ForecastCashComponent, ...]
    totals: Mapping[CashView, Decimal | KnowledgeState]
    output_id: str

    def total_for(self, view: CashView) -> Decimal | KnowledgeState:
        return self.totals[view]

    def as_dict(self) -> dict[str, object]:
        return {
            "period_id": self.period_id,
            "baseline_output_id": self.baseline_output_id,
            "fcff_output_id": self.fcff_output_id,
            "fcfe_output_id": self.fcfe_output_id,
            "components": [component.as_dict() for component in self.components],
            "totals": {
                view.value: (
                    total.value if isinstance(total, KnowledgeState) else str(total)
                )
                for view, total in self.totals.items()
            },
            "output_id": self.output_id,
        }


def _component(
    component_id: str, amount: Decimal | KnowledgeState, *views: CashView
) -> ForecastCashComponent:
    if isinstance(amount, Decimal):
        if not amount.is_finite():
            raise ValueError(f"{component_id} must be finite")
    elif not isinstance(amount, KnowledgeState):
        raise TypeError(f"{component_id} amount must be Decimal or KnowledgeState")
    if len(set(views)) != len(views):
        raise ValueError(f"duplicate cash-view flag: {component_id}")
    return ForecastCashComponent(
        component_id, amount,
        CashView.FCFF in views, CashView.FCFE in views,
        CashView.CFADS in views, CashView.DEBT_SERVICE in views,
        CashView.LIQUIDITY in views, CashView.SOURCES_USES in views,
    )


def _cash_view_total(
    components: tuple[ForecastCashComponent, ...], view: CashView
) -> Decimal | KnowledgeState:
    included = tuple(item.amount for item in components if item.includes(view))
    if not included:
        return KnowledgeState.NOT_APPLICABLE
    if any(isinstance(value, KnowledgeState) for value in included):
        return KnowledgeState.UNKNOWN
    return _exact_sum(included)


def audit_consolidated_cash_components(
    path: ConsolidatedForecastPathResult,
    cash_flows: FreeCashFlowPathResult,
) -> tuple[ForecastCashComponentAudit, ...]:
    """Explain exact FCFF/FCFE inclusion and block duplicate view components.

    The other four views remain NOT_APPLICABLE until CFADS, debt service,
    liquidity or sources/uses receive separate case-supported definitions.
    A zero amount still receives an explicit flag and lineage to this baseline.
    """

    if not isinstance(path, ConsolidatedForecastPathResult):
        raise TypeError("path must be ConsolidatedForecastPathResult")
    if not isinstance(cash_flows, FreeCashFlowPathResult):
        raise TypeError("cash_flows must be FreeCashFlowPathResult")
    if cash_flows.baseline.model_path_sha256 != path.content_sha256:
        raise ValueError("cash flow and forecast baseline do not match")
    if len(cash_flows.periods) != len(path.periods):
        raise ValueError("cash flow and forecast periods do not match")
    audits: list[ForecastCashComponentAudit] = []
    for forecast, flow in zip(path.periods, cash_flows.periods, strict=True):
        if flow.period_id != forecast.period_id:
            raise ValueError("cash flow and forecast period IDs do not match")
        inputs = forecast.inputs
        statement = forecast.result
        expected_financing = _exact_sum((
            inputs.debt_issuance, inputs.debt_repayment.copy_negate(),
            inputs.other_liabilities_financing_cash_change,
        ))
        if any((
            flow.ebit != statement.income.operating_income,
            flow.depreciation != inputs.depreciation,
            flow.operating_cash_flow != statement.cash_flow.operating,
            flow.capital_expenditure != inputs.capex,
            flow.net_debt_financing != expected_financing,
        )):
            raise ValueError("cash-flow component values differ from Core statements")
        components = (
            _component("operating_income", flow.ebit, CashView.FCFF),
            _component("depreciation", flow.depreciation, CashView.FCFF),
            _component(
                "operating_working_capital", flow.change_in_operating_working_capital.copy_negate(),
                CashView.FCFF,
            ),
            _component("capital_expenditure", inputs.capex.copy_negate(), CashView.FCFF, CashView.FCFE),
            _component(
                "unlevered_cash_taxes",
                flow.unlevered_cash_taxes.copy_negate()
                if isinstance(flow.unlevered_cash_taxes, Decimal)
                else flow.unlevered_cash_taxes,
                CashView.FCFF,
            ),
            _component("operating_cash_flow", flow.operating_cash_flow, CashView.FCFE),
            _component(
                "other_long_lived_investing_cash",
                inputs.other_long_lived_assets_investing_cash_change.copy_negate(),
                CashView.FCFE,
            ),
            _component("net_debt_like_cash_financing", flow.net_debt_financing, CashView.FCFE),
        )
        if len({item.component_id for item in components}) != len(components):
            raise ValueError("duplicate cash component IDs")
        totals = MappingProxyType({
            view: _cash_view_total(components, view) for view in CashView
        })
        if totals[CashView.FCFF] != flow.fcff or totals[CashView.FCFE] != flow.fcfe:
            raise ValueError("cash component inclusion does not reconcile to FCFF/FCFE")
        payload: dict[str, object] = {
            "schema_version": CONSOLIDATED_CASH_FLOW_SCHEMA_VERSION,
            "period_id": flow.period_id,
            "baseline_output_id": cash_flows.baseline.output_id,
            "fcff_output_id": flow.fcff_output_id,
            "fcfe_output_id": flow.fcfe_output_id,
            "components": [item.as_dict() for item in components],
        }
        audits.append(ForecastCashComponentAudit(
            period_id=flow.period_id,
            baseline_output_id=cash_flows.baseline.output_id,
            fcff_output_id=flow.fcff_output_id,
            fcfe_output_id=flow.fcfe_output_id,
            components=components,
            totals=totals,
            output_id=_hash("core_cash_inclusion", payload),
        ))
    return tuple(audits)


def project_consolidated_free_cash_flow_path(
    path: ConsolidatedForecastPathResult,
    *,
    unlevered_cash_taxes: tuple[UnleveredCashTaxInput, ...] = (),
) -> FreeCashFlowPathResult:
    """FCFE and conditional FCFF from the reconciled consolidated Core path.

    FCFF excludes other long-lived assets and financing flows; their claim
    treatment belongs in the valuation bridge. Unlevered cash taxes require an
    evidenced case method. Missing tax evidence produces UNKNOWN, never zero.
    """

    if not isinstance(path, ConsolidatedForecastPathResult):
        raise TypeError("path must be ConsolidatedForecastPathResult")
    baseline = _baseline_ref(path)
    if not isinstance(unlevered_cash_taxes, tuple) or any(
        not isinstance(item, UnleveredCashTaxInput) for item in unlevered_cash_taxes
    ):
        raise TypeError("unlevered_cash_taxes must be UnleveredCashTaxInput tuples")
    valid = {period.period_id for period in path.periods}
    tax_by_period: dict[str, UnleveredCashTaxInput] = {}
    for tax in unlevered_cash_taxes:
        if tax.period_id not in valid:
            raise ValueError(f"unlevered tax period is absent from Core path: {tax.period_id}")
        if tax.period_id in tax_by_period:
            raise ValueError(f"duplicate unlevered tax period: {tax.period_id}")
        if tax.evidence.available_at > path.spec.information_cutoff:
            raise ValueError(f"unlevered tax evidence unavailable at cutoff: {tax.period_id}")
        tax_by_period[tax.period_id] = tax

    opening = path.spec.opening
    results: list[FreeCashFlowPeriod] = []
    for period in path.periods:
        inputs, statement = period.inputs, period.result
        change_nwc = _exact_sum((
            statement.closing.receivables, opening.receivables.copy_negate(),
            statement.closing.inventory, opening.inventory.copy_negate(),
            statement.closing.other_operating_assets,
            opening.other_operating_assets.copy_negate(),
            statement.closing.payables.copy_negate(), opening.payables,
            statement.closing.accrued_operating_liabilities.copy_negate(),
            opening.accrued_operating_liabilities,
            inputs.other_liabilities_operating_cash_change.copy_negate(),
        ))
        net_debt = _exact_sum((
            inputs.debt_issuance, inputs.debt_repayment.copy_negate(),
            inputs.other_liabilities_financing_cash_change,
        ))
        fcfe = _exact_sum((
            statement.cash_flow.operating, statement.cash_flow.investing, net_debt,
        ))
        if fcfe != _exact_sum((
            statement.closing.cash, opening.cash.copy_negate(),
            inputs.dividends_paid, inputs.share_repurchases,
            inputs.share_issuance.copy_negate(),
        )):
            raise ValueError(f"FCFE does not reconcile to cash and equity financing: {period.period_id}")
        common: dict[str, object] = {
            "schema_version": CONSOLIDATED_CASH_FLOW_SCHEMA_VERSION,
            "core_free_cash_flow_schema_version": FREE_CASH_FLOW_SCHEMA_VERSION,
            "baseline_output_id": baseline.output_id,
            "period_id": period.period_id,
            "period_start": period.period_start.isoformat(),
            "period_end": period.period_end.isoformat(),
            "currency": baseline.currency,
            "unit": baseline.unit,
        }
        fcfe_id = _hash("core_fcfe", {
            **common,
            "formula": "CFO + CFI + net debt-like cash financing",
            "operating_cash_flow": str(statement.cash_flow.operating),
            "investing_cash_flow": str(statement.cash_flow.investing),
            "net_debt_like_cash_financing": str(net_debt),
            "fcfe": str(fcfe),
        })
        tax = tax_by_period.get(period.period_id)
        if tax is None:
            unlevered_tax: Decimal | KnowledgeState = KnowledgeState.UNKNOWN
            fcff: Decimal | KnowledgeState = KnowledgeState.UNKNOWN
            fcff_id = None
        else:
            unlevered_tax = tax.amount
            fcff = _exact_sum((
                statement.income.operating_income, inputs.depreciation,
                change_nwc.copy_negate(), inputs.capex.copy_negate(),
                tax.amount.copy_negate(),
            ))
            fcff_id = _hash("core_fcff", {
                **common,
                "formula": "EBIT + depreciation - delta_operating_nwc - capex - unlevered_cash_taxes",
                "operating_income": str(statement.income.operating_income),
                "depreciation": str(inputs.depreciation),
                "change_in_operating_working_capital": str(change_nwc),
                "capex": str(inputs.capex),
                "unlevered_cash_taxes": str(tax.amount),
                "tax_method_id": tax.tax_method_id,
                "tax_evidence_id": tax.evidence.source_or_assumption_id,
                "tax_evidence_available_at": _utc(tax.evidence.available_at),
                "fcff": str(fcff),
            })
        results.append(FreeCashFlowPeriod(
            period_id=period.period_id,
            period_start=period.period_start,
            period_end=period.period_end,
            operating_cash_flow=statement.cash_flow.operating,
            capital_expenditure=inputs.capex,
            net_debt_financing=net_debt,
            dividends=inputs.dividends_paid,
            change_in_operating_working_capital=change_nwc,
            ebit=statement.income.operating_income,
            depreciation=inputs.depreciation,
            unlevered_cash_taxes=unlevered_tax,
            fcfe=fcfe,
            fcff=fcff,
            fcfe_output_id=fcfe_id,
            fcff_output_id=fcff_id,
        ))
        opening = statement.closing
    frozen = tuple(results)
    free_cash_flow_path = FreeCashFlowPathResult(
        baseline=baseline,
        periods=frozen,
        output_id=_hash("core_free_cash_flow_path", {
            "schema_version": CONSOLIDATED_CASH_FLOW_SCHEMA_VERSION,
            "baseline_output_id": baseline.output_id,
            "period_cash_flow_ids": [
                (period.fcfe_output_id, period.fcff_output_id) for period in frozen
            ],
        }),
    )
    audit_consolidated_cash_components(path, free_cash_flow_path)
    return free_cash_flow_path
