# 658 — Eliminate the old credential system; only the new `agent accounts` CLI stays connected

## Impl.Abstract

- **Goal:** remove every path through the **old credential system** (capture/activate/materialize/register/reconcile/promote) anywhere in agentos, so the **only** connected surface to account credentials is the new `agent accounts {capture,activate,materialize,status}` CLI on the new model (`auth_registry` + `AuthMethod`). Disconnect the old consumers (monitor, run path); the deep re-integration of those onto the new model is a **later** redesign.
- **Status:** Slices 1–3 + 3b landed (new surface complete; register CLI + monitor auto-promote + run surface all severed; suite 202). **Next:** Slice 4a — repoint the kept usage/status system (`account_status.py`) off the old registry (4 shallow couplings, each with a new-model equivalent), then Slice 4b — delete the now-orphaned old credential modules.
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
- **Run path — DISCONNECT (decided), do not repoint.** The run flow has exactly three reads/writes into the old credential surface; **sever all three** so the run launches the provider CLI against the home as-is. `_check_account_scope` (config-only `validate_account_override`) and `account_status()` (usage; not called during run) are **kept** — they are not the credential surface. Re-integration onto the new model is a later redesign. The three:
    1. **codex home-current validation** — `codex/agent.py` `prepare_codex_run` → `inspect_codex_account_home` + `_validate_home_current_codex_run` (+ helpers). Remove; codex run uses the home as-is.
    2. **claude token env-injection** — `claude/agent.py` `prepare_run` → `has_claude_oauth_token_kind` + `load_claude_oauth_token_for_account` → `CLAUDE_CODE_OAUTH_TOKEN` env. Make `prepare_run` return empty. **The `oauth-token-env` method is unused live** (no profile/monitor/config references `*/token`; only `br` even declares it). Token-method run breaks until redesigned — accepted.
    3. **claude post-run auto-promote** — `claude/agent.py` `_refresh_ambient_auth_after_successful_run` + its call site. Remove (last claude auto-capture; "no automatic").
  - after all three, `codex/agent.py` and `claude/agent.py` no longer import/read/write the old `account_registry` credential functions — clearing the last live readers of `inspect_codex_account_home`, the claude token loaders, and the claude post-run promote.

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

### Slice 3b — disconnect the run surface (decided)
- **changes:** sever the three run-path credential touchpoints (see `Severance.Map`): codex `prepare_codex_run` home-current validation; claude `prepare_run` token env-injection (→ empty result); claude `_refresh_ambient_auth_after_successful_run` post-run promote (+ call site). Keep `_check_account_scope` and `account_status()`. Remove now-orphaned imports/helpers in `codex/agent.py` / `claude/agent.py`.
- **path exercised:** `agent run` / `agent ping` (codex + claude) — launch against the home as-is, no account/auth-registry read or write.
- **observable result:** a codex run/ping and a claude (browser) run/ping work with no old-`account_registry` call; `codex/agent.py`+`claude/agent.py` import no old credential function; token-method claude run no longer injects env (unused).
- **check (RED→GREEN where behavior is asserted):** rewrite the codex home-current preflight tests and any claude token-run / auto-promote tests to the "runs home as-is, no registry" contract; a run/ping dry-run smoke is green; grep shows no run-path import of an old credential function.

### Slice 4a — repoint the usage/status system off the old registry
- **changes:** the kept `account_status.py` (all 3 providers) couples to the old registry at four shallow points, each with a direct new-model equivalent:
    - `load_account` → the **expected identity** for the identity-match → read the account's `identity` from `auth_registry.load_settings` (new settings).
    - claude `read_claude_secure_storage` → extract the keychain cluster to `claude/keychain.py`; `account_status` (and `ClaudeAuthMethod`) import it from there.
    - codex `inspect_codex_account_home` → the home's identity/classification → `CodexAuthMethod.read_auth_data` + `extract_identity` (already exists).
    - copilot `record_copilot_account_verified` → **drop** (the old verifications ledger is gone from the new model).
- **observable result:** `account_status.py` (all 3) import nothing from the old credential registry; `agent accounts status` / monitor limits-tracking still produce identity-match + usage as before.
- **check (RED→GREEN where behavior is asserted):** existing account_status tests stay green (rewrite only those asserting the old verification write / old record shape); full suite green; live `status` unaffected.

