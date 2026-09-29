# Limited M1 case handover

1. From the repository root, run `python -m versioned_finance_core validate-case cases/walmart_fy27q1_guidance_outcome` with `PYTHONPATH=src` when the package is not installed. This checks case structure and evidence lineage.
2. Run `python cases/walmart_fy27q1_guidance_outcome/reproduce_comparison.py`. Compare its JSON to `03_m1_operating_forecast_valuation/guidance_range_comparison.json`. The script re-normalizes the three raw facts through `financial_core` and rejects a changed pinned `normalized_actuals.csv`.
3. Run `python -m pytest tests/integration/test_walmart_guidance_outcome.py -q`. This checks expected range distances, no February look-ahead and `WITHHELD` state without live network access.

The source ledger pins three company PDF byte hashes and SEC accessions. The original PDFs are not stored. To audit a changed source, download it for permitted personal inspection, hash its bytes, and add a **new** ledger receipt; do not replace the existing receipt or fact. Reconfirm the company's terms, metric definition, source publication time and cutoff before producing a new version.

If the company amends FY27 Q1 or a source URL changes content, preserve these `FILED` facts and create an append-only revised version. Recompute comparison under a new analysis cutoff; never replace the February guidance with May actual or with hindsight assumptions. A future full M1 release additionally requires a linked financial model, attributable driver variance, forecast/reforecast evidence, independent human challenge and gate review. This limited case is not eligible for `publish-release`.
