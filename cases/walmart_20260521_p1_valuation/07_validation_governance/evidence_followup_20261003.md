# Walmart P1 official-source evidence follow-up — 2026-10-03

**Status: IMPLEMENTED_DIAGNOSTIC_ONLY.** This note records an official-source
check for material public no later than the case cutoff, 2026-05-21 23:59:59
EDT, and the limited v2 conditional-model controls built from it. A fifth,
locator-only FY26 10-K HTML receipt and 12 corresponding
`assumption_evidence.csv` rows were appended. The 205 Core raw/normalized facts
were not changed, no forward cash-flow assumption was added, and no gate was
promoted.

The case remains `FEASIBILITY_ONLY`; the conditional model and M1 valuation
remain `WITHHELD`.

## Implemented diagnostic boundary

- `conditional_model_config.json` is the explicitly revised v2 scenario. The
  prior v1 configuration is retained byte-for-byte as
  `conditional_model_config_v1.json`; it is a provenance snapshot, not a
  runnable input to the current schema-v2 adapter.
- The historical lease/cash-tax diagnostic validates each configured amount
  against its locator's observed value, unit, period, source receipt, and
  pre-cutoff publication time. It does not turn these observations into a
  forward lease cash flow or a forward FCFF cash-tax rate.
- The dated-stub boundary preserves conditional DCF arithmetic for diagnosis
  but gives `release_consumable_enterprise_value=None` and `WITHHELD` when the
  May 1–20 realized flow is `UNKNOWN`.

## What the official filings establish

### Lease classification and historical cash movements

Walmart's [FY26 Form 10-K](https://www.sec.gov/Archives/edgar/data/104169/000010416926000055/wmt-20260131.htm),
filed March 13, 2026, Note 6, separates FY26 operating lease cost (USD 2,434m),
finance-lease right-of-use asset amortization (USD 888m), finance-lease interest
(USD 383m), and variable lease cost (USD 1,180m). The same note reports cash
flows from operating leases (USD 2,315m), operating cash flows from finance
leases (USD 377m), financing cash flows from finance leases (USD 891m), and a
future undiscounted-obligation schedule.

The same FY26 filing's Consolidated Statements of Income separately reports
finance-lease interest of USD 481m. The diagnostic records the USD 98m
difference from Note 6's USD 383m as
`lease_note_to_income_statement_interest_bridge_unresolved`; it does not infer
or book a reconciliation adjustment.

The [May 21 FY27 Q1 Exhibit 99.1](https://www.sec.gov/Archives/edgar/data/104169/000010416926000095/earningsreleasefy27q1.htm)
adds April 30 balance-sheet amounts, including operating and finance lease
right-of-use assets and current/long-term lease obligations. It does not provide
a Q1 lease-cost, lease-cash-flow, or future-lease-addition schedule.

**Implication:** these sources support a future, separately mapped historical
lease schedule. They demonstrate why treating total D&A as PPE depreciation and
holding all lease assets/liabilities/cash flows static is not an evidenced
economic policy. They do not determine a May 21-to-FY31 lease forecast, a
consistent FCFF/WACC/bridge convention, or a release-grade lease treatment.
`LEASE_CASHFLOW_CLAIM_ALIGNMENT` remains `WITHHELD`.

### Cash taxes are not the same as the effective-tax-rate proxy

The FY26 10-K reports total income-tax provision of USD 7,199m and total cash
taxes paid of USD 5,364m. The May 21 Exhibit gives FY27 **effective tax-rate**
guidance of approximately 23.5%–24.5%, not jurisdictional cash taxes or an
unlevered marginal cash-tax schedule.

**Implication:** the disclosed historical difference confirms that the model's
`EBIT × 24%` unlevered-cash-tax input is a screening proxy, not evidence that
cash taxes equal provision. It cannot be relabeled as a validated FCFF input or
used to pass `FINANCIAL_RECONCILIATION` or `TERMINAL_SUSTAINABILITY`.

### Dated debt information is a proxy, not the May 21 marginal borrowing cost

Walmart's [April 2026 final term sheet](https://www.sec.gov/Archives/edgar/data/104169/000119312526183374/d145944dfwp.htm)
was public before the cutoff. For the 2036 notes it reports a 43bp spread to the
named benchmark Treasury and a 4.758% issue yield. It supports the provenance of
the v2 direct pre-tax debt-rate input only as an April issue-date proxy.

**Implication:** it is not a May 21 secondary-market yield or a fully aligned
market debt value, and therefore is not a current marginal borrowing cost. It
cannot by itself resolve the WACC or dated EV-to-equity bridge finding.

## What the official sources do not establish

1. The Q1 source ends on April 30. No official pre-cutoff disclosure located in
   this review observes or allocates cash flow from May 1 through May 20. A
   May 21 DCF must not treat that pre-valuation interval as an undisclosed
   realized amount or silently discount it as a post-valuation flow.
   `DCF_STUB_TIMING` remains `WITHHELD`.
2. The official April 30 balance sheet is useful for dated book claims, but it
   does not supply May 21 excess cash, non-operating assets, all senior claims,
   a spot share count, or market-value debt. The partial bridge must retain
   unknown components and `equity_value=None`.
3. The [Treasury daily par-yield page](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?field_tdr_date_value_month=202605&type=daily_treasury_yield_curve)
   is an official locator for the dated curve observation, but this retrospective
   page does not independently establish the row's first-public timestamp at the
   case cutoff. It also reports a par yield rather than the exact zero/discount
   curve. The existing market-input record therefore remains appropriately
   `PUBLICATION_TIME_UNVERIFIED`.
4. No official primary source in this review supplies a rights-cleared,
   contemporaneously pinned May 21 WMT close, a company-specific beta, or a
   market ERP. Nasdaq and NYU observations remain locator-only screening inputs;
   they are not upgraded to core facts.
5. The [March 2026 FOMC projections](https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20260318.htm)
   are public macro context, not Walmart-specific evidence of terminal growth,
   incremental ROIC, reinvestment, or cash tax. They cannot justify the current
   material terminal FCFF transition.

## Remaining evidence and modeling tasks

- Build a forward lease/ROU/liability/cash schedule only from separately
  sourced periods and a declared convention; the new historical diagnostic is
  not that schedule.
- If a release-grade market-price or beta source is later available, record its
  rights, exact public-availability timestamp, observation date, and permitted
  transformation/redistribution scope before using it.
- Resolve the stub through an explicitly sourced period model. A mechanical
  May 1–20 allocation would be an assumption, not a public actual, and cannot
  independently pass the gate.
