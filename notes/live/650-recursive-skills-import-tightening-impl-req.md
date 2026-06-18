# 650 — Recursive Skills Import Tightening (Impl.Req)

## Scope

Narrow cleanup of the recursive `agentos skills import` code added in this session
(`src/agentos/skills/commands.py`). No behavior change to the public CLI contract.

## Cleanup themes

1. **Restore lost type annotation (clarity regression).**
   `_record_skills_project_command` was changed to return the resolved project
   handler but left unannotated (`def ...(args)`), dropping its former `-> None`.
   Add an explicit return annotation so the callers' use of the returned handler
   (`base_project.root`) is self-documenting.

2. **Single-source the recursive failure output (duplicate emission).**
   `_cmd_skills_import_recursive` prints each failure to stderr twice: once inline
   during iteration (`error: {exc}`) and again in a trailing re-list loop
   (`- {root}: {message}`). Keep the inline, in-context error (streaming feedback,
   positioned under its `=== root ===` header) and drop the redundant trailing
   re-list. The summary line keeps the failure **count**; exit code is unchanged.

## Constraints

- Module-local edits only; no new helpers, frameworks, or signature changes to
  public functions.
- Exit semantics unchanged: non-zero exit when any subproject import fails.
- `--recursive` / `--depth` behavior, ordering, and per-project output unchanged.

## Verification

- `uv run python -m pytest agentos-cli/tests/test_e2e_skills.py -q` (7 tests).
- The existing recursive tests assert the summary `count` line, not the trailing
  re-list, so they remain valid.
