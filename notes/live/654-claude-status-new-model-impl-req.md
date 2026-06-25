# 654 — Claude `status` on the new account-management model + dead-path removal

## Impl.Abstract

- **Goal:** land an end-to-end `agentos agent accounts status` for **claude-code only**, built on the redesigned account-management model (settings/state split + `Auth.Registry` state store), and remove the now-dead claude account paths.
- **Status:** not started.
- **Scope (in):**
  - `ClaudeAuthMethod` implementing the `AuthMethod` ABC read-side (`read_auth_data`, `extract_identity`) — lifting the existing working claude home readers.
  - New registry readers: the new-shape `accounts.json` (settings) and `registry/active.json` (state).
  - Rewrite `status` to a home-centric, read-only, all-homes report for claude.
  - Remove claude-specific dead paths (register/reconcile/run-path promote/old status branches/old-shape reader); park `monitor`.
- **Scope (out):**
  - `materialize` / any home write — this work is **read-only from the home's perspective**. `ClaudeAuthMethod.materialize` stays unimplemented (raises).
  - `capture` / `activate` CLI commands (next Impl.Req).
  - codex & copilot cutover — they still use the shared old machinery; do **not** delete shared pieces or their provider paths here.
  - profile-expectation drift semantics beyond the candidate gate (deferred — see Index block `Status.Home.Centric`).
- **Source context:** design session (this chat). Companion/predecessor: `653-account-management-rebuild-impl-req.md`. Conceptual home: `agentos-pkg` `Account.Management` appendix (`Home.State`, `Auth.Data`, `Auth.Ref`, `Auth.Data.Aligned`, `Auth.Data.Drift`, `Auth.Registry`, `Account.Model:Auth.Method`).
- **Already done in this session (do not redo):**
  - `accounts.json` migrated to settings-only shape for all 3 providers (state stripped; backup at `~/.agentos/accounts/_migration-backup-20260625T160418/`).
  - claude profiles re-pointed to `account-id/method` addressing (`browser-om → om/browser`, etc.).
  - one worked `Auth.Registry` instance built by hand: `~/.agentos/accounts/claude-code/registry/` (`active.json`, `captures.jsonl`, `artifacts/<sha>`) for `om/browser`. **Note:** that artifact hashed secret-only and must be re-produced self-contained (see `AuthData.Self.Contained`).

## Impl.Index

### Account.Model.Surfaces

- the on-disk model after migration, per provider under `~/.agentos/accounts/<provider>/`:
  - `accounts.json` — **settings**: `{provider, accounts: {<account-id>: {identity:{…}, auth_methods:{<method>:{class}}}}}`. Identity is provider-shaped (codex `provider_account_id`+`email`; claude `account_uuid`+`organization_uuid`+`display_name`+`email`).
  - `registry/` — **state** (`Auth.Registry`): `active.json` (`{"<account-id>/<method>": "<artifact_id>"}`), `captures.jsonl` (one record per capture: `{ts, account, method, class, auth_ref, artifact_id}`), `artifacts/<sha256>` (content-addressed payload blobs, secrets only here, mode 600).
- the pair `{captures.jsonl record + artifact}` reconstructs full `Auth.Data`; that pair **is** the `Auth.Registry`.
- settings/state are physically split: nothing mutable in `accounts.json`, nothing declarative in `registry/`.

### AuthData.Self.Contained

- the `AuthMethod` ABC signature `extract_identity(self, auth_data)` takes only the `AuthData` — so identity must live **inside** the payload.
- therefore claude's `AuthData.payload` is self-contained: `{claudeAiOauth (secret) + oauthAccount (identity)}`.
- `content_id = sha256(canonical(payload))` then covers both; the artifact alone is full `Auth.Data`; `auth_ref` (in the capture record) is its lossy projection.
- consequence: the hand-built `om` artifact (secret-only) is re-produced with this payload, yielding a new `artifact_id`; `active.json` + `captures.jsonl` updated to match. The status drift check compares a home's live `content_id` against the stored `artifact_id`, so both sides must hash the same self-contained shape.

