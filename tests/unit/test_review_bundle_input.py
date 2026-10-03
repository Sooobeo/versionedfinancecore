"""Malformed user-supplied manifests must produce controlled CLI errors."""

import json
from pathlib import Path

import pytest

from versioned_finance_core.cli import main
from versioned_finance_core.contracts.json_io import strict_json_loads
from versioned_finance_core.orchestration.case_build import verify_case_build


@pytest.mark.parametrize("number", ["1e309", "-1e9999", "NaN", "Infinity"])
def test_nonfinite_json_numbers_are_rejected_even_when_standard_notation(number: str) -> None:
    with pytest.raises(ValueError, match="Non-finite JSON numeric"):
        strict_json_loads('{"value": ' + number + '}')


@pytest.mark.parametrize("manifest", [
    [], None, {},
    {"case_id": []},
    {"case_id": "example", "cutoff_timestamp": None},
    {"case_id": "example", "cutoff_timestamp": "2026-01-01T00:00:00Z",
     "reproduction_command": 42},
    {"case_id": "example", "cutoff_timestamp": "2026-01-01T00:00:00Z",
     "reproduction_command": "rebuild", "review_state": "WITHHELD", "output_paths": [{}]},
])
def test_invalid_manifest_shape_is_rejected_before_file_access(
    tmp_path: Path, manifest: object, capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "release_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="Build manifest"):
        verify_case_build(tmp_path)
    assert main(["verify-build", str(tmp_path)]) == 2
    assert "ERROR: Build manifest" in capsys.readouterr().out
