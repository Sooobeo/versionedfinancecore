# Validation and handover

The evidence ledger contains one locator-only official SEC report receipt.
Run `python cases/standard_lithium_swa_2025dfs/07_validation_governance/reproduce_dfs.py`
from the repository root to regenerate the project-model arithmetic check.
The [case test](../../../tests/integration/test_swa_public_model.py) checks
the relative-period extractor on synthetic HTML, the `Decimal` model check,
source receipt lineage and the decision gate separation without network use.

Run `python -m pytest -q tests/integration/test_swa_public_model.py` and
`python -m pytest` for the full repository suite. Run `vfc validate-case
cases/standard_lithium_swa_2025dfs` in an editable install, or call
`versioned_finance_core.cli.main` with `src` on `PYTHONPATH`. The release-ready
check is expected to fail while M2, financial reconciliation, review and
reproduction handover gates remain `WITHHELD`.

The [review findings](review_findings.csv) list the required no-build cash
path, as-of remaining capex, funding/contract support, parent claim bridge
and independent challenge. The [draft manifest](../release/release_manifest.json)
retains null release and content hashes; it is not a published release.
