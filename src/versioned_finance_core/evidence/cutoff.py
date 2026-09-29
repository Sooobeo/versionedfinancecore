from datetime import datetime


def known_at_cutoff(first_public_at: datetime | None, analysis_cutoff: datetime) -> bool:
    """Return whether a fact was public by the analysis cutoff."""

    if analysis_cutoff.tzinfo is None or analysis_cutoff.utcoffset() is None:
        raise ValueError("analysis_cutoff must be timezone-aware")
    if first_public_at is None:
        return False
    if first_public_at.tzinfo is None or first_public_at.utcoffset() is None:
        raise ValueError("first_public_at must be timezone-aware")
    return first_public_at <= analysis_cutoff

