"""Evidence-backed, record-derived engineering recommendations."""

from __future__ import annotations

from dataclasses import dataclass

from .clustering import Assignment, cluster_records, tokenize
from .models import FailureRecord

RECOMMENDATION_RULES: dict[str, tuple[str, frozenset[str]]] = {
    "planning": (
        "Checkpoint the active plan and verify prerequisites before each consequential step.",
        frozenset("prerequisite step plan roadmap dependency".split()),
    ),
    "retrieval": (
        "Check source freshness and confirm retrieved passages match the requested document.",
        frozenset("stale passage source document search freshness".split()),
    ),
    "hallucination": (
        "Require evidence and a citation for factual claims, and state uncertainty when verification fails.",
        frozenset("invented unsupported citation evidence claim".split()),
    ),
    "tool_misuse": (
        "Validate tool arguments against the declared schema before invocation.",
        frozenset("malformed schema argument payload contract".split()),
    ),
    "state_corruption": (
        "Checkpoint state before mutation and verify the saved snapshot after restore.",
        frozenset("mutation overwrite snapshot restore state".split()),
    ),
    "looping": (
        "Add repeated-cycle detection with a bounded retry budget and a no-progress exit.",
        frozenset("repeated retry cycle iteration bounded".split()),
    ),
    "permissions": (
        "Check the caller's role and authorization before accessing protected resources.",
        frozenset("protected permission authorization role access".split()),
    ),
    "execution": (
        "Handle command timeouts and verify the process exit status before reporting completion.",
        frozenset("command process exit timeout runtime".split()),
    ),
}


@dataclass(frozen=True, slots=True)
class Citation:
    record_id: str
    quote: str

    def to_dict(self) -> dict[str, str]:
        return {"record_id": self.record_id, "quote": self.quote}


@dataclass(frozen=True, slots=True)
class Recommendation:
    category: str
    action: str
    citations: tuple[Citation, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "category": self.category,
            "action": self.action,
            "citations": [citation.to_dict() for citation in self.citations],
        }


def build_recommendations(
    records: list[FailureRecord] | tuple[FailureRecord, ...],
    assignments: list[Assignment] | None = None,
) -> list[Recommendation]:
    """Generate only rules whose trigger terms occur in assigned records."""
    assignment_list = assignments if assignments is not None else cluster_records(records)
    category_by_id = {item.record_id: item.category for item in assignment_list if item.status == "ASSIGNED"}
    recommendations: list[Recommendation] = []
    for category, (action, triggers) in RECOMMENDATION_RULES.items():
        citations: list[Citation] = []
        for record in sorted(records, key=lambda item: item.id):
            if category_by_id.get(record.id) != category:
                continue
            behaviour_tokens = tokenize(record.observed_behaviour + " " + record.expected_behaviour)
            if not behaviour_tokens & triggers:
                continue
            quote = next((candidate for candidate in record.evidence_quotes if tokenize(candidate) & triggers), None)
            if quote is None:
                continue
            citations.append(Citation(record_id=record.id, quote=quote))
        if citations:
            recommendations.append(Recommendation(category=category, action=action, citations=tuple(citations)))
    return recommendations
