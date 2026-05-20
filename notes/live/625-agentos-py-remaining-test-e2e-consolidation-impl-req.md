# Impl.Req: Agentos-Py Remaining Test E2E Consolidation

## Impl.Abstract

Status: implemented

Source Context:
- User accepted the target test shape from the prior e2e simplification pass: keep only e2e tests unless a test protects a durable file/hash/output contract.
- Prior Impl.Req: `notes/live/624-agentos-py-e2e-test-simplification-impl-req.md`
- Current follow-up target: finish the remaining non-e2e-ish tests by consolidating `tests/test_account_usage_fallback.py` and `tests/test_agent_monitor_auto_prime.py`.
- There is a small uncommitted cleanup pass in the worktree that centralizes captured JSON parsing in several test files. Preserve it and do not revert it.

Scope:
- Reduce or remove the two remaining granular/internal test files:
  - `tests/test_account_usage_fallback.py`
  - `tests/test_agent_monitor_auto_prime.py`
- Move durable behavior coverage into the compact e2e/account test layer or into smaller contract-style tests only where e2e coverage cannot observe the contract directly.
- Keep the important behaviors covered:
  - Codex account status records fresh app-server usage in the usage registry.
  - Codex account status falls back to cached usage registry data after live usage failure.
  - Codex account status remains an error when live usage fails and no cache exists.
  - Auto-prime zero-limit workflow preserves the durable period-key behavior that prevents duplicate priming.

Non-Goals:
- Do not rewrite production monitor/account code unless test consolidation exposes a real bug.
- Do not preserve private-helper unit tests merely because they already exist.
- Do not expand the suite into broader granular coverage while moving files.

Acceptance Signals:
- `uv run pytest` passes.
- `tests/test_account_usage_fallback.py` is deleted or reduced to a minimal durable-contract file with a clear reason.
- `tests/test_agent_monitor_auto_prime.py` is deleted or reduced to 1-2 compact durable-contract tests.
- Important account fallback behavior is covered through `tests/test_e2e_agent_accounts.py` or an equivalent scenario-style file.
- Test source LOC decreases, or any small increase in shared helpers is more than offset by deleting granular duplication.

## Impl.Index

### Test.Shape.Intent

Evidence:
- User explicitly wants aggressive test reduction and e2e-oriented coverage.
- Existing target shape says: "Delete unit tests for private helpers unless they protect a durable file/hash/output contract."

Alignment:
- `account_usage_registry_fallback(...)` tests are private-helper tests and should not survive unchanged.
- `AutoPrimeZeroLimitsWorkflow._eligible_periods(...)` tests are private-method tests, but some assertions protect durable externally meaningful behavior: the persisted `period_key` shape and repeat-ping prevention.

### Account.Usage.Fallback.Coverage

Evidence:
- `tests/test_account_usage_fallback.py` currently imports internal account-status models, fallback helpers, usage registry helpers, and `CodexAgent`.
- The file contains both pure fallback helper tests and Codex account-status integration tests.
- `tests/test_e2e_agent_accounts.py` already owns account registry, link, status, monitor config, and provider-specific account CLI scenarios.

Alignment:
- Move Codex usage fallback scenarios into `tests/test_e2e_agent_accounts.py` because that is the account workflow surface.
- Pure helper tests should be deleted unless the implementer finds a durable registry output contract that cannot be observed through Codex status.
- Reuse or move duplicated account setup helpers instead of copying JWT/auth setup again.

### Monitor.AutoPrime.Coverage

Evidence:
- `tests/test_agent_monitor_auto_prime.py` directly calls `AutoPrimeZeroLimitsWorkflow._eligible_periods`.
- It verifies trigger-specific period-key behavior:
  - zero usage uses the normal period key.
  - near-zero, sliding reset, and period-key churn use an `uninitialized` key.
  - the uninitialized key prevents repeated priming.

Alignment:
- Keep only compact contract coverage for durable period-key semantics.
- Prefer a small scenario-style test name and assertion shape over five private-method tests.
- If there is no public CLI path to observe period-key selection without an impractical amount of setup, a small contract test is acceptable.

### Shared.Test.Fixtures

Evidence:
- `_jwt`, `_auth_json`, and Codex register/link setup are duplicated or locally owned in account tests.
- Prior cleanup added shared helpers such as `captured_json`, `read_json_file`, `read_jsonl_file`, and environment isolation helpers in `tests/_helpers.py`.

