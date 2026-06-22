# Account Management Rebuild — impl-req

## Impl.Abstract

- **scope:** rebuild the agentos account-management system to reflect the settled `Account.Management` design. Disconnect every *implicit* home-writing and auto-activation path; keep exactly two motion classes — **automatic capture** and **explicit operations** (activation, materialize). Introduce the `Auth.Method` class as the provider seam and the new nested registry model (`Provider.Account → Auth.Method → Auth.Data.Artifact`).
- **out of scope (this rebuild):** verification / ping (the only writer of `Valid.Credentials` evidence) — deferred to a later explicit path; freshness-based / conditional / automatic activation policies — only explicit set/rotate now; usage monitor's *usage* logic (only its implicit promote calls are touched); data migration of the old registry shape (we back it up now, migrate later); copilot stays metadata-only.
- **status:** in progress. **Phase A complete (Slices 0–5, all green)** — the new subsystem is built additively and isolated; full suite 181 passed, ruff clean, zero live behavior touched. **Phase B (Slices 6–8, per-provider cutover) and Phase C (Slice 9, teardown) remain** — the integration work, recommended as focused follow-up passes (see `Impl.Log` 2026-06-21 executer Phase A).
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

### Strangler.Buildout (re-slicing that fixes the big-bang)

- **observed drift:** the first slicing (old Slices 1–5) was a big-bang cutover — changing the on-disk shape under the old code broke every provider registry, `account_status`, `reconcile`, the run preflight, the monitor, and ~10 test files at once, with no intermediate green state (executer deviation, `Impl.Log` 2026-06-21).
- **fix — strangler buildout:** build the new subsystem as new, isolated modules first (Phase A) — additive, nothing live imports them, every slice green. Then cut over **one provider at a time** (Phase B). Tear down the dead old paths only once unreferenced (Phase C).
- **the one enabling edit:** relax `_validate_account_record` up front (Slice 1) so old- and new-shape records both load — this lets migrated and not-yet-migrated providers coexist on the shared loader during Phase B.
- **why per-provider works:** `accounts/<provider>/` storage is provider-scoped, so flipping codex to the new shape cannot affect claude/copilot files; cross-provider code (`reconcile`, monitor promote) is removed last, after every provider is off it.
- **`No.Legacy` still holds at the end:** the coexistence is transitional scaffolding *within* the execution; Phase C deletes the old reconcile/promote/sync, and the old shape is archived (Slice 0), not kept.

### Decisions (locked)

- **Capture placement:** capture is cheap (mostly a quick read) and priority. Call it from as many account-involving agent commands as sensible — **`agent.run` at minimum** — plus other strategic points by good taste. It must be best-effort and never block/fail the host command.
- **Backup before touching data:** copy the existing `~/.agentos/accounts` tree to `~/.agentos/archive/<timestamp>/` (or similar) as a precondition slice. Migration of old→new shape is deferred; the backup is kept.
- **Transitional run/status behavior:** with implicit healing removed, a run/status against a stale/missing home **fails fast / uses the home as-is**. This is a temporary stopgap, **not** a design constraint — proper re-trigger points get designed later.
- **No.Legacy (end state):** the *final* tree has no reconcile, no implicit triggers, no compat shims (per `agentos-py/AGENTS.md`). The only transitional tolerance is the shape-relaxed loader (Slice 1), which exists solely to keep Phase B green and is not a permanent dual-shape shim — once all providers are migrated, only the new shape is produced.

### Open.Feedback.To.Design

- `Credential.Capture` automatic-vs-explicit was the one design `meta` open question; this rebuild resolves it as **automatic, invoked from host commands** (not self-firing). Recorded here; the index `meta` line can be updated when this lands.

## Execution.Plan

> **Strangler buildout** (see `Strangler.Buildout`). Phase A builds the new subsystem as new, isolated modules — every slice green because nothing live imports them yet. Phase B cuts over **one provider at a time**. Phase C tears down the dead old paths once unreferenced. `RED.GREEN` behavior tests at boundaries; no live provider calls in tests. **No slice may leave the tree red.**

### Slice 0 — Backup existing registry (precondition)

