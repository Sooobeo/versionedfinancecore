# South West Arkansas DFS: M2 feasibility memo

**Status:** `FEASIBILITY_ONLY`; `M2_CAPITAL_ALLOCATION = WITHHELD` at the
2025-10-15 23:59:59 ET cutoff. This is a personal research reconstruction,
not Standard Lithium's decision, an investment recommendation, or approval of
capital or financing.

## Decision and claim boundary

The proposed comparison is **build the DFS project minus keep the project
rights without building**, using incremental post-tax cash flows at the same
100% South West Arkansas project scope. The option-world forecast is disclosed
in [the SEC-filed NI 43-101 DFS, Section 22.4, Table 22-2](https://www.sec.gov/Archives/edgar/data/1537137/000110465925099044/tm2528539d1_ex99-1.htm).
The no-build/hold cash path is incomplete. The reported build NPV therefore
cannot be labeled incremental NPV or a go decision.

The model is **100% project, unlevered, real 2025 USD millions**. SWA Lithium
LLC is the operating entity; Standard Lithium and Equinor hold 55% and 45%
JV interests, respectively. Neither 55% of project NPV nor 100% of project
FCFF is demonstrated to be distributable Standard Lithium cash. A parent
value/financing decision needs a legal and financial bridge that is absent.

## What the public model supports

The report states `[F]` post-tax project NPV at 8% of **USD 1,275.0 million**
and IRR of **18.2%**. These are the author's forecast outputs, not measured
returns. Table 22-2 provides relative years `-4,-3,-2,-1,1..20`. The `-4`
cash cell is a dash (`UNKNOWN`); the remaining 23 rounded post-tax FCFF cells
sum to **USD 4,701.5 million** `[D]`, equal to the displayed total `[F]`.
No relative year is mapped to a calendar year or to the case cutoff.

The independent `Decimal` check in
[`dfs_reproduction.json`](dfs_reproduction.json) discounts the rounded annual
cash row at 8% under three timing assumptions: beginning of period
**1,324.786**, middle **1,274.775**, and end **1,226.653** USD millions
`[D]`. The middle-period hypothesis is **USD 0.225 million below** the filed
1,275.0. A maximum USD 0.05 million rounding error per displayed cash cell
could move that middle-period sum by about **USD 0.539 million**. The root of
the rounded annual row is **18.2026453%** `[D]`, which displays as 18.2%.
The report says cash flows are discounted to the start of project execution,
but the exact intra-year convention and unrounded annual cash flows are not
disclosed. Middle-period timing is therefore an inference compatible with the
reported result, **not** a verified replication of the report's internal
model. The beginning/end values illustrate the material timing ambiguity.

## Missing option and execution evidence

1. **Status quo:** Section 4 reports USD 1 million annual TETRA lease
   maintenance and a 2.5% gross lithium revenue override. It does not give a
   complete no-build/hold, abandonment, grant clawback, opportunity-cost or
   rights-expiry cash path. Zero would be an unsupported substitution.
2. **As-of investment:** Relative construction periods do not identify the
   project cash already spent by the cutoff, remaining capex, cancellation
   commitments, or the actual FID and commissioning dates. Past expenditures
   would be sunk at an as-of FID; only future incremental amounts belong in
   that decision. The filed whole-project NPV does not make this adjustment.
3. **Financing and contract capacity:** Section 22.3 assumes 100% equity
   funding and excludes debt financing charges. It states there are no binding
   contractual arrangements in its cost model. Section 1.19 still calls for
   further surface rights, engineering, permitting, and limited-notice work.
   A sources/uses schedule, funding commitments, accessible cash, financing
   terms, and executable contract schedule are not substantiated here.
4. **Scenarios:** The constant USD 22,400/t LCE price is a DFS model
   assumption, not a signed offtake price. Without a complete status quo and
   as-of capital schedule, downside, cash trough, break-even price and
   switching value cannot be responsibly turned into a corporate decision.

The strongest challenge to interpreting the published positive NPV as an
investment case is that it measures the report's entire forecast build path
under its assumed price, costs and timing. It does not measure the incremental
choice available at the cutoff or the equity/funding claim Standard Lithium
could execute. The alternative value could differ materially once real
remaining capex, holding costs and legal/funding terms are known.

**Conditional conclusion:** The official annual project model passes a
bounded arithmetic and lineage check. The same-scope build-minus-no-build
NPV, corporate cash trough, financing feasibility, and FID recommendation are
`WITHHELD`. The open evidence and review gates are recorded in
[`review_findings.csv`](../07_validation_governance/review_findings.csv) and
[`gate_results.csv`](../07_validation_governance/gate_results.csv).

## Reproduction

Run `python cases/standard_lithium_swa_2025dfs/07_validation_governance/reproduce_dfs.py`
to regenerate the independent arithmetic JSON from the transcribed model
row. [`extract_dfs.py`](../01_evidence_core/extract_dfs.py) can parse a locally
obtained copy of the SEC filing; the source HTML is not retained or committed.
The source locator, acceptance timestamp, rights treatment and digest are in
[`dfs_evidence.md`](../01_evidence_core/dfs_evidence.md). This arithmetic
check intentionally does not call the canonical dated M2 evaluator: the DFS
only discloses relative periods, so a real date would be invented.