### Claude.Auth.Method

- `ClaudeAuthMethod` implements the ABC read-side only; lifts the existing working readers, does not reinvent them:
  - identity: `~/.claude*/.claude.json` → `oauthAccount` (`accountUuid`, `emailAddress`, `displayName`).
  - secret: macOS Keychain service `Claude Code-credentials-<8hex of sha256(resolved home)>` (fallback `Claude Code-credentials`), else `<home>/.credentials.json` → `{claudeAiOauth:{…}}`.
  - `read_auth_data(home)` composes `{claudeAiOauth + oauthAccount}` → `AuthData`, or `None` if either part is absent (home not logged in / undeterminable).
  - `extract_identity(auth_data)` → `AccountIdentity` from `oauthAccount` (`provider_account_id = accountUuid`, `email`, `label = displayName`, `raw`).
  - `materialize(...)` → `raise NotImplementedError` (out of scope).
  - class attrs: `provider="claude-code"`, `materializable=True`; `name` is the method label (e.g. `"browser"`). Existing readers to lift live in `claude/account_registry.py` (`read_claude_secure_storage_info`, keychain service names, `oauthAccount` read).

### Status.Home.Centric

- `status` is a read-only, home-centric, all-homes report — it never writes a home and makes no provider/network call.
- **home source = profiles only (MVP).** Build `home → {provider, candidates}` where candidates = union of the profile `accounts` (`<account-id>/<method>`) across every profile listing that home; dedup homes by merging candidate sets. Profiles supply provider + candidate accounts; deeper profile-expectation semantics are deferred.
- per home, the report:
  1. read with the provider's listed method(s) → `Auth.Data`, or **`undeterminable`** (reported as the home's status, not an error).
  2. `extract_identity` → resolve to an account by matching identity against `accounts.json`.
  3. **candidate gate:** the resolved account must be in the home's candidate set.
     - in set → registry check: `content_id` vs `active.json[account/method]` → **`aligned`** or **`drift`**.
     - not in set (foreign/unknown identity present in the home) → **`error:unlisted-account`**.
- per-home status set (V1): `undeterminable` | `aligned` | `drift` | `error:unlisted-account`.
- maps to `Auth.Data.Aligned` / `Auth.Data.Drift`; "we check each home's `Auth.Data` against the expected config of the system."

### Dead.Path.Removal

- claude-scoped only — codex/copilot still use shared old machinery; leave shared pieces and their provider paths intact.
- remove: run-path post-run promote (`promote_verified_claude_ambient_auth_from_home`, `has_claude_oauth_token_kind`, `commands.py` ~281–294); `register` claude branch + `register_claude_account`; `reconcile` claude branch + `claude/account_reconcile.py` + `reconcile_claude_accounts`; old `status` claude branches + `_inspect_account_home` (claude path); old-shape `accounts.json` reader/writer paths in `claude/account_registry.py` that are no longer reachable.
- **keep** the home readers/writer that were lifted or are still shared.
- `monitor`: park — disable the subcommand (it reads the old shape); do not port.
- this surfaces the AGENTS.md "no backward-compatibility layers" policy and the index `No.Legacy.Allowed` / `No.Regression.Tests.Allowed` rules — rewrite affected tests, don't shim.

## Execution.Plan

Order: 1 → 2 → 3 (e2e green) → 4 (teardown). Reach the first observable endpoint (status printing for one real claude home) as fast as possible.

