# Impl.Req: Claude Auth Cleanup

## Impl.Abstract

Status: implemented

Source context:
- The Claude ambient auth artifact implementation landed in `agentos-py` and now has focused tests.
- A cleanup pass should improve maintainability without changing behavior or expanding the auth design.

Scope:
- Remove repeated Claude test-home construction from three test files.
- Split dense Claude reconcile registration planning/mutation logic into focused module-local helpers.

Out of scope:
- Changing Claude credential artifact format.
- Changing reconcile activation semantics.
- Changing Keychain read/write behavior.
- Broad file reorganization of `src/agentos/claude/account_registry.py`.

## Impl.Index

### Block 1: Claude test setup repeats credential fixture knowledge

Claim:
The same synthetic Claude home builder appears in three test modules and repeats `.claude.json`, `.credentials.json`, OAuth field names, default token values, display name, and organization id.

Hard.Evidence:
- `tests/test_claude_account_registry.py` defines `_write_claude_home(...)`.
- `tests/test_claude_account_reconcile.py` defines `_write_claude_home(...)`.
- `tests/test_claude_account_status.py` defines `_write_claude_home(...)`.

Design consequence:
Move the shared builder into `tests/_helpers.py` as `write_claude_home(...)` and import it in the three Claude test files. Keep the helper test-local; do not introduce production utilities.

### Block 2: Claude reconcile registration logic has too many responsibilities inline

Claim:
`_reconcile_claude_accounts(...)` currently performs classification, dedupe, selection, warning generation, check-mode action construction, and mutation inline.

Hard.Evidence:
- `src/agentos/claude/account_reconcile.py` has a long `if request.register_discovered:` loop where each account's fresh candidates are deduped, warning payloads are built, check-mode actions are appended, and mutations call `register_claude_ambient_auth_from_home(...)`.

Design consequence:
Extract module-local helpers around the fresh-candidate registration block, such as:
- `_register_fresh_artifacts(...)`
- `_multiple_fresh_artifacts_warning(...)`
- `_register_candidate_actions(...)`

Keep the behavior exactly the same and avoid new public API.

## Execution.Plan

### Slice 1: Shared Claude test home helper

Status: completed

Change:
- Add `write_claude_home(...)` to `tests/_helpers.py`.
- Update the three Claude test modules to import and use it.
- Delete duplicate local helper functions and now-unused `json` / `write_text_file` imports.

Validation:
- `uv run pytest tests/test_claude_account_registry.py tests/test_claude_account_reconcile.py tests/test_claude_account_status.py -q`

### Slice 2: Reconcile fresh registration helper extraction

Status: completed

Change:
- Extract the fresh artifact registration block from `_reconcile_claude_accounts(...)` into focused private helpers.
- Preserve exact action/warning semantics, including dedupe-by-artifact-id and conservative activation when multiple distinct artifacts are seen.

Validation:
- `uv run pytest tests/test_claude_account_reconcile.py -q`
- `uv run ruff check src/agentos/claude/account_reconcile.py tests/test_claude_account_reconcile.py tests/test_claude_account_registry.py tests/test_claude_account_status.py`

## Acceptance Signals

- Claude tests no longer duplicate the home fixture builder.
- `_reconcile_claude_accounts(...)` reads as orchestration rather than mixed planning/mutation detail.
- All affected tests pass.
- No account registry behavior or CLI output semantics change.

## Validation Commands

```sh
cd /Users/pereiro/projects/agentos-project/agentos-py
uv run pytest tests/test_claude_account_registry.py tests/test_claude_account_reconcile.py tests/test_claude_account_status.py -q
uv run pytest -q
uv run ruff check src/agentos/claude/account_reconcile.py tests/test_claude_account_reconcile.py tests/test_claude_account_registry.py tests/test_claude_account_status.py
```

## Impl.Log

- 2026-06-09: Impl.Req created by `hugentics-codebase-cleaner` after committing the Claude ambient auth feature baseline. No implementation performed in this artifact creation pass.
