# Account Management Rebuild — impl-req

## Impl.Abstract

- **scope:** rebuild the agentos account-management system to reflect the settled `Account.Management` design. Disconnect every *implicit* home-writing and auto-activation path; keep exactly two motion classes — **automatic capture** and **explicit operations** (activation, materialize). Introduce the `Auth.Method` class as the provider seam and the new nested registry model (`Provider.Account → Auth.Method → Auth.Data.Artifact`).
- **out of scope (this rebuild):** verification / ping (the only writer of `Valid.Credentials` evidence) — deferred to a later explicit path; freshness-based / conditional / automatic activation policies — only explicit set/rotate now; usage monitor's *usage* logic (only its implicit promote calls are touched); data migration of the old registry shape (we back it up now, migrate later); copilot stays metadata-only.
- **status:** not started. Design settled in-chat and indexed.
- **design source:** `agentos-pkg` index `Account.Management` (`agentos-md/skills/agentos-pkg/index/104-index.md`) + full sub-blocks in `agentos-md/skills/agentos-pkg/appendix/Account.Management-appendix.md`. That appendix is the authority for every concept named here (`Account.Model`, `Account.Model:Auth.Method`, `Account.Identity`, `Auth.Data`, `Auth.Data.Artifact`, `Account.Registry`, `Credential.Capture`, `Capture.Over.Materialization`, `Unknown.Account`, `Active.Auth.Artifact`, `Active.Auth.Artifact.Rotation`, `Active.Auth.Drift`, `Materializable.Account`, `Keep.Up.With.Rotation`).

## Impl.Index

### Why.Rebuild (the drift being corrected)

- the current system welds capture, home-sync, ping-verify, and active-promote into `reconcile`, and fires that bundle *implicitly* from runs, status, and the monitor.
- implicit home writes + implicit active-promote cause the refresh-token rotation races and account flipping documented in the session (`browser-br`, `~/.codex` tk/br flip).
- the design's core invariant: **`Capture.Over.Materialization`** — capture (read-out, append-only) is always-on and safe; home-writing (materialize) is explicit and yields. The rebuild makes the code match that invariant.

### Current.Implementation (inspected, to be cut)

- **implicit home-write / auto-activation triggers** (all to be severed):
  - codex run preflight — promote + materialize + reconcile-sync on *every* run: `codex/agent.py:185-261` (and `_sync_codex_materialized_home` `:343`, `:261`).
  - codex `account.status` — full `reconcile_codex_accounts` as a side effect (sync + active revert): `codex/account_status.py:54,183`.
  - claude run + status — `promote_verified_claude_ambient_auth_from_home`: `claude/agent.py:191-196`, `claude/account_status.py:354`.
  - monitor auto-prime — `promote_verified_*_from_home` for both providers: `agent/monitor/workflows.py:2311-2324`.
- **reconcile to be deleted/unbundled:** `claude/account_reconcile.py`, `codex/account_reconcile.py`. Salvage only the *capture* sub-logic (observe a home → archive artifact): see `_observed_artifacts_by_account` `codex/account_reconcile.py:636`, `append_artifact` (`agent/account_registry.py:147`). Drop `_sync_*_homes`, `_sync_account_for_home`, `_may_sync_home`, ping.
- **registry model today (old shape, to replace):** `agent/account_registry.py` — `accounts.json` carries a single account-level `auth_kind` + `active_artifact_id` + `account_id`; `artifacts.jsonl` append-only; `verifications.jsonl`; payloads in `artifacts/<id>.<kind>.json`. Provider builders: `claude/account_registry.py`, `codex/account_registry.py`, `copilot/account_registry.py`.
- **the load chokepoint:** `_validate_account_record` (`agent/account_registry.py:305-312`) hard-requires an account-level `auth_kind` on **every** `load_account`. The new shape moves `auth_kind` into `auth_methods`, so this single gate breaks all readers until updated — it is the one mandatory edit for the new shape to load, not a diffuse risk.
- **run-resolution is shape-safe:** `resolve_account_runtime_agent` (`agent/providers.py:64-95`) reads only `account_record["provider"]`/`["account"]`; `agent/monitor/config.py:179` only needs `load_account` to not throw; `agent/profile_scope.py` reads `AgentAccountContext`, not registry records. Once the validation gate accepts the new shape, these paths need no change.
- **materialize today (to simplify to a primitive):** `materialize_codex_account_to_home` `codex/account_registry.py:212` currently also triggers sync/reconcile internally; CLI `agent/commands.py:394`.

### Design.Target.Model (what the rebuilt code expresses)

