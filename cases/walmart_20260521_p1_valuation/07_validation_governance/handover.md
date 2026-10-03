# Walmart P1 conditional model reproduction and review handover

**Scope:** Three SEC documents support 205 normalized consolidated facts at the May 21, 2026, 23:59:59 EDT cutoff. The original 161 facts and a later retrieval vintage with 44 additional Q1 balance-sheet facts remain distinct. The [Core forecast](../02_financial_core/conditional_linked_forecast.json) links the April 30 opening balance sheet to remaining FY27 through FY31 income statements, balance sheets, cash flows, FCFF, and FCFE. The [M1 screen](../03_m1_operating_forecast_valuation/conditional_valuation_screen.json) shows conditional WACC, terminal, dated DCF, and a partial claim bridge. The scenario was constructed retrospectively on October 1 and is not a May 21 frozen analyst forecast. Release and investment decisions remain `WITHHELD`.

## Local reproduction

Run from the repository root. Use a fresh staging directory. Neither `build/` nor the case review JSON files are immutable publications.

```powershell
$env:PYTHONPATH = 'src'
python -m versioned_finance_core validate-case cases/walmart_20260521_p1_valuation
$wmtP1Root = "build/walmart_p1_recheck_$([guid]::NewGuid().ToString('N'))"
python -m versioned_finance_core build-core cases/walmart_20260521_p1_valuation --build-root $wmtP1Root
$wmtP1CoreDir = (Get-ChildItem "$wmtP1Root/walmart_20260521_p1_valuation" -Directory | Select-Object -First 1).FullName
python cases/walmart_20260521_p1_valuation/02_financial_core/check_reported_statements.py --normalized-actuals "$wmtP1CoreDir/normalized_actuals.csv" --output "$wmtP1Root/reported_statement_checks.json"
python cases/walmart_20260521_p1_valuation/02_financial_core/build_conditional_model.py --normalized-actuals "$wmtP1CoreDir/normalized_actuals.csv" --output-dir "$wmtP1Root/conditional_review"
```

The new Core `normalized_actuals.csv` should contain 205 facts. The FY26 cash and restricted-cash identity and the original reported income and balance-sheet checks should have zero residual. April 2026 detailed assets, current liabilities, and total liabilities plus equity also reconcile to disclosed totals. Compare the new conditional JSON period identity residuals, cash-component audit IDs, Core path and FCFF IDs with the case review artifacts. The M1 DCF must consume that same Core FCFF path ID.

The [config](../02_financial_core/conditional_model_config.json) records values, IDs, and rationales for the retrospective assumptions. The [assumption locators](../01_evidence_core/assumption_evidence.csv) distinguish observations from first-public timestamps. Several market timestamps and usage rights are unverified, so those observations cannot become approved release facts. The original `ingest_sec_financials.py` pins the initial SEC body digest and may fail against a new SEC transport response. The [Q1 supplement ingestion](../01_evidence_core/ingest_sec_q1_balance_supplement.py) checks the new canonical digest and all 78 prior Q1 values before adding only missing balance-sheet lines. Live network access is not a default test dependency.

## Conditions before release

1. Verify as-of availability and rights for the price, Treasury, ERP, and beta observations. Reconcile March shares and April book debt and leases to the May 21 market-weight and claim date.
2. Set one consistent policy for operating and finance lease expense, assets, liabilities, cash payments, FCFF, WACC, and the bridge. Review the proxy that treats total D&A as PPE depreciation and the other asset and noncash movements.
3. The first Core period begins May 1 but the valuation date is May 21. Separate the possible realized May 1-20 cash flow and align opening claims to the valuation date.
4. Support jurisdictional cash tax, sustainable terminal growth, incremental ROIC and reinvestment. The terminal artifact reports `final_core_fcff_output_id`, `transition_difference`, and `transition_ratio`; explain the roughly 1.77 times step from final Core FCFF to terminal next-year FCFF before release. Resolve excess cash, nonoperating assets, and other senior claims while preserving missing claims as unknown. The current bridge must retain `equity_value=None`.
5. Establish a contemporaneously frozen analyst forecast, a defensible downside, price-based sensitivity, and a prespecified out-of-time assessment. The user reported reviewing earlier material, but no independent named, dated challenge, response, and retest for this conditional model is recorded.

Run `python -m pytest`, `python -m compileall -q src`, and `python -m ruff check src tests`. A failure from `validate-case --release-ready` on the documented blocking gates is the correct current result. Add revised sources as new vintages and any eligible publication as a new immutable release ID.
