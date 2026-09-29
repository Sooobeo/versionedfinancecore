# Official-source extraction and limits

## Source vintage and rights

| Receipt | SEC locator | Filing date / acceptance shown by SEC | Conservative first-public bound | Use at 2026-02-11 cutoff |
|---|---|---|---|---|
| `sec_fmcc_2025_10k` | [2025 Form 10-K](https://www.sec.gov/Archives/edgar/data/38009/000003800926000010/fmcc-20251231.htm) | 2026-02-11 / 2026-02-10 19:15:16 | 2026-02-11 23:59:59 EST | eligible |
| `sec_fmcc_2026q2_10q` | [2026 Q2 Form 10-Q](https://www.sec.gov/Archives/edgar/data/38009/000003800926000041/fmcc-20260630.htm) | 2026-07-29 / 2026-07-28 19:31:29 | 2026-07-29 23:59:59 EDT | excluded; later observation |

SEC [10-K index](https://www.sec.gov/Archives/edgar/data/38009/000003800926000010/0000038009-26-000010-index.htm) and [10-Q index](https://www.sec.gov/Archives/edgar/data/38009/000003800926000041/0000038009-26-000041-index.htm) give filing and acceptance dates. Acceptance is not substituted for observed publication time. The last second of filing date is a conservative known-public-by bound, not a measured release second.

The source ledgers store URLs, document identifiers, retrieval times and SHA-256 of SEC HTML bytes. The 2026 10-Q receipt/facts are in [out_of_time_evaluation](../out_of_time_evaluation/README.md), separate from the 2025 decision-input ledger. We do not retain or redistribute the raw HTML because redistribution rights have not been established. The script `ingest_sec_fmcc.py` explicitly fetches the official pages to verify pinned hashes and writes only selected table cells. All transcribed cells remain pending independent review.

## 2025 10-K row locations

- Consolidated statement of cash flows, page 73: 2025 operating **3,846**, investing **−1,615**, financing **−2,495**, exchange effect **281**, opening cash/cash equivalents/restricted cash **9,360**, closing **9,377**, each in USD millions. These make a complete accounting cash identity; they do **not** supply CFADS.
- MD&A liquidity, page 47: cash **9.3**, committed asset-backed facilities **43.6**, other unsecured facilities **1.5**, restricted/securitization cash utilization **3.0**, asset-backed capacity utilization **26.4**, unsecured facility utilization **0.6**, other adjustments **0.2**, and net liquidity available for use **24.6**, each in USD billions. This is the company's **consolidated definition**, not legal-parent accessible cash.
- Note 9, pages 95–96: 2025-12-31 gross debt maturity categories total **141,904** USD millions, less unamortized costs/premium **247** and fair-value adjustments **240**, equal carrying debt **141,417**. The annual maturity columns are buckets, not exact payment dates. Note 9 separately lists long-term debt interest payments; we keep them distinct from principal.
- Note 9 and MD&A: asset-backed debt is an obligation of securitization entities payable from their collateral, not Ford Credit LLC or other subsidiaries. Receivables and cash in those structures cannot simply fund parent unsecured debt. Asset-backed facility use depends on eligible assets, certain hedges and asset-performance terms. FCE and Ford Bank facilities have different legal borrowers and covenants.

The 2026 10-Q later reports June 30 net available liquidity **27.4** USD billions and carrying debt **137,348** USD millions. Those observations do not update the 2025 balance or supply an ex-ante 2026 forecast.

## Independent arithmetic checks

All values below use decimal arithmetic and disclosed units:

- Cash: `9,360 + 3,846 − 1,615 − 2,495 + 281 = 9,377` USD millions.
- Group liquidity bridge: `9.3 + 43.6 + 1.5 − 3.0 − 26.4 − 0.6 + 0.2 = 24.6` USD billions.
- Debt carrying bridge: `82,410 unsecured + 59,494 asset-backed − 247 costs − 240 fair-value adjustment = 141,417` USD millions.

No 2026 funding surplus or shortfall follows from comparing the 2025 liquidity stock to 2026 annual principal maturities: receivable collections, originations, operating needs, facility draw conditions, entity restrictions and refinancing timing are required.