- **`Auth.Method` class = the provider seam (backbone, build first).** One class per credential class (`auth-json`, `ambient-auth`, `gh-auth-token`). Capability set for this rebuild: `read/serialize Auth.Data`, `extract Account.Identity`, `materialize (write Auth.Data into a home)`. Class-level property `Materializable`. `verify` / `freshness` are reserved for later. Provider-specific extraction stays in the class (`General.Avoids.Specific` — the codex `chatgpt_account_id` claim, the `access_token`-not-`id_token` read, etc. live in the codex class).
- **Nested registry model.** `Provider.Account` (identity: provider, account alias, `provider_account_id` = normalized `Account.Identity`, convenience metadata) → `auth_methods` map keyed by `Auth.Method` name → each method holds an append-only `Auth.Data.Artifact` history (content-addressed) + one per-method `Active.Auth.Artifact` pointer. Secrets only in artifact payload files; never in index/ledger.
- **`Credential.Capture` (the one automatic path).** Detect `Auth.Data` in a live source → `Auth.Method.extract Account.Identity` → classify: known account ⇒ append under it; recognized-but-unmatched ⇒ append under the per-provider `Unknown.Account` bucket keeping the extracted id for later adoption. **Never rejects.** Identity check *classifies*, does not gate. Errors over unknown/mismatched credentials belong downstream, not at capture.
- **Activation = explicit registry operation only.** Set / rotate the per-method `Active.Auth.Artifact` pointer. Registry-only, never a home write. No automatic / verified-coupled promotion in this rebuild.
- **Materialize = explicit primitive only.** Write the active artifact's `Auth.Data` into a home via the `Auth.Method`. No read-back, no sync, no promote. Sole home-write path; sole caller is the explicit `agent accounts materialize` CLI.

### Decisions (locked)

- **Capture placement:** capture is cheap (mostly a quick read) and priority. Call it from as many account-involving agent commands as sensible — **`agent.run` at minimum** — plus other strategic points by good taste. It must be best-effort and never block/fail the host command.
- **Backup before touching data:** copy the existing `~/.agentos/accounts` tree to `~/.agentos/archive/<timestamp>/` (or similar) as a precondition slice. Migration of old→new shape is deferred; the backup is kept.
- **Transitional run/status behavior:** with implicit healing removed, a run/status against a stale/missing home **fails fast / uses the home as-is**. This is a temporary stopgap, **not** a design constraint — proper re-trigger points get designed later.
- **No.Legacy:** delete reconcile and the implicit triggers outright; do not keep compat shims (per `agentos-py/AGENTS.md`).

### Open.Feedback.To.Design

- `Credential.Capture` automatic-vs-explicit was the one design `meta` open question; this rebuild resolves it as **automatic, invoked from host commands** (not self-firing). Recorded here; the index `meta` line can be updated when this lands.

## Execution.Plan

> Vertical slices. Reach a testable endpoint fast (Slice 1 makes the new model real and capturable), then expand. `RED.GREEN` behavior tests at boundaries; no live provider calls in tests.

### Slice 0 — Backup existing registry (precondition)

- copy `~/.agentos/accounts` → `~/.agentos/archive/accounts-<timestamp>/` before any code that writes the registry runs. A one-shot, idempotent helper is acceptable.
- observable: archive copy exists; original untouched.
- check: behavior test on the backup helper (temp `AGENTOS_HOME`): given a populated accounts tree, the archive copy is created and byte-identical; re-run does not clobber an existing archive.

### Slice 1 — `Auth.Method` class + new nested registry model

- introduce the `Auth.Method` abstraction (base + codex/claude/copilot subclasses) with capabilities `read/serialize Auth.Data`, `extract Account.Identity`, `materialize`, plus class property `Materializable`.
- introduce the new `Account.Model` read/write layer: nested `Provider.Account → auth_methods → Auth.Data.Artifact` with per-method active pointer. New on-disk shape (fresh; old shape is backed up, not migrated).
- **update the load chokepoint** `_validate_account_record` (`agent/account_registry.py:305-312`) for the new shape — `auth_kind` is per-method, no longer an account-level required field. This unblocks every `load_account` caller (run resolution, monitor config) at once.
- path: registry load/store + `Auth.Method` resolution + `load_account` validation.
- observable: a `Provider.Account` can be created with one or more auth methods, each holding artifacts + an active pointer, round-tripping to disk; `provider_account_id` is populated from `Account.Identity` extraction; `load_account` accepts the new shape and `resolve_account_runtime_agent` still resolves provider/account unchanged.
- check: **RED.GREEN** tests — codex `Auth.Method.extract Account.Identity` returns the right UUID from a fixture `Auth.Data` (access_token claim, not id_token); registry round-trips the nested shape; `load_account` on a nested record validates (no account-level `auth_kind` demanded); secrets never appear in index/ledger surfaces.

### Slice 2 — `Credential.Capture` (the automatic path)

- build capture: source `Auth.Data` → extract identity → classify known/`Unknown.Account` → append `Auth.Data.Artifact` (content-addressed dedup). Salvage the observe-and-archive logic from the old reconcile; discard its sync/promote.
- wire one real call site end-to-end (`agent.run`, best-effort, non-blocking) to prove the automatic trigger.
- path: host command → capture → registry append.
- observable: running capture against a home with a known account appends/dedups under that account; against an unrecognized-but-identifiable credential, appends under the provider's `Unknown.Account`; capture never raises into the host command.
- check: **RED.GREEN** — known-account capture appends then dedups on repeat (`Keep.Up.With.Rotation`); orphan capture lands in `Unknown.Account` with its extracted id; a capture error is swallowed (host command still succeeds).

### Slice 3 — Explicit activation (set / rotate)

