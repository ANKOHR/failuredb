"""FailureDB regression and end-to-end tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from failuredb.clustering import cluster_records
from failuredb.fixtures import fixture_records, write_fixtures
from failuredb.models import CATEGORIES, read_jsonl, validate_record
from failuredb.recommendations import build_recommendations
from failuredb.reports import HONESTY_BANNER, render_html, render_markdown

ROOT = Path(__file__).resolve().parents[1]


def cli(*args: object, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    return subprocess.run(
        [sys.executable, "-m", "failuredb", *(str(arg) for arg in args)],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def write_records(path: Path, values: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(value, sort_keys=True) + "\n" for value in values), encoding="utf-8")


def assignments_by_id(records=None):
    records = records if records is not None else fixture_records()
    return {assignment.record_id: assignment for assignment in cluster_records(records)}


def test_fixture_generation_is_byte_deterministic_and_labeled(tmp_path: Path) -> None:
    first_data, first_manifest = write_fixtures(tmp_path / "one")
    second_data, second_manifest = write_fixtures(tmp_path / "two")
    assert first_data.read_bytes() == second_data.read_bytes()
    assert first_manifest.read_bytes() == second_manifest.read_bytes()
    manifest = json.loads(first_manifest.read_text(encoding="utf-8"))
    assert "SYNTHETIC FICTIONAL" in manifest["label"]
    assert manifest["record_count"] == 9
    records, issues = read_jsonl(first_data)
    assert not issues
    assert len(records) == 9
    assert {record.data_origin for record in records} == {"synthetic_fixture"}


def test_valid_fixture_records_cover_all_eight_categories() -> None:
    records = fixture_records()
    assert set(CATEGORIES).issubset({record.category for record in records})
    assert all(record.evidence_quotes for record in records)


@pytest.mark.parametrize("category", CATEGORIES)
def test_each_category_accepts_a_valid_typed_record(category: str) -> None:
    fixture = next(record.to_dict() for record in fixture_records() if record.category == category)
    record, issues = validate_record(fixture)
    assert record is not None
    assert record.category == category
    assert issues == []


def test_validation_reports_named_errors_for_malformed_record(tmp_path: Path) -> None:
    malformed = {
        "id": "bad id",
        "category": "mystery",
        "tool": "",
        "severity": "urgent",
        "episode_ref": 5,
        "observed_behaviour": "x",
        "expected_behaviour": "y",
        "evidence_quotes": [],
        "extra": True,
    }
    path = tmp_path / "bad.jsonl"
    path.write_text(json.dumps(malformed) + "\nnot json\n", encoding="utf-8")
    records, issues = read_jsonl(path)
    assert records == []
    rendered = "\n".join(str(issue) for issue in issues)
    for name in ("id", "category", "tool", "severity", "episode_ref", "evidence_quotes", "extra", "JSON"):
        assert name in rendered


def test_missing_required_field_has_named_error() -> None:
    raw = fixture_records()[0].to_dict()
    del raw["expected_behaviour"]
    record, issues = validate_record(raw)
    assert record is None
    assert any(issue.field == "expected_behaviour" and "missing" in issue.message for issue in issues)


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    raw = fixture_records()[0].to_dict()
    path = tmp_path / "dupes.jsonl"
    write_records(path, [raw, raw])
    records, issues = read_jsonl(path)
    assert len(records) == 1
    assert any(issue.field == "id" and "duplicate" in issue.message for issue in issues)


def test_clustering_assigns_each_planted_failure_to_its_category() -> None:
    records = fixture_records()
    results = assignments_by_id(records)
    for record in records:
        if record.id == "fx-ambiguous-001":
            continue
        assignment = results[record.id]
        assert assignment.status == "ASSIGNED"
        assert assignment.category == record.category
        assert assignment.score >= 0.60


def test_ambiguous_record_is_low_confidence_review() -> None:
    assignment = assignments_by_id()["fx-ambiguous-001"]
    assert assignment.status == "REVIEW"
    assert assignment.category is None
    assert assignment.score < 0.60
    assert assignment.candidate_category == "planning"
    assert assignment.runner_up_category == "retrieval"


def test_clustering_is_deterministic_and_assignments_have_scores() -> None:
    records = fixture_records()
    first = [item.to_dict() for item in cluster_records(records)]
    second = [item.to_dict() for item in cluster_records(list(reversed(records)))]
    assert first == second
    assert all(isinstance(item["score"], float) for item in first)
    assert all(0.0 <= item["score"] <= 1.0 for item in first)


def test_query_category_severity_and_tool_filters_have_exact_counts(tmp_path: Path) -> None:
    data, _ = write_fixtures(tmp_path / "fixtures")
    db = tmp_path / "db.jsonl"
    assert cli("ingest", data, "--db", db).returncode == 0
    by_severity = json.loads(cli("query", "--severity", "high", "--db", db).stdout.split("\n" + HONESTY_BANNER)[0])
    by_tool = json.loads(cli("query", "--tool", "browser", "--db", db).stdout.split("\n" + HONESTY_BANNER)[0])
    for category in CATEGORIES:
        by_category = json.loads(cli("query", "--category", category, "--db", db).stdout.split("\n" + HONESTY_BANNER)[0])
        assert by_category["count"] == 1
    assert by_severity["count"] == 3
    assert by_tool["count"] == 1
    assert by_tool["records"][0]["id"] == "fx-looping-001"


def test_query_full_text_search_finds_planted_behaviour(tmp_path: Path) -> None:
    data, _ = write_fixtures(tmp_path / "fixtures")
    db = tmp_path / "db.jsonl"
    cli("ingest", data, "--db", db)
    result = cli("query", "--text", "stale passage", "--db", db)
    parsed = json.loads(result.stdout.split("\n" + HONESTY_BANNER)[0])
    assert parsed["count"] == 1
    assert parsed["records"][0]["id"] == "fx-retrieval-001"


def test_recommendations_cite_existing_records_and_verbatim_evidence() -> None:
    records = fixture_records()
    by_id = {record.id: record for record in records}
    recommendations = build_recommendations(records)
    assert len(recommendations) == 8
    for recommendation in recommendations:
        assert recommendation.citations
        for citation in recommendation.citations:
            assert citation.record_id in by_id
            assert citation.quote in by_id[citation.record_id].evidence_quotes
            assert by_id[citation.record_id].category == recommendation.category


def test_recommendations_are_derived_from_assigned_matching_records() -> None:
    records = fixture_records()
    results = {item.record_id: item for item in cluster_records(records)}
    recommendations = build_recommendations(records)
    cited_ids = {citation.record_id for rec in recommendations for citation in rec.citations}
    assert "fx-ambiguous-001" not in cited_ids
    assert all(results[record_id].status == "ASSIGNED" for record_id in cited_ids)


def test_recommendation_omits_records_without_matching_evidence_quotes() -> None:
    records = fixture_records()
    records[0] = type(records[0])(
        **{**records[0].to_dict(), "evidence_quotes": ("Unrelated excerpt.",)}
    )
    recommendations = build_recommendations(records)
    assert all(item.category != "planning" for item in recommendations)


def test_reports_include_summary_recommendations_citations_and_honesty_boundary() -> None:
    records = fixture_records()
    markdown = render_markdown(records)
    html = render_html(records)
    for report in (markdown, html):
        assert "HONESTY BOUNDARY" in report
        assert "synthetic" in report
        assert "not a trained" in report
        assert "Engineering recommendations" in report
        assert "fx-planning-001" in report
        assert "Checkpoint the active plan" in report
    assert "## Cluster summary" in markdown
    assert "<h2>Cluster summary</h2>" in html
    assert "| REVIEW | 1 | medium: 1 |" in markdown


def test_reports_are_byte_identical_across_reruns() -> None:
    records = fixture_records()
    assert render_markdown(records).encode("utf-8") == render_markdown(records).encode("utf-8")
    assert render_html(records).encode("utf-8") == render_html(records).encode("utf-8")


def test_cli_report_files_are_byte_identical_across_reruns(tmp_path: Path) -> None:
    data, _ = write_fixtures(tmp_path / "fixtures")
    db = tmp_path / "db.jsonl"
    cli("ingest", data, "--db", db)
    first = tmp_path / "one.md"
    second = tmp_path / "two.md"
    assert cli("report", "--format", "md", "--out", first, "--db", db).returncode == 0
    assert cli("report", "--format", "md", "--out", second, "--db", db).returncode == 0
    assert first.read_bytes() == second.read_bytes()


def test_cli_all_subcommands_smoke_end_to_end(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "fixtures"
    result = cli("fixtures", "--out", fixture_dir)
    assert result.returncode == 0, result.stderr
    data = fixture_dir / "failures.jsonl"
    db = tmp_path / "db.jsonl"

    result = cli("ingest", data, "--db", db)
    assert result.returncode == 0, result.stderr
    assert "Accepted 9 records" in result.stdout

    result = cli("cluster", "--db", db)
    assert result.returncode == 0, result.stderr
    assert '"status": "REVIEW"' in result.stdout

    result = cli("query", "--category", "execution", "--db", db)
    assert result.returncode == 0, result.stderr
    assert '"count": 1' in result.stdout

    result = cli("recommend", "--db", db)
    assert result.returncode == 0, result.stderr
    assert "fx-looping-001" in result.stdout

    md_path = tmp_path / "report.md"
    result = cli("report", "--format", "md", "--out", md_path, "--db", db)
    assert result.returncode == 0, result.stderr
    assert HONESTY_BANNER in md_path.read_text(encoding="utf-8")
    html_path = tmp_path / "report.html"
    result = cli("report", "--format", "html", "--out", html_path, "--db", db)
    assert result.returncode == 0, result.stderr
    assert "<html" in html_path.read_text(encoding="utf-8")


def test_cli_validation_rejects_bad_input_with_named_errors(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.jsonl"
    malformed.write_text('{"id":"broken","category":"bad"}\n', encoding="utf-8")
    result = cli("ingest", malformed, "--db", tmp_path / "db.jsonl")
    assert result.returncode == 2
    assert "category" in result.stderr
    assert "severity" in result.stderr
    assert "Accepted 0 records. Rejected 1 records." in result.stdout


def test_cli_help_states_honesty_boundary() -> None:
    result = cli("--help")
    assert result.returncode == 0
    assert "synthetic, fictional fixtures" in result.stdout
    assert "not a trained" in result.stdout


def test_ingest_appends_and_rejects_existing_duplicate_id(tmp_path: Path) -> None:
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    record = fixture_records()[0].to_dict()
    write_records(first, [record])
    write_records(second, [record])
    db = tmp_path / "db.jsonl"
    assert cli("ingest", first, "--db", db).returncode == 0
    result = cli("ingest", second, "--db", db)
    assert result.returncode == 2
    assert "duplicate id" in result.stderr
    loaded, issues = read_jsonl(db)
    assert not issues
    assert len(loaded) == 1
