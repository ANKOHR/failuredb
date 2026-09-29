"""Deterministic weighted feature-overlap clustering."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .models import CATEGORIES, FailureRecord

# These vocabularies are the inspectable category cues and behaviour prototypes.
# Similarity is deterministic and uses no model, random seed, or external service.
CATEGORY_CUES: dict[str, frozenset[str]] = {
    "planning": frozenset("plan planning step sequence prioritize schedule checkpoint".split()),
    "retrieval": frozenset("retrieve retrieval search source document stale lookup result".split()),
    "hallucination": frozenset("unsupported fabricate citation evidence claim invented".split()),
    "tool_misuse": frozenset("schema argument parameter payload invoke malformed".split()),
    "state_corruption": frozenset("state overwrite corrupt persist checkpoint mutation".split()),
    "looping": frozenset("loop repeat retry cycle again repeated".split()),
    "permissions": frozenset("permission authorize access protected credential authorization".split()),
    "execution": frozenset("execute execution command timeout exit runtime".split()),
}
BEHAVIOUR_PROTOTYPES: dict[str, frozenset[str]] = {
    "planning": frozenset("milestone ordered prerequisite priority roadmap dependency".split()),
    "retrieval": frozenset("indexed passage freshness retrieved lookup returned".split()),
    "hallucination": frozenset("invented uncited verification factual assertion unsupported".split()),
    "tool_misuse": frozenset("malformed validation contract argument payload rejected".split()),
    "state_corruption": frozenset("snapshot mutation restore stale overwrite inconsistent".split()),
    "looping": frozenset("repeated iteration bounded retry cycle exhausted".split()),
    "permissions": frozenset("role denied privilege authorization protected forbidden".split()),
    "execution": frozenset("process exit verify command failure runtime completed".split()),
}
TOOL_PROFILES: dict[str, frozenset[str]] = {
    "planning": frozenset({"planner"}),
    "retrieval": frozenset({"search_api"}),
    "hallucination": frozenset({"response_generator"}),
    "tool_misuse": frozenset({"calendar_api"}),
    "state_corruption": frozenset({"memory_store"}),
    "looping": frozenset({"browser"}),
    "permissions": frozenset({"admin_api"}),
    "execution": frozenset({"shell"}),
}
TOKEN_RE = re.compile(r"[a-z0-9]+")

LABEL_WEIGHT = 0.10
CATEGORY_CUE_WEIGHT = 0.35
TOOL_WEIGHT = 0.20
BEHAVIOUR_WEIGHT = 0.35
MIN_CONFIDENCE = 0.60
MIN_MARGIN = 0.12


@dataclass(frozen=True, slots=True)
class Assignment:
    record_id: str
    category: str | None
    status: str
    score: float
    candidate_category: str
    runner_up_category: str
    runner_up_score: float

    def to_dict(self) -> dict[str, object]:
        return {
            "record_id": self.record_id,
            "category": self.category,
            "status": self.status,
            "score": self.score,
            "candidate_category": self.candidate_category,
            "runner_up_category": self.runner_up_category,
            "runner_up_score": self.runner_up_score,
        }


def tokenize(text: str) -> frozenset[str]:
    return frozenset(TOKEN_RE.findall(text.casefold()))


def _scores(record: FailureRecord) -> list[tuple[str, float]]:
    behaviour = tokenize(record.observed_behaviour + " " + record.expected_behaviour)
    values: list[tuple[str, float]] = []
    for category in CATEGORIES:
        cues = CATEGORY_CUES[category]
        prototypes = BEHAVIOUR_PROTOTYPES[category]
        cue_score = min(1.0, len(behaviour & cues) / 2.0)
        prototype_score = len(behaviour & prototypes) / len(prototypes)
        label_score = 1.0 if record.category == category else 0.0
        tool_score = 1.0 if record.tool.casefold() in TOOL_PROFILES[category] else 0.0
        score = (
            LABEL_WEIGHT * label_score
            + CATEGORY_CUE_WEIGHT * cue_score
            + TOOL_WEIGHT * tool_score
            + BEHAVIOUR_WEIGHT * prototype_score
        )
        values.append((category, round(score, 4)))
    return sorted(values, key=lambda pair: (-pair[1], pair[0]))


def cluster_record(record: FailureRecord) -> Assignment:
    ranked = _scores(record)
    best_category, best_score = ranked[0]
    runner_up_category, runner_up_score = ranked[1]
    review = best_score < MIN_CONFIDENCE or best_score - runner_up_score < MIN_MARGIN
    return Assignment(
        record_id=record.id,
        category=None if review else best_category,
        status="REVIEW" if review else "ASSIGNED",
        score=best_score,
        candidate_category=best_category,
        runner_up_category=runner_up_category,
        runner_up_score=runner_up_score,
    )


def cluster_records(records: list[FailureRecord] | tuple[FailureRecord, ...]) -> list[Assignment]:
    return [cluster_record(record) for record in sorted(records, key=lambda item: item.id)]
