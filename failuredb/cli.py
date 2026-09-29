"""Command line interface for FailureDB."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .clustering import cluster_records
from .fixtures import write_fixtures
from .models import CATEGORIES
from .recommendations import build_recommendations
from .reports import HONESTY_BANNER, render_html, render_markdown
from .storage import DatabaseError, ingest_into_database, load_database

DEFAULT_DB = Path("failuredb.jsonl")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="failuredb",
        description="A local database and analysis CLI for typed agent failure records.",
        epilog=HONESTY_BANNER,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    fixtures = subparsers.add_parser("fixtures", help="write synthetic fictional example failures", epilog=HONESTY_BANNER)
    fixtures.add_argument("--out", required=True, type=Path, help="directory for failures.jsonl and FIXTURES.json")

    ingest = subparsers.add_parser("ingest", help="validate and append failure records", epilog=HONESTY_BANNER)
    ingest.add_argument("failures_jsonl", type=Path)
    ingest.add_argument("--db", type=Path, default=DEFAULT_DB, help=f"database path (default: {DEFAULT_DB})")

    cluster = subparsers.add_parser("cluster", help="assign records to categories or REVIEW", epilog=HONESTY_BANNER)
    cluster.add_argument("--db", type=Path, default=DEFAULT_DB, help=f"database path (default: {DEFAULT_DB})")

    query = subparsers.add_parser("query", help="filter assigned records", epilog=HONESTY_BANNER)
    query.add_argument("--category", choices=CATEGORIES, help="assigned cluster category; REVIEW records are excluded")
    query.add_argument("--severity", choices=("low", "medium", "high", "critical"))
    query.add_argument("--tool", help="exact tool name")
    query.add_argument("--text", help="case-insensitive full-text phrase in observed or expected behaviour")
    query.add_argument("--db", type=Path, default=DEFAULT_DB, help=f"database path (default: {DEFAULT_DB})")

    recommend = subparsers.add_parser("recommend", help="derive recommendations with record citations", epilog=HONESTY_BANNER)
    recommend.add_argument("--db", type=Path, default=DEFAULT_DB, help=f"database path (default: {DEFAULT_DB})")

    report = subparsers.add_parser("report", help="render a cluster and recommendation report", epilog=HONESTY_BANNER)
    report.add_argument("--format", choices=("md", "html"), default="md")
    report.add_argument("--out", type=Path, help="write report to this path instead of stdout")
    report.add_argument("--db", type=Path, default=DEFAULT_DB, help=f"database path (default: {DEFAULT_DB})")
    return parser


def _json_dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False)


def _run(args: argparse.Namespace) -> int:
    if args.command == "fixtures":
        data_path, manifest_path = write_fixtures(args.out)
        print(f"Wrote synthetic fictional fixtures: {data_path} and {manifest_path}")
        print(HONESTY_BANNER)
        return 0

    if args.command == "ingest":
        try:
            accepted, rejected, issues = ingest_into_database(args.failures_jsonl, args.db)
        except (OSError, DatabaseError) as exc:
            print(str(exc), file=sys.stderr)
            print(HONESTY_BANNER)
            return 2
        print(f"Accepted {accepted} records. Rejected {rejected} records.")
        for issue in issues:
            print(str(issue), file=sys.stderr)
        print(HONESTY_BANNER)
        return 2 if rejected else 0

    try:
        records = load_database(args.db)
    except (OSError, DatabaseError) as exc:
        print(str(exc), file=sys.stderr)
        print(HONESTY_BANNER)
        return 2
    assignments = cluster_records(records)

    if args.command == "cluster":
        print(_json_dump({"assignments": [assignment.to_dict() for assignment in assignments], "record_count": len(records)}))
        print(HONESTY_BANNER)
        return 0

    if args.command == "query":
        assignment_by_id = {assignment.record_id: assignment for assignment in assignments}
        matched = []
        phrase = args.text.casefold() if args.text else None
        for record in records:
            assignment = assignment_by_id[record.id]
            if args.category and assignment.category != args.category:
                continue
            if args.severity and record.severity != args.severity:
                continue
            if args.tool and record.tool.casefold() != args.tool.casefold():
                continue
            searchable = (record.observed_behaviour + " " + record.expected_behaviour).casefold()
            if phrase and phrase not in searchable:
                continue
            row = record.to_dict()
            row["cluster"] = assignment.category if assignment.category else "REVIEW"
            row["cluster_score"] = assignment.score
            matched.append(row)
        print(_json_dump({"count": len(matched), "records": matched}))
        print(HONESTY_BANNER)
        return 0

    recommendations = build_recommendations(records, assignments)
    if args.command == "recommend":
        print(_json_dump([recommendation.to_dict() for recommendation in recommendations]))
        print(HONESTY_BANNER)
        return 0

    if args.command == "report":
        rendered = render_markdown(records, assignments, recommendations) if args.format == "md" else render_html(records, assignments, recommendations)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(rendered, encoding="utf-8", newline="\n")
            print(f"Wrote {args.format} report to {args.out}")
            print(HONESTY_BANNER)
        else:
            print(rendered, end="")
        return 0

    raise AssertionError(f"unknown command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    return _run(args)