- registry-only operation to set/rotate the per-method `Active.Auth.Artifact`. No home write.
- path: CLI/registry op → active pointer update.
- observable: activating an artifact updates only the per-method pointer; nothing in any home changes.
- check: **RED.GREEN** — set active moves the pointer; rotate to another artifact moves it; no home file/Keychain mutation occurs (assert home untouched).

### Slice 4 — Explicit materialize primitive

- reduce materialize to: resolve active artifact → `Auth.Method.materialize` writes its `Auth.Data` into the target home. No read-back, sync, or promote. Keep `agent accounts materialize` as the sole caller.
- path: CLI → `Auth.Method.materialize` → home.
- observable: materialize writes the active artifact's `Auth.Data` into the home and does nothing else (no registry mutation, no sync).
- check: **RED.GREEN** — after materialize the home holds the active artifact's data; registry/active pointer unchanged; no reconcile/sync side effects (assert no extra writes).

### Slice 5 — Delete reconcile + sever implicit triggers

- delete `claude/account_reconcile.py`, `codex/account_reconcile.py` and the `reconcile` CLI/handlers (`agent/commands.py`).
- cut implicit triggers: codex run preflight (`codex/agent.py:185-261`), codex+claude `account.status` reconcile/promote (`codex/account_status.py:54,183`, `claude/account_status.py:354`), claude run promote (`claude/agent.py:191-196`), monitor promote (`agent/monitor/workflows.py:2311-2324`). Replace with nothing (or a best-effort capture call where sensible per the placement decision).
- path: run / status / monitor → no implicit home-write or promote.
- observable: a codex/claude run no longer materializes/syncs/promotes; `account.status` is read-only w.r.t. homes and active pointers; the monitor does not promote.
- check: **RED.GREEN** — run path produces no `materialized`/`synced`/`promoted` events and no home mutation; `account.status` leaves homes + active pointers unchanged; grep-level check that reconcile symbols are gone (`No.Legacy`).
- **test disposition (`No.Legacy`):** delete `tests/test_claude_account_reconcile.py`, `tests/test_codex_account_reconcile.py`; rewrite `tests/test_agent_run_account_preflight.py` (preflight no longer materializes), `tests/test_agent_monitor_auto_prime.py` (no promote), `tests/test_{claude,codex,copilot}_account_status.py` (status read-only); rewrite `tests/test_agent_account_registry.py` + `tests/test_claude_account_registry.py` for the new nested shape (Slice 1). Keep `tests/test_agent_account_events.py` if events survive.

### Risks / deviation triggers

- **Capture coupled to run correctness:** capture must be best-effort; if a capture failure can fail a run, that is a deviation — capture wraps and swallows. Trigger: any test where a capture error propagates.
- **Old-shape readers:** scoped to one chokepoint — `_validate_account_record` (account-level `auth_kind`). The run/monitor/profile read paths are confirmed shape-safe (see `Current.Implementation`). Trigger: a *new* runtime path found reading account-level `auth_kind`/`active_artifact_id`/`account_id` directly (the surviving ones are inside the modules being rebuilt).
- **Monitor usage dependence:** removing the promote calls must not break the usage *harvest reads*. `monitor/config.py:179` only needs `load_account` to succeed; verify the usage path (`agent/monitor/workflows.py` harvest) reads the active artifact through the new model, not via the deleted promote. Trigger: a monitor usage read that only worked because promote had just run.
- **Identity unextractable:** a method that can't extract `Account.Identity` cannot classify — capture must skip/park it without raising (it is the weak-binding case, out of scope to fully solve now). Trigger: a provider method with no stable id reached by capture.

### Acceptance signals

- A codex/claude `agent.run` performs **zero** implicit home writes, syncs, or active promotions; capture runs best-effort and records what the home holds.
- `reconcile` is gone; the only home-write is explicit `agent accounts materialize`; the only active change is explicit activation.
- New nested registry model round-trips; `Unknown.Account` collects identifiable orphans; `provider_account_id` extracted from the correct token claim.
- Existing registry backed up under `~/.agentos/archive/`.
- Full suite + ruff green; obsolete reconcile/trigger tests removed (`No.Legacy`).

## Impl.Log

- 2026-06-21: Impl-Req captured from the in-chat `Account.Management` design session (impl-designer, Interactive). Locked: unbundle reconcile (salvage capture only), `Auth.Method` class backbone, nested registry model, capture automatic via host commands (resolves the design's one open `meta` question), explicit-only activation + materialize, backup-then-defer-migration, transitional fail-fast run/status. Verification/ping and advanced activation policies explicitly deferred.
- 2026-06-21: deeper codebase scan refined the plan. Found the load chokepoint `_validate_account_record` (account-level `auth_kind`) gates every `load_account` — promoted to the mandatory Slice 1 edit. Confirmed run-resolution (`resolve_account_runtime_agent`), `monitor/config.py:179`, and `profile_scope.py` are shape-safe (read only provider/account), shrinking the "old-shape readers" risk to that one gate. Added concrete `No.Legacy` test disposition to Slice 5 (delete reconcile tests; rewrite preflight/auto-prime/status/registry tests).
