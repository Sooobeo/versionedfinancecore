# DFS evidence and publication boundaries

The sole core receipt is [Standard Lithium's SEC 6-K Exhibit 99.1](https://www.sec.gov/Archives/edgar/data/1537137/000110465925099044/tm2528539d1_ex99-1.htm), accession `0001104659-25-099044`. The [SEC filing header](https://www.sec.gov/Archives/edgar/data/1537137/000110465925099044/0001104659-25-099044-index-headers.html) records acceptance at **2025-10-14 08:42:38 ET**. The technical report's **2025-09-03 effective date is not its detailed model's public availability date**. Because the header gives an acceptance time and not a separate dissemination time, `first_public_at` in the ledger is a conservative known-public-by bound at 2025-10-14 23:59:59 ET. The case cutoff is the following day.

The source ledger records the URL, accession, UTC-offset timestamps, scope and SHA-256 `9d20587f998e240be98cde7327257ab990f67b3007e9a3e7702fa1db31a67c53`. The complete report is not stored in this repository. Its important notice says third-party reliance is at the third party's risk; [SEC guidance](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data) also requires fair scripted access. Only selected model values and citation locators are kept.

## Source meaning

- Section 1.1 identifies SWA Lithium LLC as project operator and the 55%/45% JV ownership. Section 4 describes brine rights assigned to the LLC and a TETRA override plus annual lease maintenance. These facts do not show unrestricted cash transfers to either parent.
- Section 22.3 says project capex is modeled with 100% equity funding, no project-debt financing cost and no binding contractual arrangements. Its assumed LCE price is USD 22,400 per tonne. The tax and working-capital estimates are project model inputs.
- Section 22.4, Tables 22-1 and 22-2 disclose model output in **real 2025 USD millions**: 100% project post-tax NPV at 8% of USD 1,275.0 million, IRR 18.2%, and 23 numeric relative-period post-tax unlevered cash-flow values summing to USD 4,701.5 million. These are **forecasts** and not historical receipts or Standard Lithium's net equity value.
- Section 1.19 recommends moving toward execution while listing further surface rights, data, engineering, permitting and limited-notice activities. This report recommendation is not a verified FID or project-financing closing.

`extract_dfs.py` reads the official Table 22-2 HTML without network access or date conversion. The relative-period values in `dfs_project_model.csv` are tagged `[A]` as forecast inputs. `dfs_reproduction.json` identifies the published figures `[F]` as statements *in the filing* and separately labels our arithmetic `[D]`.

The extractor was also run manually on a fresh in-memory download of the SEC HTML. Its SHA-256 matched the ledger, it returned 24 relative periods, and every numeric post-tax FCFF cell matched `dfs_project_model.csv`; the first period's en dash was retained as `UNKNOWN`. This live check is not a test-suite dependency, and no report bytes were written to the repository.
