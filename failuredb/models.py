"""Typed failure records and strict JSONL validation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

CATEGORIES = (
    "planning",
    "retrieval",
    "hallucination",
    "tool_misuse",
    "state_corruption",
    "looping",
    "permissions",
    "execution",
)
SEVERITIES = ("low", "medium", "high", "critical")
DATA_ORIGINS = ("synthetic_fixture", "user_supplied")
REQUIRED_FIELDS = (
    "id",
    "category",
    "tool",
    "severity",
    "episode_ref",
    "observed_behaviour",
    "expected_behaviour",
    "evidence_quotes",
)
ALLOWED_FIELDS = frozenset((*REQUIRED_FIELDS, "data_origin"))


@dataclass(frozen=True, slots=True)
class FailureRecord:
    id: str
    category: str
    tool: str
    severity: str
    episode_ref: str
    observed_behaviour: str
    expected_behaviour: str
    evidence_quotes: tuple[str, ...]
    data_origin: str = "user_supplied"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence_quotes"] = list(self.evidence_quotes)
        return data


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    line: int
    field: str
    message: str

    def __str__(self) -> str:
        return f"line {self.line}: {self.field}: {self.message}"


def validate_record(value: Any, line: int = 1) -> tuple[FailureRecord | None, list[ValidationIssue]]:
    """Validate one JSON value and return a typed record plus named issues."""
    issues: list[ValidationIssue] = []
    if not isinstance(value, dict):
        return None, [ValidationIssue(line, "record", "expected a JSON object")]

    for field in sorted(set(value) - ALLOWED_FIELDS):
        issues.append(ValidationIssue(line, field, "unknown field"))
    for field in REQUIRED_FIELDS:
        if field not in value:
            issues.append(ValidationIssue(line, field, "required field is missing"))

    def required_text(field: str) -> str | None:
        item = value.get(field)
        if not isinstance(item, str):
            issues.append(ValidationIssue(line, field, "expected a string"))
            return None
        if not item.strip():
            issues.append(ValidationIssue(line, field, "must not be empty"))
            return None
        return item.strip()

    record_id = required_text("id") if "id" in value else None
    category = required_text("category") if "category" in value else None
    tool = required_text("tool") if "tool" in value else None
    severity = required_text("severity") if "severity" in value else None
    episode_ref = required_text("episode_ref") if "episode_ref" in value else None
    observed = required_text("observed_behaviour") if "observed_behaviour" in value else None
    expected = required_text("expected_behaviour") if "expected_behaviour" in value else None

    if record_id is not None and any(ch.isspace() for ch in record_id):
        issues.append(ValidationIssue(line, "id", "must not contain whitespace"))
    if category is not None and category not in CATEGORIES:
        issues.append(ValidationIssue(line, "category", f"expected one of: {', '.join(CATEGORIES)}"))
    if severity is not None and severity not in SEVERITIES:
        issues.append(ValidationIssue(line, "severity", f"expected one of: {', '.join(SEVERITIES)}"))

    quotes: tuple[str, ...] = ()
    if "evidence_quotes" in value:
        raw_quotes = value["evidence_quotes"]
        if not isinstance(raw_quotes, list) or not raw_quotes:
            issues.append(ValidationIssue(line, "evidence_quotes", "expected a non-empty array of strings"))
        elif any(not isinstance(quote, str) or not quote.strip() for quote in raw_quotes):
            issues.append(ValidationIssue(line, "evidence_quotes", "each item must be a non-empty string"))
        else:
            quotes = tuple(quote.strip() for quote in raw_quotes)

    data_origin = value.get("data_origin", "user_supplied")
    if not isinstance(data_origin, str) or data_origin not in DATA_ORIGINS:
        issues.append(ValidationIssue(line, "data_origin", f"expected one of: {', '.join(DATA_ORIGINS)}"))

    if issues:
        return None, issues
    assert record_id is not None
    assert category is not None
    assert tool is not None
    assert severity is not None
    assert episode_ref is not None
    assert observed is not None
    assert expected is not None
    return FailureRecord(
        id=record_id,
        category=category,
        tool=tool,
        severity=severity,
        episode_ref=episode_ref,
        observed_behaviour=observed,
        expected_behaviour=expected,
        evidence_quotes=quotes,
        data_origin=data_origin,
    ), []


def read_jsonl(path: str | Path) -> tuple[list[FailureRecord], list[ValidationIssue]]:
    """Load valid JSONL records while collecting named per-line errors."""
    records: list[FailureRecord] = []
    issues: list[ValidationIssue] = []
    seen: set[str] = set()
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            if not raw_line.strip():
                continue
            try:
                value = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                issues.append(ValidationIssue(line_number, "JSON", f"invalid JSON: {exc.msg}"))
                continue
            record, record_issues = validate_record(value, line_number)
            if record_issues:
                issues.extend(record_issues)
                continue
            assert record is not None
            if record.id in seen:
                issues.append(ValidationIssue(line_number, "id", f"duplicate id '{record.id}'"))
                continue
            seen.add(record.id)
            records.append(record)
    return records, issues


def write_jsonl(path: str | Path, records: list[FailureRecord] | tuple[FailureRecord, ...]) -> None:
    """Write records in stable ID order using canonical JSON formatting."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="\n") as handle:
        for record in sorted(records, key=lambda item: item.id):
            handle.write(json.dumps(record.to_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")
