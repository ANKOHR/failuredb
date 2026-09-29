"""Local JSONL database operations."""

from __future__ import annotations

from pathlib import Path

from .models import FailureRecord, ValidationIssue, read_jsonl, write_jsonl


class DatabaseError(Exception):
    """Raised when a database file cannot be loaded or updated safely."""


def load_database(path: str | Path) -> list[FailureRecord]:
    database = Path(path)
    if not database.exists():
        return []
    records, issues = read_jsonl(database)
    if issues:
        details = "\n".join(str(issue) for issue in issues)
        raise DatabaseError(f"database validation failed:\n{details}")
    return records


def ingest_into_database(source: str | Path, database: str | Path) -> tuple[int, int, list[ValidationIssue]]:
    """Append valid records; reject malformed lines and duplicate IDs by name."""
    incoming, issues = read_jsonl(source)
    if Path(database).exists():
        existing, database_issues = read_jsonl(database)
        if database_issues:
            raise DatabaseError("existing database validation failed:\n" + "\n".join(map(str, database_issues)))
    else:
        existing = []
    existing_ids = {record.id for record in existing}
    unique_incoming: list[FailureRecord] = []
    for record in incoming:
        if record.id in existing_ids:
            issues.append(ValidationIssue(0, "id", f"duplicate id '{record.id}' already exists in database"))
            continue
        existing_ids.add(record.id)
        unique_incoming.append(record)
    if unique_incoming:
        write_jsonl(database, [*existing, *unique_incoming])
    rejected_count = len({issue.line for issue in issues})
    return len(unique_incoming), rejected_count, issues
