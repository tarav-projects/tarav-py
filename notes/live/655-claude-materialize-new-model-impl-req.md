# 655 — Reimplement `materialize` on the new model (claude) + eliminate the legacy materialize path

## Impl.Abstract

- **Goal:** implement `Auth.Data.Materialization` on the new account model — write an account's **active** `Auth.Data` into a provider home so an agent logs in — for **claude-code**, wire it to `agent accounts materialize`, and **eliminate the legacy materialize CLI path** (`No.Legacy.Allowed`).
- **Status:** not started. The procedure is already proven by hand this session (all 7 claude homes materialized to `aligned`); this Impl.Req turns that hand-script into the real `ClaudeAuthMethod.materialize` + CLI, test-covered.
- **Scope (in):**
  - implement `ClaudeAuthMethod.materialize(auth_data, home)` (currently raises `NotImplementedError`).
  - reimplement `agent accounts materialize` on the new model: read the account's active artifact from `Auth.Registry`, materialize it into the target home via the provider `AuthMethod`. **Capture-first** (`Capture.Over.Materialization`).
  - **eliminate the legacy materialize CLI path**: the `_cmd_agent_accounts_materialize` codex→`materialize_codex_account_to_home` route and `_format_agent_accounts_materialize`.
- **Scope (out):**
  - **all non-claude providers — ignore them entirely.** Do not touch codex/copilot materialize code, their CLI branches, or their tests. This Impl.Req is claude-only; other providers are a separate concern handled at their own cutover.
  - bulk/multi-home materialize, profile-driven home selection — the primitive writes **one** `--home`. Bulk is a later workflow on top.
  - run-path auto-materialize / auto-promote (already removed / separately deferred). Materialize stays **explicit, user-invoked only**.
- **Source context:** this session's hand-materialize demo; predecessor `654-claude-status-new-model-impl-req.md`. Conceptual home: `agentos-pkg` `Account.Management` (`Auth.Data.Materialization`, `Capture.Over.Materialization`, `Active.Auth.Data`).

## Impl.Index

### Materialize.Primitive

- `Auth.Data.Materialization` writes a `Provider.Account`'s **active** `Auth.Data` into a home so an agent can log in — the only primitive that mutates a home, sole writer of the home/system layer.
- inputs: the account's `Active.Auth.Data` artifact (from `registry/active.json` → `read_artifact`) and the target `--home`. It is a pure write — it does not activate or verify.
- explicit and user-invoked only — nothing auto-materializes. Single `--home` per call.

### Claude.Materialize.Mechanics

- the artifact payload is self-contained: `{<secret...> + oauthAccount}`. Claude's `Home.State` splits across two locations, so materialize writes **both**:
  - **secret** → secure storage via the existing `write_claude_secure_storage(home, secret)` (Keychain hash-specific on darwin, `.credentials.json` off). The secret is **everything in the payload except `oauthAccount`** — NOT just `claudeAiOauth`. (Live bug found this session: `~/.claude-br` carried an extra secret key; writing only `claudeAiOauth` left the home reading back a different `content_id` and staying `drift`.)
  - **identity** → set `oauthAccount` in `<home>/.claude.json`, preserving the file's other keys.
- correctness invariant: after materialize, `ClaudeAuthMethod.read_auth_data(home).content_id()` MUST equal the active artifact id (the home now reads back exactly the active artifact → `aligned`). This round-trip is the materialize test oracle.
- the secret-storage write location matches where `ClaudeAuthMethod` reads (hash-specific Keychain `[0]` / in-home `.credentials.json`) — verified universal across all live claude homes this session.

### Capture.Over.Materialization

- before overwriting a home, **capture** what is live there (`Auth.Data.Capture`): if the home holds readable `Auth.Data` whose `content_id` is not already archived, store it + append a capture record (dedup). A home may hold a valid, unregistered snapshot (rotation) that must not be lost.
- capture is non-destructive and always runs first; materialize is the yielding direction. `--check` reports the intended write (and any capture-first) without mutating the home.

### Materialize.CLI.NewModel

