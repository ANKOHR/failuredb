"""Bundled fictional fixtures for demonstrations and tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import FailureRecord, validate_record, write_jsonl

FIXTURE_DATA: tuple[dict[str, Any], ...] = (
    {
        "id": "fx-planning-001", "category": "planning", "tool": "planner", "severity": "high",
        "episode_ref": "synthetic-episode-plan-01",
        "observed_behaviour": "The plan skipped a prerequisite step and placed the final action before its dependency.",
        "expected_behaviour": "Keep an ordered roadmap with each prerequisite before its dependent milestone.",
        "evidence_quotes": ["The plan skipped a prerequisite step and placed the final action before its dependency."],
        "data_origin": "synthetic_fixture",
    },
    {
        "id": "fx-retrieval-001", "category": "retrieval", "tool": "search_api", "severity": "medium",
        "episode_ref": "synthetic-episode-retrieval-01",
        "observed_behaviour": "Search returned a stale passage from the index instead of the current source document.",
        "expected_behaviour": "Retrieve the current document and check source freshness before using the result.",
        "evidence_quotes": ["Search returned a stale passage from the index instead of the current source document."],
        "data_origin": "synthetic_fixture",
    },
    {
        "id": "fx-hallucination-001", "category": "hallucination", "tool": "response_generator", "severity": "critical",
        "episode_ref": "synthetic-episode-claim-01",
        "observed_behaviour": "The response invented an unsupported factual claim and supplied no citation or evidence.",
        "expected_behaviour": "Verify each factual assertion against evidence and include a citation, or state uncertainty.",
        "evidence_quotes": ["The response invented an unsupported factual claim and supplied no citation or evidence."],
        "data_origin": "synthetic_fixture",
    },
    {
        "id": "fx-tool-misuse-001", "category": "tool_misuse", "tool": "calendar_api", "severity": "high",
        "episode_ref": "synthetic-episode-tool-01",
        "observed_behaviour": "The invocation sent a malformed payload with an invalid date argument that the schema rejected.",
        "expected_behaviour": "Validate every argument against the tool contract and schema before invoking it.",
        "evidence_quotes": ["The invocation sent a malformed payload with an invalid date argument that the schema rejected."],
        "data_origin": "synthetic_fixture",
    },
    {
        "id": "fx-state-corruption-001", "category": "state_corruption", "tool": "memory_store", "severity": "critical",
        "episode_ref": "synthetic-episode-state-01",
        "observed_behaviour": "A state mutation overwrote the saved snapshot and left a stale, inconsistent value after restore.",
        "expected_behaviour": "Checkpoint persisted state before mutation and verify the restored snapshot afterward.",
        "evidence_quotes": ["A state mutation overwrote the saved snapshot and left a stale, inconsistent value after restore."],
        "data_origin": "synthetic_fixture",
    },
    {
        "id": "fx-looping-001", "category": "looping", "tool": "browser", "severity": "medium",
        "episode_ref": "synthetic-episode-loop-01",
        "observed_behaviour": "The agent repeated the same browser retry cycle until the iteration budget was exhausted.",
        "expected_behaviour": "Use a bounded retry count, detect repeated cycles, and exit when no progress occurs.",
        "evidence_quotes": ["The agent repeated the same browser retry cycle until the iteration budget was exhausted."],
        "data_origin": "synthetic_fixture",
    },
    {
        "id": "fx-permissions-001", "category": "permissions", "tool": "admin_api", "severity": "high",
        "episode_ref": "synthetic-episode-permission-01",
        "observed_behaviour": "The call accessed a protected resource without checking the user's role or authorization privilege.",
        "expected_behaviour": "Check permission and authorization before invoking any protected action.",
        "evidence_quotes": ["The call accessed a protected resource without checking the user's role or authorization privilege."],
        "data_origin": "synthetic_fixture",
    },
    {
        "id": "fx-execution-001", "category": "execution", "tool": "shell", "severity": "low",
        "episode_ref": "synthetic-episode-execution-01",
        "observed_behaviour": "The command process returned a failure exit code after a runtime timeout.",
        "expected_behaviour": "Execute with timeout handling and verify the process exit status before reporting completion.",
        "evidence_quotes": ["The command process returned a failure exit code after a runtime timeout."],
        "data_origin": "synthetic_fixture",
    },
    {
        "id": "fx-ambiguous-001", "category": "execution", "tool": "unknown_tool", "severity": "medium",
        "episode_ref": "synthetic-episode-ambiguous-01",
        "observed_behaviour": "The agent paused between the next step and a source check, and the trace does not specify which came first.",
        "expected_behaviour": "Choose an order only after clarifying whether the next step or source check should come first.",
        "evidence_quotes": ["The trace does not specify which came first between the next step and a source check."],
        "data_origin": "synthetic_fixture",
    },
)


def fixture_records() -> list[FailureRecord]:
    records: list[FailureRecord] = []
    for line, raw in enumerate(FIXTURE_DATA, 1):
        record, issues = validate_record(raw, line)
        if issues:
            raise ValueError("invalid built-in fixture: " + "; ".join(map(str, issues)))
        assert record is not None
        records.append(record)
    return records


def write_fixtures(output_dir: str | Path) -> tuple[Path, Path]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    data_path = destination / "failures.jsonl"
    manifest_path = destination / "FIXTURES.json"
    records = fixture_records()
    write_jsonl(data_path, records)
    manifest = {
        "label": "SYNTHETIC FICTIONAL FIXTURES FOR RESEARCH",
        "description": "These records are invented examples, not reports of real production incidents.",
        "record_count": len(records),
        "categories": sorted({record.category for record in records}),
        "failure_records": data_path.name,
    }
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return data_path, manifest_path