- copy `~/.agentos/accounts` → `~/.agentos/archive/accounts-<timestamp>/` before any code that writes the registry runs. A one-shot, idempotent helper is acceptable.
- observable: archive copy exists; original untouched.
- check: behavior test on the backup helper (temp `AGENTOS_HOME`): given a populated accounts tree, the archive copy is created and byte-identical; re-run does not clobber an existing archive.
- status: **done** — `archive_account_registry(label=...)` in `agent/account_registry.py` (statuses `archived`/`exists`/`empty`); tests in `tests/test_agent_account_registry.py` (green).

### Phase A — build the new subsystem (additive, isolated, every slice green)

> New modules nothing live imports yet. Exercised only via isolated tests (temp `AGENTOS_HOME`, test-double `Auth.Method`s). The live registry stays old-shape and untouched throughout Phase A.

#### Slice 1 — `Auth.Method` seam + relax the load gate

- introduce the `Auth.Method` base + capability protocol (`read/serialize Auth.Data`, `extract Account.Identity`, `materialize`; class property `Materializable`) — abstract, no provider specifics yet.
- **relax** `_validate_account_record` (`agent/account_registry.py:305-312`) to accept records **with or without** an account-level `auth_kind` (old and new shapes both load). One shared edit, done first, so migrated and not-yet-migrated providers coexist on the loader through Phase B.
- observable: the abstract `Auth.Method` + a test double resolve their capability surface; `load_account` accepts both an old record (account-level `auth_kind`) and a new one (none).
- check: **RED.GREEN** — loader accepts both shapes; a fake `Auth.Method` satisfies the protocol. No live path changes.
- status: **done** — `agent/auth_method.py` (`AuthData` content-addressed + `AuthMethod` ABC); `_validate_account_record` shape-tolerant. Tests `tests/test_agent_auth_method.py` + loader test (green; 45-test account/reconcile sweep green).

#### Slice 2 — new nested `Account.Model` read/write layer

- provider-agnostic nested model: `Provider.Account → auth_methods → Auth.Data.Artifact` + per-method `Active.Auth.Artifact` pointer; content-addressed artifacts; secrets only in payload files. New read/write functions (not the old `upsert_account`). Not imported by any live path.
- observable: a nested account round-trips to disk; an artifact dedups by content hash; the per-method active pointer sets/reads.
- check: **RED.GREEN** — nested round-trip; dedup; secrets never in index/ledger surfaces. Isolated temp home.
- status: **done** — `agent/account_model.py` (composes existing storage primitives, not `upsert_account`); `tests/test_agent_account_model.py` green.

#### Slice 3 — `Credential.Capture` primitive (provider-agnostic core)

- core capture: given an extracted `Account.Identity` + payload from an `Auth.Method`, classify known vs `Unknown.Account` and append. Never rejects — classifies. Salvage the observe-and-archive intent from the old reconcile capture sub-logic (`codex/account_reconcile.py:636`); discard sync/promote. Driven by a test-double method.
- observable: known-id capture appends then dedups under the account; unmatched-but-identified lands in the provider `Unknown.Account` keeping the id; a capture error is swallowed.
- check: **RED.GREEN** — the three behaviors above with a fake `Auth.Method`.
- status: **done** — `agent/credential_capture.py` (`capture_from_home` + `_safe`; `UNKNOWN_ACCOUNT` bucket; orphan keeps `extracted_provider_account_id`); `tests/test_agent_credential_capture.py` green.

#### Slice 4 — explicit activation primitive

- registry-only set/rotate of the per-method `Active.Auth.Artifact`. No home write.
- observable: set moves the pointer; rotate moves it; no home mutation.
- check: **RED.GREEN** — set/rotate update only the pointer; assert no home touched.
- status: **done** — `set_active_artifact` in `agent/account_model.py` (set+rotate, validates artifact known, registry-only); tests in `tests/test_agent_account_model.py` green.

#### Slice 5 — explicit materialize primitive

- `Auth.Method.materialize`: write a given artifact's `Auth.Data` into a home. Pure write — no read-back, sync, or promote.
- observable: materialize writes the payload into the home and nothing else.
- check: **RED.GREEN** — home holds the payload after; registry/active pointer unchanged; no other writes. Driven by a test-double method.
- status: **done** — `agent/credential_materialize.py` (`materialize_active`: resolve active → `Auth.Method.materialize`, pure write); `tests/test_agent_credential_materialize.py` green.