- add a **claude-code** path to `agent accounts materialize` on the new model: resolve `--account` (an `<account-id>/<method>` address) → its active artifact in `Auth.Registry` → `ClaudeAuthMethod.materialize(artifact, home)`.
- the claude path reads `--provider`, `--account` (`<account-id>/<method>`, explicit — no bare-resolve in V1), `--home` (the target), `--check` (dry-run). It ignores `--force` (capture-first makes overwriting always-safe).
- errors hard (`CPU.Program` discipline): no active artifact for the address, unknown method, or unreadable artifact → clear error. No silent fallback.
- claude works fully (proven by this session's hand-materialize of all 7 homes). Other providers' branches are left exactly as they are — out of scope.

### Legacy.Materialize.Removal

- `No.Legacy.Allowed` for claude: the claude materialize must be the **new-model path only** — do not resurrect or reuse the old promote/reconcile-based home-write machinery (the run-path auto-promote was already removed in 654). The low-level `write_claude_secure_storage` writer is reused (it is the storage primitive, not legacy logic).
- if any vestigial claude home-write/materialize helper exists and is unreachable after this change, remove it; rewrite any test asserting old claude materialize behavior.
- leave all non-claude materialize code untouched.

## Execution.Plan

Order: 1 → 2 (CLI e2e) → 3 (claude legacy sweep). Claude only — ignore other providers throughout. Reach the observable endpoint (materialize one home → `aligned`) fast.

### Slice 1 — `ClaudeAuthMethod.materialize`
- **changes:** implement `materialize(auth_data, home)` — write `{payload − oauthAccount}` via `write_claude_secure_storage`, then set `oauthAccount` in `<home>/.claude.json` (preserve other keys).
- **path exercised:** artifact payload → home secure storage + `.claude.json`.
- **observable result:** after `materialize(artifact, home)`, `ClaudeAuthMethod.read_auth_data(home).content_id() == artifact.content_id()`.
- **check (RED→GREEN):** behavior test, keychain disabled (`sys.platform="linux"` → `.credentials.json` path). Write an artifact with an extra secret key beyond `claudeAiOauth` into a fixture home, read back, assert `content_id` matches (guards the full-secret bug). RED before impl, GREEN after.

### Slice 2 — `agent accounts materialize` claude path on the new model (e2e)
- **changes:** add a claude-code branch to `_cmd_agent_accounts_materialize`: parse `--account` as `<account-id>/<method>`, load active artifact from `auth_registry`, **capture-first** the target home, then `ClaudeAuthMethod.materialize`. Leave the existing non-claude branch(es) untouched.
- **path exercised:** CLI → `Auth.Registry` active lookup → capture-first → `ClaudeAuthMethod.materialize` → home.
- **observable result:** a fixture drifted claude home, after `materialize --provider claude-code --account om/browser --home <h>`, reads `aligned` in `status`; a home holding an unregistered snapshot has it captured first (new artifact + capture record); `--check` mutates nothing.
- **check (RED→GREEN):** behavior test driving the command over fixture profiles/registry/home; assert post-materialize `status` is `aligned`, capture-first recorded the prior snapshot, and `--check` leaves the home unchanged. Plus a manual live run on one claude home recorded in `Impl.Log`.

### Slice 3 — claude legacy sweep (`No.Legacy.Allowed`)
- **changes:** confirm the claude materialize is the new-model path only; remove any now-unreachable vestigial claude home-write/materialize helper and any test asserting old claude materialize behavior. Touch nothing outside claude.
- **observable result:** grep shows no claude materialize path other than `ClaudeAuthMethod.materialize` + its CLI branch; non-claude code unchanged.
- **check:** full suite green; targeted grep over the claude package.

### Risks / deviation triggers
- **secret shape** — never assume the secret is only `claudeAiOauth`; write the whole payload minus `oauthAccount`. (Proven failure mode.)
- **storage-location mismatch** — materialize must write where `ClaudeAuthMethod` reads. `write_claude_secure_storage` (keychain on darwin / file off) matched all live homes; if a home diverges, the round-trip oracle catches it (verify=FAIL).
- **Keychain in tests** — use the `.credentials.json` fallback; live Keychain only in the manual run.
- **stay claude-scoped** — do not edit non-claude materialize code, branches, or tests; if a change seems to require it, stop and narrow.
- **`.claude.json` clobber** — preserve all keys; only set `oauthAccount`.

### Acceptance signals
- claude home materializes to `aligned` via the CLI; capture-first preserves any unregistered snapshot; `--check` is read-only.
- claude materialize is the new-model path only (no legacy claude materialize remains); non-claude code untouched; suite green.

## Impl.Log

- (empty — implementer appends deviations, open-space decisions, blockers; nothing diff-visible)
