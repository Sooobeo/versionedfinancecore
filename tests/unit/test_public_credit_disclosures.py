"""Synthetic arithmetic fixtures; not evidence about any actual issuer."""

from dataclasses import replace
from datetime import date
from decimal import Decimal, localcontext

import pytest

from versioned_finance_core.contracts import KnowledgeState
from versioned_finance_core.modules.m3.public_disclosures import (
    PublicCreditFact,
    audit_nominal_capacity,
    audit_public_credit_disclosures,
)

D = Decimal
AS_OF = date(2025, 12, 31)


def fact(metric, value, *, unit="USD", start=AS_OF, end=AS_OF, kind="INSTANT"):
    return PublicCreditFact(metric, metric, D(value), "USD", unit,
                            ("SYNTHETIC_TEST",), start, end, kind)


def test_disclosure_audit_known_answer_and_missing_never_zero():
    entries = [fact("debt_gross_principal", "100"),
               fact("debt_unamortized_cost_adjustment", "-2"),
               fact("debt_fair_value_adjustment", "3"), fact("debt_carrying_amount", "101")]
    result = audit_public_credit_disclosures(entries, balance_date=AS_OF)
    assert result[2]["state"] == "PASS"
    assert result[2]["calculated_value"] == "101"
    assert result[0]["state"] == "NOT_TESTABLE_FROM_PUBLIC_DATA"
    assert result[0]["residual"] == "UNKNOWN"
    entries[-1] = replace(entries[-1], value=D("102"))
    assert audit_public_credit_disclosures(entries, balance_date=AS_OF)[2]["residual"] == "-1"


def test_duplicate_and_scope_mismatch_are_rejected():
    entry = fact("debt_gross_principal", "100")
    with pytest.raises(ValueError, match="Duplicate"):
        audit_public_credit_disclosures([entry, entry], balance_date=AS_OF)
    with pytest.raises(ValueError, match="unit mismatch"):
        audit_public_credit_disclosures([
            entry, fact("debt_carrying_amount", "100", unit="USD_MILLION"),
        ], balance_date=AS_OF)


def test_overlapping_or_historical_maturity_buckets_rejected():
    entry = fact("maturity_unsecured_principal", "100", kind="MATURITY_BUCKET")
    with pytest.raises(ValueError, match="nonoverlapping"):
        audit_public_credit_disclosures([entry], balance_date=AS_OF)


def test_unknown_and_large_nominal_capacity_do_not_create_drawable_cash():
    unknown = audit_nominal_capacity(commitment=D("100"), drawn=KnowledgeState.UNKNOWN,
                                     disclosed_undrawn=D("90"))
    assert unknown["state"] == "NOT_TESTABLE_FROM_PUBLIC_DATA"
    assert unknown["drawable_amount"] == "UNKNOWN"
    with localcontext() as context:
        context.prec = 3
        result = audit_nominal_capacity(commitment=D("100000000000000000000000.01"),
                                       drawn=D(".01"),
                                       disclosed_undrawn=D("100000000000000000000000"))
    assert result == {"state": "PASS", "residual": "0.00", "drawable_amount": "UNKNOWN"}


@pytest.mark.parametrize("invalid", ["-1", "NaN", "Infinity"])
def test_invalid_nominal_capacity_rejected(invalid):
    with pytest.raises(ValueError, match="finite and nonnegative"):
        audit_nominal_capacity(commitment=D(invalid), drawn=D(0), disclosed_undrawn=D(0))


def test_binary_float_and_negative_maturity_rejected():
    with pytest.raises(TypeError, match="Decimal"):
        audit_nominal_capacity(commitment=1.5, drawn=D(0), disclosed_undrawn=D(0))
    negative = fact("maturity_unsecured_principal", "-1", start=date(2026, 1, 1),
                    end=date(2026, 12, 31), kind="MATURITY_BUCKET")
    with pytest.raises(ValueError, match="cannot be negative"):
        audit_public_credit_disclosures([negative], balance_date=AS_OF)
