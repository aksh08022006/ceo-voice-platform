"""Deterministic human-readable rendering of machine evaluation reports."""

from .contracts import EvaluationReport


def render_evaluation_report(report: EvaluationReport) -> str:
    lines = [
        f"# Evaluation {report.report_id}",
        "",
        f"Status: {report.status.value}",
        f"Overall score: {report.overall_score:.3f}",
        f"Candidate: {report.candidate_id}",
        "",
        "## Dimensions",
        "",
    ]
    lines.extend(
        f"- {item.dimension.value}: {item.score:.3f} ({'pass' if item.passed else 'review'})"
        for item in report.dimensions
    )
    for heading, dimension in (
        ("Voice summary", "voice_fidelity"),
        ("Structural summary", "structural_fidelity"),
        ("Constraint summary", "constraint_compliance"),
    ):
        selected = next(item for item in report.dimensions if item.dimension.value == dimension)
        lines.extend(("", f"## {heading}", ""))
        lines.extend(
            f"- {item.metric_id}: {item.score:.3f} — {item.explanation}"
            for item in selected.metrics
        )
    lines.extend(("", "## Failure analysis", ""))
    if report.failures:
        lines.extend(
            f"- {item.category.value}: {item.message} Action: {item.recommended_action}"
            for item in report.failures
        )
    else:
        lines.append("- No threshold failures detected.")
    lines.extend(("", "## Recommended improvements", ""))
    if report.recommended_improvements:
        lines.extend(f"- {item}" for item in report.recommended_improvements)
    else:
        lines.append("- No threshold-driven improvements required.")
    lines.extend(("", "## Traceability", ""))
    lines.extend(
        (
            f"- Context: {report.context_id}",
            f"- Retrieval bundle: {report.retrieval_bundle_id}",
            f"- HVM release: {report.hvm_release_id}",
            f"- VKR release: {report.vkr_release_id}",
            f"- Evidence references: {len(report.evidence_references)}",
        )
    )
    return "\n".join(lines) + "\n"
