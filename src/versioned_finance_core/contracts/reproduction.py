"""Identity fields compared by automated handover, excluding run timestamps."""

REPRODUCTION_SCHEMA_VERSION = 1
REPRODUCTION_KIND = "AUTOMATED_REPRODUCTION_HANDOVER"
COMPARISON_FIELDS = (
    "schema_version", "contract_version", "program_id", "case_id", "release_id",
    "supersedes_release_id", "coverage_state", "review_state", "reproduction_command",
    "declared_limitations", "cutoff_timestamp", "source_snapshot_hash", "input_hash", "config_hash",
    "formula_or_code_hash", "output_hash", "memo_hash", "content_hash", "file_hashes",
    "output_paths", "memo_paths", "gate_results", "required_common_gates",
    "required_module_gates", "release_ready", "known_limitations", "publication_state",
)
