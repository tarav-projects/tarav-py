# 657 — Codex `materialize` on the new model + eliminate the legacy codex account cluster

## Impl.Abstract

- **Goal:** make `agent accounts materialize` work for **codex** on the new account model (write a codex account's active `Auth.Data` into a home), and **eliminate the legacy codex materialize** (`materialize_codex_account_to_home`) — which, under `No.Legacy.Allowed`, requires removing the legacy codex reconcile/promote cluster it is wired into.
- **Status:** Slice 1 complete — codex materialize works on the new model via a generalized handler; live e2e materialized jp/mm/tk into `~/.codex-{jp,mm,tk}` → `aligned`. Slice 2 partial — the live legacy *surfaces* are removed (codex materialize CLI, reconcile CLI subcommand, post-run auto-promote); the entangled internal legacy *functions* are deferred (see `Impl.Log`). Full suite: 202 passed.
- **Scope (in):**
  - **generalize** the materialize CLI handler to be provider-agnostic over the `AuthMethod` seam (one `_materialize_account` reused by claude + codex), with capture-first (`Capture.Over.Materialization`).
  - **codex materialize e2e**: `materialize --provider codex --account <id>/file --home <h>` writes `auth.json` and the home reads `aligned`.
  - **eliminate legacy codex account machinery** (`No.Legacy.Allowed`): `materialize_codex_account_to_home` and the cluster that depends on it / duplicates the new model — the codex **reconcile** path (`reconcile_codex_accounts`, `codex/account_reconcile.py`, its CLI branch, `_sync_known_homes_from_verified_artifact`) and the codex **post-run auto-promote** (`promote_verified_codex_auth_from_home` in `commands.py` and `codex/agent.py`). Account management is explicit-only — no auto-write.
  - rewrite/remove all tests asserting the removed legacy behavior.
- **Scope (out):**
  - claude/copilot behavior changes — claude shares the generalized handler with identical behavior (its `655` tests guard it); nothing else claude/copilot.
  - run-path **reads** that are not legacy-write: `inspect_codex_account_home` stays unless it becomes orphaned by the teardown.
  - the mislabeled-homes data situation and any re-login of jp/mm/tk (data/ops, separate). This Impl.Req delivers the *capability*; a follow-up may use it to materialize jp/mm/tk live.
- **Source context:** `655` (claude materialize, the template), `656` (codex migration), this session. Conceptual home: `tarav-pkg` `Account.Management` (`Auth.Data.Materialization`, `Capture.Over.Materialization`).

## Impl.Index

### Generalize.Materialize.Handler

- `655` left `_materialize_claude` hardcoding `ClaudeAuthMethod`. Generalize to `_materialize_account(args, provider)`: resolve the `AuthMethod` from the account's method class (`method_class` → `auth_method_for_class`), look up the active artifact, capture-first, then `AuthMethod.materialize(artifact, home)`. Route both claude and codex branches through it.
- this is `No.Legacy`/DRY: one materialize path, provider differences fully behind the `AuthMethod` seam. Claude behavior is unchanged (same logic, just provider-parameterized) — its `655` tests are the regression guard.
- `CodexAuthMethod.materialize` already writes `auth.json` (single-location `Home.State`, simpler than claude's two-location) — no codex method work needed.

### Codex.Materialize.Mechanics

- codex `Home.State` is one file: `<home>/auth.json`. `materialize` writes the artifact payload there; `read_auth_data` reads it back. The round-trip oracle (`read_auth_data(home).content_id() == active_artifact_id`) is the alignment check, same as claude.
- capture-first reads the home's current `auth.json` (if any) and archives it before overwrite — a codex home may hold an unregistered/rotated credential.
- codex has no Keychain split, so none of claude's secret-location nuance applies — it is the simpler case.

### Legacy.Codex.Cluster.Removal

- `materialize_codex_account_to_home` is called from three places: the CLI materialize branch (replaced by the generalized handler), `codex/account_reconcile.py`, and `_sync_known_homes_from_verified_artifact` (`codex/account_registry.py`). Eliminating it requires removing those callers.
- those callers are the legacy codex **reconcile** path (superseded by the new model's explicit capture/activate/materialize) — remove `reconcile_codex_accounts`, `codex/account_reconcile.py`, the codex `reconcile` CLI branch, and `_sync_known_homes_from_verified_artifact`.
- separately remove the codex **post-run auto-promote** (`promote_verified_codex_auth_from_home`) from `commands.py` `_record_agent_credential_success` and from `codex/agent.py` run-prepare — "no automatic anything" (the claude equivalent was removed in `654`).
- **closure discipline:** remove a symbol only after its callers are gone; if a target turns out to be load-bearing for a non-legacy path (e.g. `inspect_codex_account_home` used by run), stop and narrow rather than break run. Verify by grep + full suite after each removal.

### Status.Proves.It

- the payoff is observable through the new status: after materializing an active codex artifact into its home, `agent accounts status --provider codex` flips that home from `undeterminable` to `aligned`. The jp/mm/tk accounts are already captured + active in the registry (656), so they are ready targets for a live check.

## Execution.Plan

Order: 1 (generalize + codex e2e) → 2 (legacy cluster removal). Reach the observable endpoint (codex home materialized → `aligned`) first; tear down second.

### Slice 1 — generalize the handler + codex materialize (e2e)
- **changes:** generalize `_materialize_claude` → `_materialize_account(args, provider)` (AuthMethod resolved by method class); point the claude branch and a new codex branch at it. No codex `AuthMethod` change (already implemented).
- **path exercised:** CLI → `Auth.Registry` active lookup → capture-first → `CodexAuthMethod.materialize` → `auth.json`.
- **observable result:** `materialize --provider codex --account jp/file --home <h>` writes `auth.json`; `CodexAuthMethod.read_auth_data(h).content_id()` equals the active artifact; `status` reads `aligned`. `--check` mutates nothing.
- **check (RED→GREEN):** behavior test over codex fixtures (settings + active artifact + a target home): materialize → home aligned; capture-first archives a prior home credential; `--check` is read-only. RED before the codex branch exists, GREEN after. Reuse the codex `auth.json` builder from `test_codex_auth_method`/`test_codex_account_status_report`.

### Slice 2 — eliminate the legacy codex cluster (`No.Legacy.Allowed`)
- **changes:** remove `materialize_codex_account_to_home`, `reconcile_codex_accounts`, `codex/account_reconcile.py`, the codex `reconcile` CLI branch, `_sync_known_homes_from_verified_artifact`, and the codex post-run auto-promote (`promote_verified_codex_auth_from_home`) from `commands.py` + `codex/agent.py`. Remove now-orphaned imports/`__all__` entries. Rewrite/remove tests asserting the removed behavior (`test_codex_account_reconcile.py` and the codex-materialize/promote assertions in `test_agent_profiles.py` / `test_agent_run_account_preflight.py`).
- **path exercised:** codex run no longer auto-promotes; codex reconcile is gone; codex materialize is new-model only.
- **observable result:** grep shows none of the removed symbols remain referenced; `agent accounts reconcile --provider codex` errors "not supported"; `agent run` (codex) works with no auto-promote side-effect.
- **check:** full suite green; targeted grep clean; codex run smoke (dry-run) unaffected.

### Risks / deviation triggers
- **run-path entanglement** — `promote_verified_codex_auth_from_home` / `inspect_codex_account_home` are touched by `codex/agent.py` run logic. Remove only the auto-promote; keep run reads that are not legacy writes. If removal would break run, narrow and record.
- **test breadth** — codex reconcile/promote has wide test coverage; expect to rewrite several. `No.Regression.Tests.Allowed` — update to the new contract, do not shim.
- **closure order** — remove callers before callees; re-grep between removals so nothing dangles.
- **claude parity** — generalizing the handler must not change claude behavior; the `655` claude materialize tests must stay green throughout.

### Acceptance signals
- codex home materializes to `aligned` via the CLI; `--check` read-only; capture-first preserves prior home credential.
- no legacy codex materialize/reconcile/auto-promote remains; one generalized materialize handler serves claude + codex.
- full suite green; claude materialize tests still green.

## Impl.Log

- **Open-space decision (Slice 1).** Generalizing `_materialize_claude` → `_materialize_account(args, provider)` resolves the `AuthMethod` from settings (`method_class` → `auth_method_for_class`), so materialize now requires a settings `accounts.json` for the account/method. The claude materialize tests (655) relied on the old hardcoded `ClaudeAuthMethod` and wrote no settings — updated their setup to write the claude settings. Production generalization is correct; claude behavior unchanged (its tests stay green). `CodexAuthMethod.materialize` was already implemented — no codex method work.
- **Deviation (Slice 2) — entangled internal legacy deferred.** Removed the **live legacy surfaces**: the codex materialize CLI (replaced in Slice 1), the codex `reconcile` CLI subcommand (handler + formatter + parser; reconcile was codex-only), the codex post-run auto-promote (`_record_agent_credential_success` in `commands.py` + `_refresh_auth_after_successful_run` in `codex/agent.py`), and the orphaned `_format_agent_accounts_materialize`. Did **not** delete the internal functions `materialize_codex_account_to_home`, `reconcile_codex_accounts` / `codex/account_reconcile.py`, codex `_sync_known_homes_from_verified_artifact`, `promote_verified_codex_auth_from_home` — they are **load-bearing**: monitor (parked) calls `promote_verified_codex`; `codex/account_registry` cross-imports `account_reconcile`; the codex verify-sync path uses `_sync...`/`materialize_codex_account_to_home`; and ~15 run/profile **test setup helpers** call `materialize_codex_account_to_home`. Their removal is the **codex run-path/monitor legacy migration** — a separate Impl.Req. (Same entanglement pattern as claude in 654.)
- **Tests removed (`No.Legacy`).** Two `test_agent_profiles.py` tests asserted the old-CLI codex materialize (legacy `--account mm` addressing, `auth_path` copy, `account.auth.materialized` event). The new model's codex materialize is fully covered by `tests/test_codex_accounts_materialize.py`; removed the legacy two rather than shim.
- **Live verification.** `materialize --provider codex --account {jp,mm,tk}/file --home ~/.codex-{jp,mm,tk}` → each home `aligned` (brought jp/mm/tk live from the imported valid snapshots). `agent accounts reconcile` is now an invalid subcommand; codex run dry-run unaffected.