### Slice 1 — `ClaudeAuthMethod` read-side
- **changes:** new `ClaudeAuthMethod(AuthMethod)` in the claude package; lift the existing keychain/`.claude.json` readers behind `read_auth_data` + `extract_identity`; `materialize` raises.
- **path exercised:** read a live claude home → `AuthData{claudeAiOauth+oauthAccount}` → `AccountIdentity`.
- **observable result:** given `~/.claude-om`, `read_auth_data` returns an `AuthData` whose `content_id` is stable and `extract_identity` yields `accountUuid 973c403b-…` / `ocabrerabarrera@gmail.com`; absent home → `None`.
- **check (RED→GREEN):** behavior test at the method boundary using a fixture home (`.claude.json` + a `.credentials.json` secret to avoid Keychain in tests). RED before the class exists, GREEN after. Assert no secret value is logged.

### Slice 2 — registry + settings readers; re-produce `om` artifact
- **changes:** reader for new-shape `accounts.json` (identity→account-id resolution, list `account-id/method` + class); reader for `registry/active.json`. Re-produce the `om/browser` artifact self-contained (`{claudeAiOauth+oauthAccount}`), update `active.json` + `captures.jsonl` to the new `artifact_id`.
- **path exercised:** settings + state load → resolve an identity to an account → look up its active `artifact_id`.
- **observable result:** identity `973c403b-…` resolves to account `om`; `active.json["om/browser"]` returns the new self-contained hash; the live `~/.claude-om` `content_id` equals it.
- **check (RED→GREEN):** behavior test over a fixture `accounts.json` + `registry/` asserting identity→account resolution and active lookup; an assertion that live-read `content_id` matches the stored artifact for `om`.

### Slice 3 — rewrite `status` (e2e green light)
- **changes:** replace the claude path of `_cmd_agent_accounts_status` with the home-centric report: enumerate profile homes → `home → {provider, candidates}` (dedup+merge) → per-home read + gate + registry check → render `undeterminable | aligned | drift | error:unlisted-account`. JSON + human output.
- **path exercised:** full stack — profiles → homes → `ClaudeAuthMethod` → settings/`active.json` → per-home status.
- **observable result:** `agentos agent accounts status --provider claude-code` lists every claude home with a status; `~/.claude-om` reads `aligned`; a logged-out/managed home reads `undeterminable`.
- **check (RED→GREEN):** behavior test driving the command over a fixture profiles dir + homes + registry, asserting the status line per home and exit code; a manual run against the live machine recorded in `Impl.Log`.

### Slice 4 — teardown (dead claude paths)
- **changes:** delete the items in `Dead.Path.Removal`; disable `monitor`; rewrite/remove tests that covered the deleted claude paths (no regression shims).
- **path exercised:** run path no longer post-run-promotes claude; `register`/`reconcile` claude branches gone.
- **observable result:** grep shows no live references to the removed symbols; `agentos agent run` (claude) works with no promote side-effect; `register`/`reconcile`/`monitor` for claude are gone/disabled.
- **check:** full test suite green; targeted grep asserts the symbols are gone; codex/copilot paths still import and pass (shared machinery untouched).

### Risks / deviation triggers
- **Keychain in tests** — don't depend on the macOS Keychain in CI; tests use the `.credentials.json` fallback. Live Keychain only in the manual run.
- **Shared-machinery entanglement** — if a "claude-only" deletion turns out to be imported by codex/copilot, stop and narrow (Interactive: ask; Autonomous: keep it, note in `Impl.Log`).
- **`content_id` mismatch** — if live-read and stored hashes diverge, the payload canonicalization differs between read and capture; reconcile the canonical form before proceeding (this is the crux of `AuthData.Self.Contained`).
- **profile home duplication** — a home in several profiles must merge candidate sets, not pick one; a wrong merge shows up as spurious `error:unlisted-account`.

### Acceptance signals
- `status --provider claude-code` reports all claude homes read-only, with the V1 status set, `~/.claude-om = aligned`.
- no home is ever written; no network call in `status`.
- claude dead paths removed; codex/copilot untouched; suite green.

## Impl.Log

- (empty — implementer appends deviations, open-space decisions, blockers; nothing that's visible in the diff)
