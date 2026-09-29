"""Deterministic Markdown and HTML reports."""

from __future__ import annotations

from collections import Counter, defaultdict
from html import escape

from .clustering import Assignment, cluster_records
from .models import CATEGORIES, SEVERITIES, FailureRecord
from .recommendations import Recommendation, build_recommendations

HONESTY_BANNER = (
    "HONESTY BOUNDARY: Bundled failures are synthetic, fictional fixtures for research. "
    "This report makes no claim that input records are real production incidents. "
    "Clustering is deterministic rule-based grouping, not a trained or machine-learned classifier."
)


def _cluster_rows(assignments: list[Assignment]) -> tuple[list[tuple[str, int, dict[str, int]]], dict[str, Assignment]]:
    by_cluster: dict[str, list[Assignment]] = defaultdict(list)
    assignment_by_id = {item.record_id: item for item in assignments}
    for item in assignments:
        by_cluster[item.category if item.category is not None else "REVIEW"].append(item)
    rows = []
    for category in (*CATEGORIES, "REVIEW"):
        members = by_cluster.get(category, [])
        if not members:
            continue
        rows.append((category, len(members), {}))
    return rows, assignment_by_id


def _severity_counts(
    category: str,
    records: list[FailureRecord],
    assignment_by_id: dict[str, Assignment],
) -> str:
    counts = Counter(
        record.severity
        for record in records
        if (assignment_by_id[record.id].category or "REVIEW") == category
    )
    return ", ".join(f"{severity}: {counts[severity]}" for severity in SEVERITIES if counts[severity]) or "none"


def render_markdown(
    records: list[FailureRecord],
    assignments: list[Assignment] | None = None,
    recommendations: list[Recommendation] | None = None,
) -> str:
    assignments = assignments if assignments is not None else cluster_records(records)
    recommendations = recommendations if recommendations is not None else build_recommendations(records, assignments)
    rows, assignment_by_id = _cluster_rows(assignments)
    ordered_records = sorted(records, key=lambda item: item.id)
    lines = [
        "# FailureDB report",
        "",
        f"> **{HONESTY_BANNER}**",
        "",
        "## Cluster summary",
        "",
        "| Cluster | Count | Severities |",
        "| --- | ---: | --- |",
    ]
    for category, count, _ in rows:
        lines.append(f"| {category} | {count} | {_severity_counts(category, ordered_records, assignment_by_id)} |")
    lines.extend(["", "## Engineering recommendations", ""])
    if not recommendations:
        lines.append("No recommendations were produced because no assigned cluster had matching evidence.")
    for recommendation in recommendations:
        lines.append(f"### {recommendation.category}")
        lines.append("")
        lines.append(recommendation.action)
        lines.append("")
        lines.append("Evidence:")
        for citation in recommendation.citations:
            lines.append(f'- `{citation.record_id}`: "{citation.quote}"')
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_html(
    records: list[FailureRecord],
    assignments: list[Assignment] | None = None,
    recommendations: list[Recommendation] | None = None,
) -> str:
    assignments = assignments if assignments is not None else cluster_records(records)
    recommendations = recommendations if recommendations is not None else build_recommendations(records, assignments)
    rows, assignment_by_id = _cluster_rows(assignments)
    ordered_records = sorted(records, key=lambda item: item.id)
    output = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8"><title>FailureDB report</title></head><body>',
        "<h1>FailureDB report</h1>",
        f'<p class="honesty-boundary"><strong>{escape(HONESTY_BANNER)}</strong></p>',
        "<h2>Cluster summary</h2>",
        "<table><thead><tr><th>Cluster</th><th>Count</th><th>Severities</th></tr></thead><tbody>",
    ]
    for category, count, _ in rows:
        output.append(
            f"<tr><th>{escape(category)}</th><td>{count}</td><td>{escape(_severity_counts(category, ordered_records, assignment_by_id))}</td></tr>"
        )
    output.extend(["</tbody></table>", "<h2>Engineering recommendations</h2>"])
    if not recommendations:
        output.append("<p>No recommendations were produced because no assigned cluster had matching evidence.</p>")
    for recommendation in recommendations:
        output.extend([f"<section><h3>{escape(recommendation.category)}</h3>", f"<p>{escape(recommendation.action)}</p>", "<ul>"])
        for citation in recommendation.citations:
            output.append(
                f'<li><code>{escape(citation.record_id)}</code>: &quot;{escape(citation.quote)}&quot;</li>'
            )
        output.append("</ul></section>")
    output.append("</body></html>")
    return "\n".join(output) + "\n"