### Phase B — cut over one provider at a time (each provider green; others untouched)

> Per-provider because `accounts/<provider>/` storage is provider-scoped — flipping one provider's shape cannot affect another's files, and the shared loader already tolerates both shapes (Slice 1). For each provider: implement its `Auth.Method` subclass, route its registry/status/run paths through the new model + `Credential.Capture`, drop its implicit promote/sync/materialize, and rewrite that provider's tests. After each slice the migrated provider no longer imports `reconcile`.

#### Slice 6 — codex cutover

- codex `Auth.Method` subclass: identity from the **access_token `chatgpt_account_id` claim** (not id_token), read/serialize `auth.json`, materialize.
- route codex registry + `account_status` + run preflight (`codex/agent.py:185-261`) through the new model; wire `Credential.Capture` into the codex run path (best-effort); **remove** codex promote (`:187`), implicit materialize/sync (`:226-261`), and the `reconcile_codex_accounts` side effect in `codex/account_status.py:54,183`.
- observable: a codex run captures (best-effort) and performs no implicit materialize/sync/promote; codex `account.status` mutates no home or pointer; codex accounts persist in the new nested shape.
- check: **RED.GREEN** — codex run emits no `materialized`/`synced`/`promoted` and no home mutation; capture appends; status leaves home+pointer unchanged. Rewrite `tests/test_codex_account_*` and the codex parts of `tests/test_agent_run_account_preflight.py`. codex no longer imports `codex/account_reconcile.py`.

#### Slice 7 — claude cutover

- claude `Auth.Method` subclass (Keychain-backed `ambient-auth`: identity + read/serialize + materialize).
- route claude registry + `account_status` + run (`claude/agent.py:191-196`) through the new model + capture; remove the `promote_verified_claude_ambient_auth_from_home` calls (run + status `claude/account_status.py:354`).
- observable / check: **RED.GREEN** mirror of Slice 6 for claude; rewrite `tests/test_claude_account_*`. claude no longer imports `claude/account_reconcile.py`.

#### Slice 8 — copilot cutover

- copilot `Auth.Method` subclass: `gh-auth-token`, **non-materializable** (reference-only). Route copilot status/registry through the new model as a metadata-only account (no stored secret, no artifact payload).
- observable / check: **RED.GREEN** — a copilot account exists with a non-materializable method and no payload; status read-only. Rewrite `tests/test_copilot_account_status.py`.

### Phase C — teardown (dead paths removed; green)

#### Slice 9 — delete reconcile + monitor promote + dead old code

- with all providers migrated, `reconcile_*_accounts` is unreferenced: delete `claude/account_reconcile.py`, `codex/account_reconcile.py`, the `reconcile` CLI/handlers (`agent/commands.py`), and `tests/test_{claude,codex}_account_reconcile.py`.
- remove the monitor promote calls (`agent/monitor/workflows.py:2311-2324`); rewrite `tests/test_agent_monitor_auto_prime.py` (no promote). Confirm the `monitor/config.py` usage-harvest reads active via the new model.
- remove now-dead old-registry write paths (old `materialize_*`/`promote_*`/`_sync_*_homes` helpers superseded by the primitives); rewrite `tests/test_agent_account_registry.py` for the new shape; drop `tests/test_claude_account_registry.py` content that targeted the old shape.
- observable: `reconcile` and all implicit promote/sync/materialize are gone; the only home-write is explicit `agent accounts materialize`; the only active change is explicit activation.
- check: **RED.GREEN** + `No.Legacy` grep — no `reconcile` / `promote_verified` / `_sync_*_homes` symbols remain; monitor does not promote; full suite green.

### Risks / deviation triggers

- **Shared loader must stay shape-tolerant through Phase B:** if a not-yet-migrated provider or a shared reader trips on a mixed old/new registry, the Slice-1 relaxation is incomplete. Trigger: any `load_account` failure on a mixed registry during Phase B.
- **Capture coupled to run correctness:** capture is best-effort; a capture failure must never fail a run. Trigger: a test where a capture error propagates.
- **Monitor usage dependence:** removing promote (Slice 9) must not break usage *harvest reads*; `monitor/config.py:179` only needs `load_account` to succeed. Trigger: a monitor usage read that only worked because promote had just run.
- **Identity unextractable:** a method that can't extract `Account.Identity` must skip/park without raising (weak-binding case, out of scope to fully solve now). Trigger: a provider method with no stable id reached by capture.

