"""Human-readable scientific reports with explicit missingness and limits."""

from .contracts import ExperimentReport


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def render_report(report: ExperimentReport) -> str:
    """Render observed results without promoting harness evidence to fidelity evidence."""

    lines = [
        "# Blinded writing experiment",
        "",
        f"Status: **{report.status}**. Rated ballots: "
        f"{report.rated_ballots}/{report.expected_ballots}.",
        f"Baseline: `{_cell(report.baseline_arm)}`. "
        f"Manifest SHA-256: `{report.manifest_sha256}`.",
        "",
    ]
    if report.synthetic:
        lines.extend(["**Synthetic fixture: no real-person voice quality claim.**", ""])
    if report.results:
        lines.extend(
            [
                "| Arm | Author scope | Dimension | Cases / groups | Win | Tie | Loss | Preference (95% CI) |",
                "|---|---|---|---:|---:|---:|---:|---:|",
            ]
        )
        for row in report.results:
            interval = (
                "unavailable"
                if row.preference_ci95 is None
                else f"{row.preference_ci95[0]:.1%}-{row.preference_ci95[1]:.1%}"
            )
            lines.append(
                f"| {_cell(row.arm)} | {_cell(row.author_id or 'all supplied authors')} | "
                f"{_cell(row.dimension)} | {row.rated_cases} / {row.independent_groups} | "
                f"{row.win_rate:.1%} | {row.tie_rate:.1%} | {row.loss_rate:.1%} | "
                f"{row.preference_rate:.1%} ({interval}) |"
            )
    else:
        lines.append(
            "No human ratings were supplied. No quality scores or intervals were computed."
        )
    lines.extend(["", "## Interpretation limits", ""])
    lines.extend(f"- {limitation}" for limitation in report.limitations)
    return "\n".join(lines) + "\n"
