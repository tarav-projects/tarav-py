# Chatlas Query Field Output - impl-req

## Impl.Abstract

- **scope:** add a small built-in field-output mode to `agentos chatlas query`, starting with `--field session_id`, and document the JSON + `jq` escape hatch for arbitrary row fields.
- **status:** ready.
- **source:** direct design discussion after needing the session ids for sessions matching `--min-user-turns` selectors.
- **goal:** support a simple scripting path:

```sh
agentos chatlas query --min-user-turns 4 --field session_id
```

while keeping the default query output as the full JSON payload and pointing advanced users to:

```sh
agentos chatlas query --min-user-turns 4 | jq -r '.rows[].session_id'
```

- **strong constraint:** this is not a new query engine. The query selection, sorting, limits, and filters must continue to use the existing `run_chatlas_query(...)` path.

## Impl.Index

### Current.Query.CLI

- CLI registration lives in `src/agentos/chatlas/commands.py`.
- The query command is handled by `_cmd_chatlas_query(args)`.
- `_cmd_chatlas_query(...)` currently calls:
  - `chatlas_query(**_chatlas_query_selector_kwargs(args))`
  - `print(format_json_output(payload))`
- Query selector arguments are registered in `_add_chatlas_query_selector_arguments(...)`.
- `_chatlas_query_selector_kwargs(...)` forwards only selector/filter controls into the query engine.
- There is no output-shape argument for `agentos chatlas query` today.

### Current.Query.Engine

- The query engine lives in `src/agentos/chatlas/query.py`.
- `run_chatlas_query(...)` already returns a payload with:
  - counts and filter metadata
  - `rows`
  - compact rows by default
  - full rows when `row_shape="full"` is requested by internal callers
- The implementation must not bypass or duplicate this filtering logic.
- `--field` should be a CLI projection over the returned `rows`, not a new query mode inside the index/filter machinery.

### Desired.User.Surface

- Default remains JSON:

```sh
agentos chatlas query --min-user-turns 4
```

- Basic built-in line output:

```sh
agentos chatlas query --min-user-turns 4 --field session_id
```

- Advanced arbitrary JSON output remains available through `jq`:

```sh
agentos chatlas query --min-user-turns 4 | jq -r '.rows[].session_id'
```

### Field.Policy

- Initial supported field:
  - `session_id`
- Reason:
  - this is the immediate scripting need
  - it avoids designing a general field language prematurely
- Output format:
  - one value per line on stdout
  - omit rows where the field is missing or `null`
  - no JSON envelope when `--field` is supplied
- The command should still respect all existing query controls:
  - `--updated-after`
  - `--min-user-turns`
  - `--sort`
  - `--scan-limit`
  - `--limit`
  - provider/session/display filters
  - content filters
- The command should return success when there are no matching rows and print nothing.

### Help.Policy

- `agentos chatlas query --help` should make the field mode discoverable.
- Add help text near the query argument registration explaining:
  - `--field session_id` prints one field value per matching row
  - for arbitrary fields, pipe the default JSON to `jq`
- Do not overbuild full schema documentation in this slice.
- A concise `epilog` or argument help text is enough as long as both examples are visible in `--help`.

### No.Legacy.Allowed

- Do not add compatibility aliases such as `--ids-only`.
- Do not add a second command for this.
- Do not add a broad field-expression DSL.
- Do not change the default JSON output.
- Do not change `run_chatlas_query(...)` filtering semantics.
- Do not make internal consumers of `chatlas_query(...)` receive line-oriented output.

## Execution.Plan

### Slice 1 - Add CLI Field Argument And Projection

Status: pending.

- Add `--field` to `agentos chatlas query`.
- Use `choices=("session_id",)` for the first version.
- Keep `_chatlas_query_selector_kwargs(...)` focused on query selectors; do not pass `field` into `run_chatlas_query(...)`.
- Update `_cmd_chatlas_query(...)`:
  - run the normal `chatlas_query(...)`
  - if `args.field` is absent, print the existing JSON payload
  - if `args.field == "session_id"`, print one non-null `row["session_id"]` per returned row
- Observable result:

```sh
agentos chatlas query --min-user-turns 4 --field session_id
```

prints only session ids.

### Slice 2 - Help Examples

Status: pending.

- Update query command help so `agentos chatlas query --help` shows both:

```sh
agentos chatlas query --min-user-turns 4 --field session_id
agentos chatlas query --min-user-turns 4 | jq -r '.rows[].session_id'
```

- Keep the help concise.
- The first example is the preferred built-in path.
- The second example is the escape hatch for arbitrary JSON fields.

### Slice 3 - Tests

Status: pending.

- Add focused tests in `tests/test_chatlas_commands.py`.
- Required coverage:
  - default `agentos chatlas query ...` still returns JSON payload
  - `--field session_id` prints only matching session ids, one per line
  - missing/null `session_id` rows are omitted from field output
  - `--field session_id` respects existing filters and limits
  - `chatlas query --help` contains both examples or at least the built-in and `jq` guidance text

### Slice 4 - Verification

Status: pending.

- Run focused tests:

```sh
uv run pytest tests/test_chatlas_commands.py -q
```

- Run lint:

```sh
uv run ruff check src/agentos/chatlas tests/test_chatlas_commands.py
```

- Refresh the installed CLI after the command-surface change:

```sh
uv tool install --reinstall --editable .
```

- Smoke-test the installed command:

```sh
agentos chatlas query --min-user-turns 4 --field session_id --limit 5
agentos chatlas query --help
```

## Impl.Log

- Created as the execution handoff for adding a minimal `--field session_id` output mode to `agentos chatlas query`, with help guidance for using `jq` when arbitrary JSON-field extraction is needed.
