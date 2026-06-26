# 658 — Eliminate the old credential system; only the new `agent accounts` CLI stays connected

## Impl.Abstract

- **Goal:** remove every path through the **old credential system** (capture/activate/materialize/register/reconcile/promote) anywhere in agentos, so the **only** connected surface to account credentials is the new `agent accounts {capture,activate,materialize,status}` CLI on the new model (`auth_registry` + `AuthMethod`). Disconnect the old consumers (monitor, run path); the deep re-integration of those onto the new model is a **later** redesign.
- **Status:** not started. The new model is built and proven (654–657); this is the teardown + the two missing CLI verbs.
- **Scope (in):**
  - **build** `agent accounts capture` + `agent accounts activate` (new model, generic over `AuthMethod`) — completes the connected surface.
  - **extract** the shared primitives the new model borrows from old files so the old files can be deleted.
  - **sever** the live old-credential wiring: the `register` CLI; monitor's auto-promote; monitor's `load_account` validation; run-path old credential reads.
  - **delete** the old credential modules/functions and rewrite/remove their tests (`No.Legacy.Allowed`).
- **Scope (out / keep):**
  - the **usage/status** system — `*/account_status.py` (agent/claude/codex/copilot) + `account_usage_fallback.py` — a *separate* live system (limits polling) the monitor and run path use. **Keep it.** `AccountIdentity`/`AccountStatus` (in `agent/account_status.py`) stay (shared types).
  - the **re-integration** of monitor auto-capture and run-path credential validation onto the new model — explicitly deferred ("redesign the integration back again"). This Impl.Req *disconnects*; a follow-up reconnects.
- **Source context:** this session's teardown inventory; the new model lives in `auth_registry.py`, `auth_method*.py`, `account_status_report.py`, `codex/claude auth_method.py`. Conceptual home: `agentos-pkg` `Account.Management` (the three primitive operations).

## Impl.Index

### Two.Systems.Untangle

- under "account" there are **two** systems: the **credential** system (capture/activate/materialize/register/reconcile/promote — OLD, to delete) and the **usage/status** system (limits polling — KEEP, live). The teardown targets only the credential system.
- they share three primitives the new model borrows from old files; these must be **extracted** before the old files can be deleted (see `Shared.Primitives.Extraction`).
- `account_status.py` (all providers) is usage/status — left intact, including `AccountIdentity`/`AccountStatus`.

### Shared.Primitives.Extraction

- the new model currently reaches into old files; move these so old files become deletable:
  - `auth_registry` imports `account_provider_root` (+ path helpers `account_registry_root`, `archive_account_registry`) from `agent/account_registry.py` → move into `auth_registry` (or a small `agent/account_paths.py`).
  - `claude/auth_method` imports the Keychain readers/writer (`read_claude_secure_storage_info`, `claude_keychain_service_names`, `write_claude_secure_storage`, `DEFAULT_CLAUDE_KEYCHAIN_TIMEOUT_SEC`) from `claude/account_registry.py` → move into `claude/auth_method` (it is the sole new consumer).
  - `AccountIdentity` stays in `agent/account_status.py` (kept).
- after extraction, the new model imports nothing from any old credential file.

### New.Surface.Completion

- `agent accounts capture` (new): read a `--home` via the provider `AuthMethod` → `extract_identity` → resolve to account (or `Unknown.Account`), method by class → `store_artifact` + `append_capture` (dedup). Pure archival, read-only on the home (`Capture.Over.Materialization`). The reverse class→method lookup (`auth_registry.method_for_class`) is added here.
- `agent accounts activate` (new): `--provider --account <id>/<method> --artifact <id>` → `set_active`. Pure registry pointer move. (Explicit `--artifact` in V1.)
- with these, the connected surface is `capture` / `activate` / `materialize` / `status` — all on `auth_registry`, no old-registry path.

### Severance.Map

- **CLI `register`** — remove the `register` subcommand (parser + `_cmd_agent_accounts_register` + `register_codex_account_from_auth_file` / `register_copilot_account` call sites). Old capture entry; the new `capture` replaces it.
- **Monitor auto-promote** — remove `_record_prime_ping_credential_success`'s promote (the only remaining live caller of `promote_verified_*`). Auto-prime keeps pinging; credential auto-capture is **disconnected** (re-added as a new-model workflow in the deferred redesign).
- **Monitor `load_account`** — `config.py` validates targets with `load_account` (broken on new shape). Repoint to a new `auth_registry.account_exists(provider, account_id)`, parsing the migrated `account/method` target into its account-id.
- **Run path** — `codex/agent.py` `inspect_codex_account_home` and `claude/agent.py` `account_registry` calls (home-current / account-scope validation) read the old registry. Repoint to a minimal new-model read (`AuthMethod.read_auth_data` + `auth_registry`) **or** disconnect the old call if the validation is non-essential — the bridge must not pull in old-registry code. Keep run working; do not redesign the policy here.

