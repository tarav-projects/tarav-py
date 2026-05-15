# Chatlas Index Doctor - impl-req

## Impl.Abstract

- **scope:** add a minimal read-only `agentos chatlas index doctor` command that verifies the materialized Chatlas session index against core index/raw-storage invariants
- **status:** implemented
- **source:** user request after manually auditing Chatlas index consistency following Claude archive migration and full reindex
- **target:** expose the most important consistency checks as a repeatable CLI command with focused tests
- **non-goals:** do not repair, reindex, migrate archives, scan live provider homes, normalize sessions, or add provider-specific deep checks in v1

## Impl.Index

### Doctor.Command.Surface

- Add `doctor` under the existing `agentos chatlas index` command group.
- The command is read-only.
- It should inspect the materialized Chatlas dataset surfaces:
  - session index rows under `index/sessions/**/*.jsonl`
  - raw provider partitions under `raw/<provider>/<fingerprint>/`
  - raw partition manifests at `raw/<provider>/<fingerprint>/manifest.json`
- It should not call `chatlas update`, `chatlas index redo`, live provider discovery, raw artifact export, or standard-model export.
- Initial output should support JSON for automation and a compact default human format.

#### appendix

Current command shape:

- `agentos chatlas index update`
- `agentos chatlas index reset`
- `agentos chatlas index redo`
- `agentos chatlas index query`

The doctor belongs next to these because it evaluates the index itself, not a specific selected session.

#### meta

- status: accepted implementation target

### Minimal.Check.Set

- The v1 doctor should keep the check set small and high-signal.
- Required row fields:
  - `uri`
  - `provider`
  - `session_id`
  - `updated_at`
  - `home`
  - `instance`
  - `provider_instance_fingerprint`
  - `primary_backing_artifact`
  - `backing_artifacts`
  - `extractable`
- Identity uniqueness:
  - no duplicate `uri`
  - no duplicate `(provider, provider_instance_fingerprint, session_id)`
- Backing artifact existence:
  - every `primary_backing_artifact.path` exists
  - every `backing_artifacts[].path` exists
- Home provenance hygiene:
  - `home` must not point inside Chatlas-managed storage
  - Chatlas-managed storage includes `<chatlas_root>/raw`, `<chatlas_root>/index`, `<chatlas_root>/views`, and `<chatlas_root>/archive`
  - `home` should describe original provider provenance, not derived Chatlas storage
- Manifest coverage:
  - every indexed `(provider, provider_instance_fingerprint)` must have `raw/<provider>/<fingerprint>/manifest.json`

#### appendix

This set captures the failures that matter most for current Chatlas operations:

- malformed rows
- duplicate session identity
- broken raw links
- stale or derived home provenance
- missing partition provenance manifests

It deliberately excludes broader diagnostics such as stats reconciliation, provider-specific semantic checks, archive migration coverage, and transcript normalization.

#### meta

- status: accepted implementation target

### Doctor.Report.Shape

- Return a stable JSON payload from the runtime function.
- Recommended shape:

```json
{
  "status": "ok",
  "command": "chatlas index doctor",
  "chatlas_root": "...",
  "session_index_root": "...",
  "raw_root": "...",
  "summary": {
    "row_count": 123,
    "check_count": 5,
    "error_count": 0,
    "warning_count": 0
  },
  "checks": [
    {
      "name": "required_fields",
      "status": "ok",
      "error_count": 0,
      "warning_count": 0,
      "sample_count": 0,
      "samples": []
    }
  ]
}
```

- `status` should be:
  - `ok` when every check passes
  - `error` when any required invariant fails
- Warnings are optional in v1; the initial minimal checks may all be errors.
- Samples should be bounded so a large broken index does not produce unbounded output.
- Samples should identify enough context to repair manually:
  - `uri` when available
  - provider/fingerprint/session id when available
  - field name or path where relevant

#### appendix

The command should be useful both in terminal workflows and scripted checks after migrations or reindex operations.

#### meta

- status: proposed implementation detail

### CLI.Exit.Semantics

- The command should exit `0` when `status == "ok"`.
- The command should exit nonzero when `status == "error"`.
- JSON output should still be printed for error status so automation can inspect failures.
- The default human output should be concise:
  - final status
  - row count
  - error count
  - one line per failed check with sample count
- Keep provider filtering out of v1 unless it falls out naturally from existing index selector helpers without adding complexity.

#### appendix

This mirrors ordinary doctor command behavior: successful check runs are quiet enough for humans, while failures are actionable and machine-readable.

#### meta

- status: proposed implementation detail

## Execution.Plan

### Slice 1 - Add doctor runtime over the shared index store

- add a small module, likely `src/agentos/chatlas/index_doctor.py`
- use `load_chatlas_session_index_rows(...)` as the index loading boundary
- compute `chatlas_root`, `session_index_root`, and `raw_root`
- implement the five minimal checks:
  - required row fields
  - duplicate URI
  - duplicate provider/fingerprint/session key
  - backing artifact paths exist
  - home not inside Chatlas-managed storage
  - manifest exists for every indexed provider/fingerprint partition
- keep helper functions local and simple
- path: index rows + raw partition filesystem -> doctor payload
- observable: a clean fixture returns `status: ok`
- check: focused tests call the runtime or CLI on fixture roots
- status: done

### Slice 2 - Add the CLI command surface

- register `agentos chatlas index doctor`
- add `--format markdown|json` with markdown as default, matching `chatlas stats` style
- route the command through `agentos.chatlas.core`
- print JSON payload for `--format json`
- return nonzero when runtime status is `error`
- path: CLI parser -> doctor runtime -> formatted output -> process exit code
- observable:
  - `agentos chatlas index --help` lists `doctor`
  - `agentos chatlas index doctor --format json` emits the doctor payload
- check: command tests cover clean and failing exit codes
- status: done

### Slice 3 - Add the minimal test battery

- add focused tests in `tests/test_chatlas_commands.py` or a dedicated Chatlas doctor test module
- cover:
  - clean index fixture returns `status: ok`
  - required field missing/null reports an error
  - duplicate `uri` reports an error
  - duplicate `(provider, provider_instance_fingerprint, session_id)` reports an error
  - missing backing artifact reports an error
  - `home` under Chatlas-managed storage reports an error
  - missing raw partition manifest reports an error
- avoid large fixture setup; write minimal JSONL rows and files under `tmp_path`
- path: synthetic Chatlas root -> CLI/runtime doctor -> deterministic error report
- observable: each known broken index shape is caught by exactly the intended check
- check: `uv run python -m pytest tests/test_chatlas_commands.py -q` or the dedicated test module
- status: done

### Slice 4 - Verify installed CLI behavior

- run focused tests
- run full test suite if focused tests pass
- reinstall editable CLI because a CLI command was added:
  - `uv tool install --reinstall --editable .`
- smoke check:
  - `agentos chatlas index doctor --format json`
  - `agentos chatlas index --help`
- observable: the installed `agentos` exposes and successfully runs the new doctor command
- check:
  - focused pytest command
  - `uv run python -m pytest -q`
  - installed CLI smoke output
- status: done

## Impl.Log

- 2026-05-15: Created implementation request from the accepted minimal design for `agentos chatlas index doctor`: a read-only index/raw consistency checker covering required fields, identity uniqueness, backing artifact existence, home provenance hygiene, and raw partition manifest coverage.
- 2026-05-15: Implemented `agentos chatlas index doctor` with JSON/markdown output, nonzero error exit semantics, focused tests for the minimal check set, editable CLI reinstall, and installed-command smoke checks against the current Chatlas index.
