# Ford Credit pilot handover

1. Read [case charter](../00_charter/decision_object.md), [source notes](../01_evidence_core/evidence_notes.md) and [M3 memo](../05_m3_credit_liquidity_claims/credit_memo.md). The 2025 filing's report date and its public cutoff are distinct.
2. From the repository root, run the explicit SEC locator/hash verification only if network access is available:

   ```powershell
   $env:PYTHONPATH = 'src'
   python cases/ford_credit_2025ye_m3/01_evidence_core/ingest_sec_fmcc.py
   ```

   The script is idempotent for the pinned digests. It writes no raw HTML. If SEC bytes differ, stop and review a new source receipt/version rather than overwrite the old entry.
3. Rebuild Core offline into a new build root:

   ```powershell
   $env:PYTHONPATH = 'src'
   python -m versioned_finance_core build-core cases/ford_credit_2025ye_m3 --build-root build/ford_credit_replay
   ```

   Check cash identity output ID `cash_53d0fbaa0858b786e3977797a3dc31079a0f9610fbf06d40ec11e691b6c274af`, reported and calculated closing cash `9377` USD millions, and residual `0`.
4. Run `python -m versioned_finance_core validate-case cases/ford_credit_2025ye_m3 --release-ready`. Failure on the unresolved M3, review and legal-scope gates is expected. No publication is authorized by this pilot.
5. The separate [later-observation ledger](../out_of_time_evaluation/README.md) is outside the decision-input evidence directory and excluded from the 2026-02-11 cutoff. Do not use it to fill earlier unknowns.

Minimum next evidence: Ford Credit LLC parent-legal cash availability and debt assignment; dated 2026 principal and interest events; forecast receivable collections/originations and required cash floor; facility-specific eligible asset and covenant status; independent reviewer challenge.