### Old.Modules.Deletion

- delete outright: `agent/account_model.py`, `agent/account_reconcile.py`, `claude/account_reconcile.py`, `codex/account_reconcile.py`.
- delete the old credential functions from `agent/account_registry.py` (`load_account`, `upsert_account`, `write_accounts`, `load_accounts`, `read_artifacts`, `append_artifact`, `record_account_event`, …) and from `claude/`/`codex/`/`copilot/account_registry.py` (`register_*`, `promote_verified_*`, `materialize_*`, `*_sync_*`, `inspect_codex_account_home`, `read_codex_auth_info` if unused by the new model). Keep only what the kept usage/status system still needs.
- **closure discipline:** delete callers before callees; re-grep between deletions; nothing in the kept usage/status system or the new model may dangle.

### Tests.Realignment

- the old credential system has wide test coverage (`test_*_account_reconcile.py`, `test_agent_account_model.py`, register/materialize/promote assertions in `test_agent_profiles.py` / `test_agent_run_account_preflight.py`). Rewrite to the new model or remove (`No.Regression.Tests.Allowed`, `No.Legacy.Allowed`) — do not shim. New behavior is covered by `test_agent_auth_registry.py`, `test_*_account_status_report.py`, `test_*_accounts_materialize.py`, and the new capture/activate tests.

## Execution.Plan

Order: extract → build → sever → delete. Keep the suite green between slices; reach the new-surface endpoint (capture+activate working) before tearing down.

### Slice 1 — extract shared primitives
- **changes:** move path helpers into `auth_registry` (or `account_paths.py`) and the claude Keychain readers/writer into `claude/auth_method`; repoint the new model's imports. No behavior change.
- **observable result:** the new model imports nothing from any `*account_registry.py`/`*account_reconcile.py`/`account_model.py`.
- **check:** grep shows zero new-model imports from old credential files; full suite green (pure move).

### Slice 2 — build `capture` + `activate` CLI (new surface)
- **changes:** add the two subcommands + `auth_registry.method_for_class`; generic over `AuthMethod`.
- **path exercised:** CLI → `AuthMethod.read_auth_data`/`extract_identity` → `auth_registry` store/append/set_active.
- **observable result:** `capture --provider codex --home <h>` archives the home's `Auth.Data` filed under its real account; `activate --provider codex --account jp/file --artifact <id>` sets the active pointer; `status` reflects both.
- **check (RED→GREEN):** behavior tests for capture (files by identity, dedup, `Unknown.Account` for an orphan) and activate (pointer move); RED before the subcommands exist.

### Slice 3 — sever the old wiring
- **changes:** remove the `register` subcommand; remove monitor `_record_prime_ping_credential_success` promote; repoint monitor `load_account` → `auth_registry.account_exists`; repoint/disconnect run-path `inspect_codex_account_home` / claude `account_registry` reads off the old registry.
- **observable result:** `agent accounts register` is gone; monitor config validates on the new settings; monitor auto-prime runs with no old-registry call; codex/claude run (dry-run) works with no old-credential read.
- **check (RED→GREEN where behavior is asserted):** monitor config-load test over the migrated `account/method` targets passes; a run/ping smoke (dry-run) green; grep shows no live entry point importing an old credential function.

### Slice 4 — delete old modules + realign tests
- **changes:** delete the old credential modules/functions per `Old.Modules.Deletion`; rewrite/remove their tests.
- **observable result:** grep finds no references to the deleted symbols outside their own (removed) files; the kept usage/status system + new model still import cleanly.
- **check:** full suite green; targeted grep clean; `agent accounts {capture,activate,materialize,status}` all work live; usage/limits monitor still loads.

### Risks / deviation triggers
- **usage/status entanglement** — `account_status.py` reads home credentials to call the usage API; it is KEEP. Do not delete credential helpers it still needs; if a "credential" helper turns out to be load-bearing for usage, keep it and note it.
- **run-path validation loss** — disconnecting `inspect_codex_account_home` may drop a home-current check; repoint to a minimal new-model read rather than silently dropping the policy. If it can't be done minimally, narrow and record (the policy redesign is deferred).
- **monitor parked** — monitor is otherwise parked; this Impl.Req touches only its credential wiring (`promote`, `load_account`), not its usage workflows.
- **test breadth** — expect to remove/rewrite many provider credential tests; closure discipline + re-grep between deletions.

### Acceptance signals
- the only code path to account credentials is `agent accounts {capture,activate,materialize,status}` on `auth_registry`; no old-registry/reconcile/promote/register/materialize path remains reachable.
- usage/status system intact; monitor still loads + tracks limits; run works.
- full suite green.

## Impl.Log

- (empty — implementer appends deviations, open-space decisions, blockers; nothing diff-visible)
