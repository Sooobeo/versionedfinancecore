# Valuation method eligibility at the May 21, 2026 cutoff

`[JUDG]` Calculation and release eligibility are separate decisions. The [Core forecast](../02_financial_core/conditional_linked_forecast.json) provides linked statements, FCFF, FCFE, and cash-component IDs for the remaining FY27 period through FY31. The [M1 screen](conditional_valuation_screen.json) consumes those Core FCFF IDs for a nominal USD DCF and a partial claim bridge. Its `release_status` remains `WITHHELD`. The single analyst path was constructed retrospectively on October 1 and cannot serve as a contemporaneously frozen forecast or an out-of-time valuation backtest.

| Method | Calculation and release state | Remaining evidence |
|---|---|---|
| FCFF-WACC DCF | Conditional arithmetic screen; `WITHHELD` | Core FCFF and nominal WACC have matching claims. Unlevered cash tax is a proxy. Lease and D&A classification, the May 1-20 cash-flow stub, market-input availability, sustainable terminal reinvestment, and a complete enterprise-to-equity bridge remain unverified. |
| FCFE-cost-of-equity DCF | Core FCFE path only; `WITHHELD` | No eligible equity DCF establishes accessible shareholder cash, financing and lease treatment, current share count, and cost of equity. The [FY26 10-K](https://www.sec.gov/Archives/edgar/data/104169/000010416926000055/wmt-20260131.htm) describes restrictions on transferring some international cash to the United States. |
| Trading comparables | Not run; `WITHHELD` | No reviewed peer inclusion and exclusion record or aligned operating, lease, period, and claim definitions. |
| Dividend discount | Not run; `WITHHELD` | Dividends alone do not establish all shareholder returns, including repurchases, or a sustainable payment path. |

## Interpretation of the FCFF-WACC screen

The [assumption locators](../01_evidence_core/assumption_evidence.csv) distinguish observation dates from first-public times for the historical WMT close, Treasury yield, April bond spread, NYU equity risk premium and sector betas, and March 10-K share count. The historical price was retrieved retrospectively. The NYU values are author estimates, and their first-public times and usage rights are not independently pinned. March shares and April carrying debt and leases are stale against the May 21 valuation date. This WACC is a screening proxy, including an analyst sector-beta choice rather than a measured Walmart beta.

The terminal screen derives next-period FCFF from NOPAT less `g/ROIC` reinvestment. Its `final_core_fcff_output_id`, `transition_difference`, and `transition_ratio` expose a step to next-year terminal FCFF of about 1.77 times the final Core FCFF. A sustainable bridge for that step has not been established. Long-run growth, ROIC, and cash tax are analyst assumptions. The [March 2026 FOMC projections](https://www.federalreserve.gov/monetarypolicy/fomcprojtabl20260318.htm) give macro context, not evidence of Walmart's sustainable incremental ROIC or growth. No price-based switching value is eligible before a dated market-value and claim reconciliation.

The DCF valuation date is May 21 while its first Core FCFF period runs from May 1, 2026 to January 31, 2027. `ACT_365_FIXED` discounts period-end flows but does not isolate the 20 days of possible realized cash before valuation. The partial bridge uses April 30 debt, finance leases, and both forms of noncontrolling interest. Excess cash, nonoperating assets, and other senior claims remain `UNKNOWN`; its known subtotal is not equity value and `equity_value=None`. Operating and finance lease expense, FCFF, WACC, and debt-like claim policies also require one consistent treatment.

The screen therefore cannot become a released value range, price target, or buy/sell conclusion. See the [gates](../07_validation_governance/gate_results.csv) and [open findings](../07_validation_governance/review_findings.csv).