### Slice 4b — delete the now-orphaned old modules + realign tests
- **changes:** with run/CLI/monitor/usage all off the old registry, delete the old credential modules/functions per `Old.Modules.Deletion` (`account_model.py`, `*_reconcile.py`, the register/promote/materialize/sync/inspect credential funcs in `*_registry.py`); untangle reconcile↔registry cross-imports; rewrite/remove their tests.
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

- **Scope deviation — staged the teardown.** The full Impl.Req (extract 2 clusters + 2 CLI verbs + sever 3 subsystems + delete ~9k lines across 8 files + rewrite ~dozens of provider credential test setups) is too large to land safely-verifiable in one autonomous pass. Executed the high-value, suite-green core: **Slice 1** path-helper extraction (`account_paths.py`; `auth_registry` repointed; old `account_registry` re-exports), **Slice 2** `capture`+`activate` CLI (+ `auth_registry.method_for_class`/`account_exists`, `auth_method_registry.auth_methods_for_provider`), **Slice 3** clean severances (remove `register` subcommand+handler; remove monitor `_record_prime_ping_credential_success` promote; repoint monitor `load_account` → `auth_registry.account_exists`). **Deferred:** the claude-keychain extraction, the run-path old-registry reads (`codex/agent.py` `inspect_codex_account_home`, `claude/agent.py` registry calls), and the **Slice 4 mass deletion** — entangled with ~dozens of provider test setups (`register_*`/`materialize_*` helpers) and the kept usage/status system; needs its own focused pass.
- **Latent breakage found + fixed (open-space).** The profile→`account/method` migration done earlier this session had broken the **live** config loaders (which path-validate account names): monitor `_load_targets` (`_required_string`) and the agent-context `_load_agent_account_context` both rejected `jp/file`. Both now parse the account-id (`<account-id>/<method>` → `<account-id>`); status keeps using the raw `account/method` from profiles for its candidate gate (unaffected). Live monitor config now loads (3 workflows).
- **Tests rewritten (`No.Legacy`).** Two `test_agent_monitor_auto_prime.py` tests asserted the removed monitor auto-promote (`verifications.jsonl`, source `monitor.auto_prime`); rewritten to assert no auto-promotion.
- **Goal status (honest).** New surface `capture/activate/materialize/status` complete and live-verified; `register` CLI + monitor auto-capture severed. NOT yet fully "only the new CLI connected" — the **run path still reads the old registry** (deferred), and the old credential modules/functions still exist (still used by test setups; deferred deletion). The clearest old *write* paths are gone; the remaining old *reads* + dead code are the next focused pass.
- **Live verification.** `capture --provider codex --home ~/.codex-br` archives (dedup); `activate --provider codex --account br/file --artifact <id>` sets the pointer and rejects a missing artifact; monitor config loads on the migrated `account/method` targets.
- **Slice 3b — run surface disconnected (done).** Severed the three run-path touchpoints: codex `prepare_codex_run` home-current validation (+ the dead `_validate_home_current_codex_run` helper cluster), claude `prepare_run` token env-injection (→ empty result), claude `_refresh_ambient_auth_after_successful_run` post-run promote (+ call site + `_format_claude_preamble_line`). `codex/agent.py` & `claude/agent.py` now import no old `account_registry` credential function; `_check_account_scope` (config) and `account_status()` (usage) are kept. Removed 4 tests asserting the disconnected behaviors (codex home-current ×2, claude token env-injection, claude post-run promote). Live: codex & claude dry-run launch against the home as-is with no credential preamble.
- **Latent effect.** With the run surface severed, the old credential *capture/activate/materialize/register/reconcile/promote* paths have no live consumer.
- **Slice 4 split (4a repoint → 4b delete).** The **kept usage/status system** (`account_status.py`, all 3 providers) couples to the old registry at four *shallow* points, each with a direct new-model equivalent (see Slice 4a) — so the fix is a modest repoint, not a rewrite: expected-identity → `auth_registry` settings; claude token → extracted `claude/keychain.py`; codex home read → `CodexAuthMethod`; copilot verification write → drop. After the repoint the old modules are genuinely orphaned and deletable (4b).
