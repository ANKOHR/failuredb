# FailureDB

FailureDB turns typed agent failure records into deterministic category assignments, searchable evidence, and engineering recommendations tied to specific records. Its focus is the analysis layer on top of an agent failure taxonomy.

> **Positioning:** FailureDB does not tell you agents fail. It tells you how yours fail, how often, and what to fix first, with the evidence attached.

## Quickstart

Requires Python 3.10 or newer. The application uses the Python standard library at runtime.

```powershell
python -m pip install -e ".[test]"
pytest

failuredb fixtures --out examples
failuredb ingest examples/failures.jsonl --db local-failures.jsonl
failuredb cluster --db local-failures.jsonl
failuredb query --category looping --severity medium --tool browser --db local-failures.jsonl
failuredb query --text "retry cycle" --db local-failures.jsonl
failuredb recommend --db local-failures.jsonl
failuredb report --format md --out report.md --db local-failures.jsonl
failuredb report --format html --out report.html --db local-failures.jsonl
```

The default local database is `failuredb.jsonl` in the current directory. `ingest` appends valid records and reports malformed rows with line and field names. Duplicate IDs are rejected. Commands that read the database create no files. All outputs are repeatable for identical input records.

The bundled fixture set has nine invented records, one for each of the eight taxonomy categories plus one deliberately ambiguous record. Generated fixture records carry `data_origin: synthetic_fixture`; the fixture directory also contains a `FIXTURES.json` label. Do not treat these examples as incident reports.

## HONESTY BOUNDARY

The bundled failures are synthetic, fictional fixtures for research. They are not reports of real production incidents. Clustering is deterministic rule-based grouping, not a trained classifier. No report or CLI output should be read as evidence that a real agent or production system experienced the described failures. When you ingest other records, FailureDB reports only the supplied records and does not verify whether they describe real incidents.

The CLI help, fixture manifest, command output, and reports repeat this boundary. No CUDA, torch, TensorFlow, GPU runtime, model weights, or random number generator is used.

## Architecture

```text
JSONL records
     |
     v
Typed schema validation ----> named line and field errors
     |
     v
Local JSONL database
     |
     +----> weighted feature overlap ----> category assignment or REVIEW
     |                                     |
     +----> exact filters and text search  +----> evidence-triggered recommendations
                                                   |
                                                   v
                                          Markdown or HTML report
```

Each layer is a small Python module. The command line uses `failuredb` after installation, or `python -m failuredb` directly from a checkout.

## Failure schema reference

Each JSONL line is one JSON object. These fields are required:

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | Stable record identifier, unique in the database, with no whitespace |
| `category` | string | Source category hint from the eight-category taxonomy |
| `tool` | string | Tool involved, using `unknown_tool` when it is not known |
| `severity` | string | One of `low`, `medium`, `high`, or `critical` |
| `episode_ref` | string | Reference to the episode or evaluation example |
| `observed_behaviour` | string | What the agent did |
| `expected_behaviour` | string | What the agent should have done |
| `evidence_quotes` | array of strings | Exact evidence excerpts available for citation |

`data_origin` is optional for supplied data and defaults to `user_supplied`. It accepts `user_supplied` or `synthetic_fixture`. FailureDB never infers that a record describes a real production incident from this field. Fixture rows set it to `synthetic_fixture`.

The category vocabulary is `planning`, `retrieval`, `hallucination`, `tool_misuse`, `state_corruption`, `looping`, `permissions`, and `execution`. Schema errors name the JSON line and the field so bad records can be repaired directly.

## Clustering rule

Clustering is deterministic weighted feature overlap, not machine learning. For each record and each category, FailureDB tokenizes the observed and expected behaviour with lowercase alphanumeric tokens. It computes:

- **Category cue overlap (35%)**: `min(1, matching cue tokens / 2)` using the inspectable cue lists in `failuredb/clustering.py`.
- **Tool profile overlap (20%)**: 1 for an exact match to the category's configured tool profile, otherwise 0.
- **Behaviour prototype overlap (35%)**: matched prototype tokens divided by the number of tokens in that category's prototype.
- **Source category hint (10%)**: 1 when the record's supplied `category` matches the candidate category, otherwise 0.

The final score is the sum of those four weighted values, rounded to four decimal places. The category with the highest score wins, with category name order breaking exact ties. If the best score is below `0.60` or the gap to the runner-up is below `0.12`, FailureDB records status `REVIEW`, keeps the candidate and scores visible, and leaves the assigned category empty. Otherwise it records `ASSIGNED`. This rule has no random seed because it uses no randomness.

`query --category` filters confidently assigned cluster categories and excludes `REVIEW` records. Severity and tool filters can include review records. `--text` performs case-insensitive phrase matching over observed and expected behaviour.

## Recommendations and reports

Recommendations are selected from a fixed category-to-action rule list. A recommendation appears only when at least one confidently assigned record has matching trigger terms in its behaviour. Each citation includes the record ID and an exact quote copied from that record's `evidence_quotes`. The recommendation rules and evidence triggers are inspectable in `failuredb/recommendations.py`; a recommendation with no matching records is omitted.

Reports list every non-empty category and `REVIEW` with exact counts and severity breakdowns. Recommendation sections include their cited record IDs and quotes. Markdown and HTML output contain the honesty boundary and no generation timestamp, so repeated runs over the same records are byte-identical.

## CLI reference

- `failuredb fixtures --out DIR`: write `failures.jsonl` and the synthetic fixture manifest.
- `failuredb ingest FILE [--db DB]`: validate and append records. The default DB is `failuredb.jsonl`.
- `failuredb cluster [--db DB]`: print assignment status, category, candidate, and similarity scores.
- `failuredb query [--category CATEGORY] [--severity SEVERITY] [--tool TOOL] [--text PHRASE] [--db DB]`: combine exact filters and print an exact result count.
- `failuredb recommend [--db DB]`: print recommendations and citations as JSON.
- `failuredb report [--format md|html] [--out FILE] [--db DB]`: render a report to stdout or a file.

## Development

```powershell
python -m pytest
```

Tests cover schema acceptance and rejection, all eight categories, fixture determinism and labels, clustering assignments and review handling, exact query counts, full-text search, citation provenance, deterministic reports, and CLI workflows.
