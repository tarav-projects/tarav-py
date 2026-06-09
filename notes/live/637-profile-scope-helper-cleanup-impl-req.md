# Impl.Req: Profile Scope Helper Cleanup

## Impl.Abstract

Status: executed.

Source context: post-implementation cleanup after profile schema moved from singular `account`/`home`/`account_policy` fields to scoped `accounts` and `homes` lists. The feature is working and verified, but account/home scope checks now repeat small pieces of knowledge across config loading, run resolution, base agent account checks, and monitor target validation.

Target repository: `/Users/pereiro/projects/agentos-project/agentos-py`

Pre-cleanup baseline commit: `e696e91 feat: scope agent profiles by accounts and homes`

## Impl.Index

### Cleanup.Scope

Keep the cleanup narrow.

Do not redesign profile schema, monitor target schema, account registry, or provider agents.

Only centralize repeated profile scope helper logic that became visible after the account/home profile change.

### Repeated.Knowledge

The following knowledge is repeated in several modules:

- how to get allowed account ids from a profile config or agent
- how to get allowed home paths from a profile config
- how to format allowed lists in errors
- how to test whether a requested account/home belongs to the profile scope

This should live in one small module under `agentos.agent`, so callers can share semantics without creating a broad framework.

### Boundary.Shape

Provider agents should still receive one selected runtime `account` and one selected runtime `home`.

The helper layer should not replace that runtime shape. It should only make scope validation and error formatting consistent.

### No.Legacy.Allowed

Do not reintroduce `account_policy`.

Do not add compatibility handling for old `account` or `home` profile fields.

Do not accept old schema in tests.

## Execution.Plan

### Slice 1: Add Profile Scope Helpers

Add a small module, expected path:

`src/agentos/agent/profile_scope.py`

Expected helper responsibilities:

- return allowed account ids from an `accounts` tuple
- return allowed home path strings from a `homes` tuple
- format allowed values deterministically
- validate account override against allowed accounts
- select/validate requested home against allowed homes

Validation:

- existing profile and monitor tests should still pass
- no provider behavior should change

### Slice 2: Replace Duplicated Scope Checks

Use the new helpers in:

- `src/agentos/agent/primitives.py` for `--account` scope validation
- `src/agentos/agent/providers.py` for profile `--home` selection
- `src/agentos/agent/monitor/config.py` for profile-backed monitor target validation

Keep each call site readable. Do not hide high-level monitor validation behind a generic validator.

Validation:

- run targeted profile and monitor tests
- confirm error behavior remains equivalent enough for current tests

### Slice 3: Final Verification

Run:

```bash
uv run pytest -q
uv run ruff check src tests
```

Refresh the installed CLI only if source changes affect CLI behavior and smoke testing is needed.

## Acceptance Signals

- Profile scope validation knowledge is centralized in one small helper module.
- `account_policy` remains absent from runtime code except tests that verify rejection of the removed field.
- `agentos agent run --profile browser-jp --home /tmp/not-allowed --dry-run --prompt hello` still fails.
- Full tests and Ruff pass.

## Impl.Log

- 2026-06-09: Executed as designed. No deviations.
