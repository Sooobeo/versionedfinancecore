"""Display only: no financial formula or source parsing in the handover memo."""

from __future__ import annotations


def render_reproduction(report: dict[str, object]) -> str:
    lines = [
        f"# Automated handover: {report['case_id']}", "",
        f"output_id: {report['output_id']}", "",
        f"Information cutoff: {report['analysis_cutoff']}", "",
        f"Automated reproduction: {report['automated_reproduction_state']}", "",
        f"Independent human review: {report['human_review_state']}", "",
        f"Publication state: {report['publication_state']}", "",
        f"- [First review memo]({report['first_stage']}/outputs/review_memo.md)",
        f"- [Second review memo]({report['second_stage']}/outputs/review_memo.md)",
        "", "## What this verifies", "",
    ]
    lines.extend(f"- {field}" for field in report["compared_fields"])
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.extend(["", "## Remaining release blockers", ""])
    lines.extend(f"- {item}" for item in report["remaining_release_blockers"])
    return "\n".join(lines) + "\n"