### Acceptance signals

- **Every slice left the tree green; no big-bang break** (the realignment goal).
- codex/claude `agent.run` performs **zero** implicit home writes, syncs, or active promotions; capture runs best-effort.
- `reconcile` is gone; the only home-write is explicit `agent accounts materialize`; the only active change is explicit activation.
- New nested model round-trips; `Unknown.Account` collects identifiable orphans; `provider_account_id` from the correct token claim.
- Existing registry backed up under `~/.agentos/archive/`.
- Full suite + ruff green; obsolete reconcile/trigger tests removed (`No.Legacy`).

## Impl.Log

- 2026-06-21: Impl-Req captured from the in-chat `Account.Management` design session (impl-designer, Interactive). Locked: unbundle reconcile (salvage capture only), `Auth.Method` class backbone, nested registry model, capture automatic via host commands (resolves the design's one open `meta` question), explicit-only activation + materialize, backup-then-defer-migration, transitional fail-fast run/status. Verification/ping and advanced activation policies explicitly deferred.
- 2026-06-21 (executer, Autonomous): Slice 0 implemented and green (`archive_account_registry`, 2 tests; full account-registry suite 6 passed, ruff clean). Git checkpoint `52f17dc` on `main` captured the repo as found (it also swept up unrelated pre-existing edits to monitor/reconcile from prior session work).
  - **DEVIATION / staging decision:** Slices 1–5 are not independent vertical slices — they are one big-bang cutover. Slice 1's nested-shape change (`auth_methods` map, per-method active pointer) breaks every provider registry, `account_status`, `reconcile`, the run preflight, the monitor, and ~10 test files *at once*; there is no intermediate green state until the whole cutover completes. Executing that volume in a single autonomous pass would produce a large unverifiable change and a broken tree, violating `Vertical.Slice` / `No.Regression`. Stopped at the green Slice-0 floor and surfaced for staged execution rather than bulldozing. Recommend running Slices 1→5 as focused follow-up passes (Slice 1 = `Auth.Method` classes + nested model + relax the `_validate_account_record` gate, built additively to stay green before the Slice-5 cutover).
- 2026-06-21 (executer, Autonomous, Phase A): Slices 1–5 implemented test-first, all green; full suite **181 passed**, ruff clean. New isolated modules: `agent/auth_method.py`, `agent/account_model.py`, `agent/credential_capture.py`, `agent/credential_materialize.py`; `_validate_account_record` relaxed to accept both shapes. **No live path touched** — the strangler buildout held (every slice green, no big-bang). Phase B/C (provider cutovers + teardown) are the integration work and are left as focused follow-up passes per the redesign; the new subsystem they consume is now complete and proven. No deviations.
- 2026-06-21 (impl-designer realignment): re-sliced the plan as a `Strangler.Buildout` to fix the executer's big-bang wall. Old Slices 1–5 flipped the on-disk shape under live code with no intermediate green state. New shape: Phase A (Slices 1–5) builds the new subsystem as isolated, additive modules (test-only, live registry untouched); Phase B (Slices 6–8) cuts over one provider at a time on a shape-tolerant loader; Phase C (Slice 9) deletes reconcile/monitor-promote/dead code once unreferenced. Key enabling move: relax `_validate_account_record` first so old+new records coexist; per-provider cutover is safe because `accounts/<provider>/` storage is provider-scoped. Intent unchanged — only the slicing and the coexistence strategy changed.
- 2026-06-21: deeper codebase scan refined the plan. Found the load chokepoint `_validate_account_record` (account-level `auth_kind`) gates every `load_account` — promoted to the mandatory Slice 1 edit. Confirmed run-resolution (`resolve_account_runtime_agent`), `monitor/config.py:179`, and `profile_scope.py` are shape-safe (read only provider/account), shrinking the "old-shape readers" risk to that one gate. Added concrete `No.Legacy` test disposition to Slice 5 (delete reconcile tests; rewrite preflight/auto-prime/status/registry tests).