Alignment:
- Move only truly repeated setup to `tests/_helpers.py`.
- Keep helper names domain-specific and readable; avoid a broad opaque harness.
- Prefer helpers that make e2e scenarios shorter without hiding the behavior under test.

## Execution.Plan

### Slice 1: Consolidate Codex Usage Fallback Scenarios

Status: implemented

Change:
- Move the durable Codex account-status fallback scenarios from `tests/test_account_usage_fallback.py` into `tests/test_e2e_agent_accounts.py` or a similarly named account e2e scenario file.
- Cover:
  - fresh app-server usage writes one usage registry record;
  - failed app-server usage falls back to cached registry payload;
  - failed app-server usage with no cache remains an error.

Path Exercised:
- Account registration/link setup.
- `CodexAgent.account_status()`.
- Usage registry file written under `AGENTOS_HOME`.

Observable Result:
- The account status result and usage registry JSONL records demonstrate the behavior without testing the fallback helper directly.

Validation:
- Run `uv run pytest tests/test_e2e_agent_accounts.py tests/test_account_usage_fallback.py` while this slice is in progress.
- After deletion or reduction, run the updated relevant test files.

### Slice 2: Delete Or Minimize Pure Fallback Helper Tests

Status: implemented

Change:
- Remove direct tests for `account_usage_registry_fallback(...)` if their behavior is now covered by Codex status scenarios.
- If one helper-level test remains, it must be framed as a durable output contract and should be compact.

Path Exercised:
- Prefer CLI/account-status boundaries over private helper imports.

Observable Result:
- `tests/test_account_usage_fallback.py` is deleted, or only contains a minimal justified contract test.

Validation:
- Search tests for private fallback helper imports:
  - `rg -n "account_usage_registry_fallback|AccountLimit|UsageOverTimeLimitData|AccountStatusError" tests`
- The remaining hits should be absent or intentionally justified by the kept contract.

### Slice 3: Reduce Auto-Prime Monitor Tests To Durable Contract Coverage

Status: implemented

Change:
- Replace five private-method tests in `tests/test_agent_monitor_auto_prime.py` with 1-2 compact tests that preserve durable period-key behavior:
  - zero usage produces a normal period key;
  - near-zero or moving-window trigger produces an `uninitialized` key and does not repeat once primed.
- Delete the old granular cases if the combined scenario covers the same durable distinction.

Path Exercised:
- `AutoPrimeZeroLimitsWorkflow` eligibility logic through the smallest available boundary.
- If no public boundary exists for period-key selection, direct workflow invocation is acceptable but should be explicitly contract-shaped.

Observable Result:
- Durable period-key semantics remain checked with less private-method granularity.

Validation:
- Run `uv run pytest tests/test_agent_monitor_auto_prime.py` while this slice is in progress.
- Search test names and imports to confirm the file no longer reads like a matrix of private helper cases.

### Slice 4: Final Suite And Budget Check

Status: implemented

Change:
- Run the full suite and measure test LOC/count.
- Confirm no deleted coverage was silently replaced with excessive fixture code.

Validation:
- `uv run pytest`
- `find tests -maxdepth 1 -type f -name 'test_*.py' -print0 | xargs -0 wc -l`
- `rg -n "^(from agentos|import agentos)" tests -g 'test_*.py'`

Acceptance:
- Full test suite passes.
- Test LOC decreases from the pre-slice state.
- Remaining production imports in tests are primarily CLI/boundary imports, except clearly justified contract coverage.

## Impl.Log

- 2026-05-19: Created Impl.Req for the second e2e test-consolidation pass. Scope is to remove or shrink `test_account_usage_fallback.py` and `test_agent_monitor_auto_prime.py` while preserving Codex usage fallback behavior and auto-prime period-key contract coverage.
- 2026-05-19: Implemented the remaining e2e consolidation. Deleted `tests/test_account_usage_fallback.py`; moved durable Codex usage behavior into `tests/test_e2e_agent_usage.py`; shared repeated Codex auth/register setup through `tests/_helpers.py`; reduced auto-prime period-key coverage from five granular private-method tests to two compact contract tests. Final validation: `uv run pytest` passed with 57 tests. Final measured test LOC: 2,106 total, largest file 365 LOC.
