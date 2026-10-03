"""Render a review report without performing financial calculations."""

from __future__ import annotations


def render_case_review(report: dict[str, object]) -> str:
    lines = [
        f"# Case review: {report['case_id']}", "",
        "Publication state: WITHHELD", "",
        "Personal research.", "", str(report["review_note"]), "",
        f"Information cutoff: {report['analysis_cutoff']}", "",
        f"output_id: {report['output_id']}", "",
        "## Reproduced steps", "",
    ]
    for step in report["executed_steps"]:
        lines.append(f"- {step['step']}: {step['execution_state']}")
        for path in step["artifacts"]:
            lines.append(f"  - [{path}]({path.removeprefix('outputs/')})")
    if not report["executed_steps"]:
        lines.append("No calculation step is configured.")
    lines.extend(["", "## Remaining release blockers", ""])
    lines.extend(f"- {item}" for item in report["release_blockers"])
    lines.extend(["", "## Review findings", ""])
    for finding in report["review_findings"]:
        lines.append(
            f"- {finding.get('finding_id', '')} [{finding.get('status', '')}]: "
            f"{finding.get('finding', '')}"
        )
        if finding.get("remaining_limitation"):
            lines.append(f"  - {finding['remaining_limitation']}")
    if not report["review_findings"]:
        lines.append("No review finding rows are recorded; this does not establish review completion.")
    lines.extend(["", "## Reproduction", "", "```text", report["reproduction_command"], "```", ""])
    return "\n".join(lines)
