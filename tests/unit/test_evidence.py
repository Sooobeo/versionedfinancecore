from datetime import UTC, datetime
from pathlib import Path

import pytest

from versioned_finance_core.evidence import known_at_cutoff, sha256_file


def test_known_at_cutoff_requires_publication_by_cutoff() -> None:
    cutoff = datetime(2026, 1, 10, 9, 0, tzinfo=UTC)
    assert known_at_cutoff(datetime(2026, 1, 10, 8, 59, tzinfo=UTC), cutoff)
    assert not known_at_cutoff(datetime(2026, 1, 10, 9, 1, tzinfo=UTC), cutoff)
    assert not known_at_cutoff(None, cutoff)


def test_known_at_cutoff_rejects_naive_datetimes() -> None:
    with pytest.raises(ValueError):
        known_at_cutoff(
            datetime(2026, 1, 1),  # noqa: DTZ001 - deliberately naive input
            datetime(2026, 1, 2),  # noqa: DTZ001 - deliberately naive input
        )


def test_sha256_file(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_bytes(b"versioned-finance-core")
    assert sha256_file(source) == "e00d55176f5811452c3656bed61763b194f35e46283cce2da006b2bf64f54264"
