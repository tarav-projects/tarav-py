# Impl.Req: Claude Ambient Auth Artifact And Reconcile

## Impl.Abstract

Status: ready for execution

Source context:
- User wants a Claude Code account identity system analogous to Codex `auth.json` artifact collection, but based on Claude Code secure storage / Keychain state.
- Current incident proved the need: `/Users/pereiro/.agentos/agent/homes/claude-code/browser-br` refreshed to a working Keychain credential while `/Users/pereiro/.claude-br` kept stale credential material and started returning `401 Invalid authentication credentials` despite `claude auth status` reporting logged in. Copying the working path-hashed Keychain payload back restored the original home.
- User direction: never drop credential information; collect every observed credential snapshot, maintain an active/fresh pointer, and keep historical artifacts to minimize future re-login needs.

Primary implementation repository:
- `agentos-py/` owns provider account registries, Claude account status, reconcile mechanics, and CLI command dispatch.

Scope:
- Add a Claude `ambient-browser-login` credential artifact system parallel to Codex account artifacts.
- Persist immutable Claude secure-storage snapshots under `~/.agentos/accounts/claude-code/artifacts/`.
- Update Claude `ambient-browser-login` account records to point at an active artifact.
- Add `agentos agent accounts reconcile --provider claude-code` support for collecting fresh credentials from known homes and syncing active credentials into stale/missing target homes.
- On successful Claude account status / provider use, register the successfully used secure-storage snapshot so any working home can refresh the central account registry.

Out of scope:
- Changing `oauth-token-env` semantics.
- Deleting old credential artifacts.
- Encrypting Agentos artifact storage beyond local file permissions.
- Adding a new account-remove command.
- Reworking monitor rendering or account usage registry semantics.

## Impl.Index

### Block 1: Codex artifact lifecycle is the implementation pattern

Claim:
Claude ambient auth should reuse the Codex account-artifact lifecycle, not invent a separate account model.

Hard.Evidence:
- `src/agentos/codex/account_registry.py` has `read_codex_auth_info(...)`, `register_codex_account_from_auth_file(...)`, `_store_artifact(...)`, `_append_artifact_entry(...)`, and `link_codex_account_to_home(...)`.
- `src/agentos/codex/account_reconcile.py` discovers known homes, inspects provider homes, registers newly observed artifacts, selects an active artifact, and syncs stale system homes.
- `tests/test_codex_account_reconcile.py` covers fresh known-home registration, stale system-home sync, check mode, unknown-account warnings, and account-status reconciliation.

Design consequence:
Implement Claude ambient auth with the same conceptual nouns:
- inspect home
- credential info object
- register artifact
- active artifact pointer
- link/materialize active artifact to home
- reconcile known homes

### Block 2: Claude ambient artifact is secure-storage snapshot plus identity

Claim:
The Claude ambient artifact is not `.claude.json` alone. It is the secure-storage payload required to reconstruct a home's credential plus the identity evidence needed to bind it to an Agentos account.

Hard.Evidence:
- `src/agentos/claude/account_status.py` reads identity from `<home>/.claude.json` via `_load_home_config(...)` and `_fetched_identity_from_home_config(...)`.
- The usable access token is read from `_read_claude_secure_storage(...)`, which on macOS probes Keychain services from `_claude_keychain_service_names(home)` and falls back to `<home>/.credentials.json`.
- `claude auth status` can report `loggedIn: true` while a real `claude -p ...` request fails with `401`, so identity metadata alone is insufficient.
- We observed two path-hashed services for the same account:
  - `Claude Code-credentials-a0d8f03e` for `/Users/pereiro/.claude-br`
  - `Claude Code-credentials-db18d7d9` for `/Users/pereiro/.agentos/agent/homes/claude-code/browser-br`

Design consequence:
Introduce a Claude ambient artifact file such as:

```json
{
  "schema_version": 1,
  "provider": "claude-code",
  "auth_kind": "ambient-browser-login",
  "identity": {
    "email": "josuepereiro37@gmail.com",
    "account_uuid": "f8f48efc-...",
    "display_name": "josh",
    "organization_uuid": "dce73896-..."
  },
  "secure_storage": {
    "claudeAiOauth": {}
  },
  "source": {
    "home": "/Users/pereiro/.agentos/agent/homes/claude-code/browser-br",
    "storage_kind": "macos-keychain",
    "keychain_service": "Claude Code-credentials-db18d7d9",
    "observed_at": "2026-06-09T..."
  }
}
```

The artifact id is a SHA-256 of canonical artifact JSON. Event logs and status output must not print `secure_storage`.

### Block 3: Active artifact pointer represents the freshest reusable credential

Claim:
Claude ambient accounts need `active_artifact_id` just like Codex accounts. Old artifacts stay in history; the active pointer changes.

Hard.Evidence:
- Current `~/.agentos/accounts/claude-code/accounts.json` stores `browser-br` and `browser-jp` as `auth_kind: "ambient-browser-login"` with `active_artifact_id: null`.
- Current Claude artifact storage only exists for `oauth-token-env` (`*.oauth-token`).
- User explicitly wants to keep historical credential info and minimize re-login by reusing the freshest successful material.

Design consequence:
For `ambient-browser-login`, update account records to:

```json
{
  "provider": "claude-code",
  "account": "browser-br",
  "auth_kind": "ambient-browser-login",
  "active_artifact_id": "<sha>",
  "artifact_file": "artifacts/<sha>.ambient-auth.json",
  "email": "josuepereiro37@gmail.com",
  "account_uuid": "f8f48efc-..."
}
```

Append every observed artifact to `artifacts.jsonl`. Never delete or overwrite older artifact files. If the same artifact id is already known, return the existing artifact entry without duplicating.

### Block 4: Materialization writes the active artifact into the target home's credential slot

Claim:
For Claude ambient auth, "linking" is no longer just a claimed-home event. It should be able to materialize the account's active credential into the target home.

Hard.Evidence:
- Current `link_claude_account_to_home(...)` in `src/agentos/claude/account_registry.py` only records `kind: "claimed"` and does not write credentials.
- Manual recovery succeeded by copying the secure-storage payload from `Claude Code-credentials-db18d7d9` to `Claude Code-credentials-a0d8f03e`.
- `src/agentos/claude/account_status.py` computes path-specific Keychain names from `sha256(str(home))[:8]`.

Design consequence:
Add Claude ambient materialization helpers:
- resolve target credential service for a home
- write a secure-storage payload to that service on macOS
- write `<home>/.credentials.json` fallback where appropriate or when not on macOS
- ensure `<home>/.claude.json` has compatible `oauthAccount` identity metadata when the source artifact provides it

`agent accounts link --provider claude-code --account browser-br --home <home>` should materialize active ambient credentials when `auth_kind == "ambient-browser-login"` and `active_artifact_id` exists. If no active artifact exists, keep the current claimed-home behavior or raise a clear error; see Deviation Triggers.

### Block 5: Reconcile collects from any successful known home and syncs stale homes

Claim:
Claude reconcile should scan configured homes and system homes, register newly observed working credentials, and sync known account homes to active credential state.

Hard.Evidence:
- `agent accounts reconcile --provider codex` is wired in `_cmd_agent_accounts_reconcile(...)`; Claude currently raises unsupported.
- `codex/account_reconcile.py` already has shared request/result/action/warning models under `agent/account_reconcile.py`.
- Known homes can be discovered from configured profiles through `load_agent_configs(...)` and from registered system homes under `agentos_home_dir() / "agent" / "homes" / provider / account`.

Design consequence:
Add `src/agentos/claude/account_reconcile.py` mirroring Codex structure:
- discover configured Claude homes
- discover registered system homes
- inspect each home's `.claude.json` and secure storage
- classify as `matching-active`, `known-account-new-hash`, `registered`, `unknown`, `missing`, or `broken`
- register fresh artifacts for known accounts
- select an active artifact per account, preferring the newest successful/observed artifact when multiple candidates exist
- sync target homes by materializing the active artifact

### Block 6: Successful Claude usage should refresh central storage

Claim:
Reconcile is necessary but not enough. Any successful Claude run/status path should opportunistically register the credential that just worked.

Hard.Evidence:
- User explicitly wants "on any agentos `agent.run` we can refresh this system storing the data that successfully logged".
- `_claude_account_status_impl(...)` already knows the registered account, home, identity, and whether statusLine usage succeeded.
- Claude `Agent.run(...)` has provider-level control after a subprocess completes.

Design consequence:
After successful Claude account status with `usage_status == "ok"` for an `ambient-browser-login` account:
- inspect the effective home secure storage
- register artifact if new
- update active artifact for the account if identity matches

For `ClaudeAgent.run(...)`, add a narrow post-success hook for ambient accounts only when the provider process exits `0`. If adding this hook risks slowing or destabilizing interactive runs, limit the first slice to account-status/monitor paths and document the follow-up. Do not record artifacts when identity is missing or mismatched.

### Block 7: Security discipline is part of the contract

Claim:
Claude ambient artifacts contain OAuth secrets and must be treated at least as carefully as Codex `auth.json`.

Hard.Evidence:
- `security find-generic-password -w` returns raw credential JSON.
- Agentos event logs currently redact obvious auth payload keys through `_redacted_event_payload(...)`, but new event payloads must avoid carrying secrets at all.
- `src/agentos/claude/account_registry.py` writes token artifacts with mode `0600`; the ambient artifact writer should do the same.

Design consequence:
- Artifact files must be `0600`.
- JSON command output returns only safe summaries: artifact id, source home, keychain service name, identity, storage kind.
- Do not print `secure_storage`, access tokens, refresh tokens, or raw Keychain payloads.
- Account events must include metadata only.

## Execution.Plan

### Slice 1: Claude ambient credential info and artifact registration

Status: pending

Change:
- Extend `src/agentos/claude/account_registry.py` with dataclasses/functions for ambient auth:
  - `ClaudeAmbientAuthInfo`
  - `read_claude_ambient_auth_info(home: Path) -> ClaudeAmbientAuthInfo`
  - `register_claude_ambient_auth_from_home(home: Path, account: str, register_only: bool = False, ...)`
  - `_store_ambient_auth_artifact(...)`
  - `_append_ambient_auth_artifact_entry(...)`
- Reuse or move low-level secure-storage readers from `src/agentos/claude/account_status.py` so account registry/reconcile can read the same Keychain and `.credentials.json` sources without duplicating logic.
- Keep existing `oauth-token-env` artifact behavior unchanged.

Path exercised:
- A test home with `.claude.json` and synthetic secure-storage payload is registered as `browser-br`.

Observable result:
- `accounts.json` for the ambient account has `active_artifact_id` and `artifact_file`.
- `artifacts.jsonl` has an `auth_kind: "ambient-browser-login"` entry.
- `artifacts/<sha>.ambient-auth.json` exists with mode `0600`.

Validation:
- Add focused tests under `tests/` for registration, duplicate artifact id behavior, identity mismatch rejection, and redacted/safe output.

### Slice 2: Claude ambient materialization to a home

Status: pending

Change:
- Add materialization helpers for writing an active ambient artifact to a Claude home:
  - macOS: write Keychain service `Claude Code-credentials-<sha256(home)[:8]>`
  - fallback/non-macOS: write `<home>/.credentials.json`
- Update `link_claude_account_to_home(...)` to materialize active ambient auth when available.
- Preserve current claimed-only behavior only when there is no active ambient artifact and the function is intentionally being used as a metadata claim. The user-facing message must distinguish `claimed` from `materialized`.

Path exercised:
- Register an ambient artifact from a source home, link to a target home, then inspect the target secure-storage slot.

Observable result:
- Target home receives the credential payload matching the active artifact.
- `agent accounts link --provider claude-code --account browser-br --home <target> --json` reports `kind: "artifact"` or equivalent materialized status with safe metadata.

Validation:
- Unit tests with monkeypatched secure-storage writer.
- On macOS-capable local smoke, verify the target path-hashed service exists without printing secrets.

### Slice 3: Claude reconcile command

Status: pending

Change:
- Add `src/agentos/claude/account_reconcile.py`.
- Wire `_cmd_agent_accounts_reconcile(...)` to call `reconcile_claude_accounts(...)` for `--provider claude-code`.
- Discover configured Claude homes and system managed homes, mirroring Codex home discovery.
- Classify inspected homes and register/sync active artifacts using shared `AccountReconcileResult`, `AccountReconcileAction`, and `AccountReconcileWarning`.

Path exercised:
- Configured home has a fresh credential; system home has stale/missing credential; reconcile registers the fresh artifact and syncs the system home.

Observable result:
- `agentos agent accounts reconcile --provider claude-code --check --json` reports `would_register_artifact` and `would_sync_home`.
- Without `--check`, the registry and target home are updated.

Validation:
- Add `tests/test_claude_account_reconcile.py` parallel to `tests/test_codex_account_reconcile.py`.
- Manual local check:
  - `agentos agent accounts reconcile --provider claude-code --check --json`
  - `agentos agent accounts reconcile --provider claude-code --json`

### Slice 4: Account-status success refresh

Status: pending

Change:
- In `_claude_account_status_impl(...)`, after successful `ambient-browser-login` statusLine usage, register the secure-storage artifact from the same `agent.home` and activate it if identity matches the registered account.
- Add safe metadata to `AccountStatus.raw`, for example `auth_artifact_record`, without embedding secure storage.
- Avoid recording when statusLine falls back to registry data; only a live successful provider interaction proves the credential currently works.

Path exercised:
- Monitor runs `limits-tracking` for `claude-code/browser-br`, statusLine succeeds, and the active ambient artifact updates if the Keychain payload changed.

Observable result:
- `agentos agent accounts monitor --once --json` can cause a new Claude ambient artifact to appear when Claude has refreshed the Keychain payload.

Validation:
- Unit test monkeypatching statusLine success and secure-storage payload change.
- Existing monitor tests continue to pass.

### Slice 5: Optional ClaudeAgent.run post-success hook

Status: pending

Change:
- Add a narrow post-success hook in `ClaudeAgent.run(...)` for registered `ambient-browser-login` accounts.
- If subprocess exit code is `0`, attempt to register active ambient auth from the effective home.
- Swallow or record non-fatal artifact-registration failures only as metadata/events; do not turn a successful user run into a failure unless the user explicitly asked for strict auth refresh.

Path exercised:
- `agentos agent run --profile claude-br --prompt ...` succeeds, then central artifact storage reflects the credential used by that home.

Observable result:
- Successful Claude run can refresh central auth artifact storage even outside the monitor.

Validation:
- Provider-run unit test with mocked subprocess result and mocked ambient registration.
- Manual smoke with `agentos agent run --profile claude-br --prompt ...` after prior slices are validated.

## Risks

- **Secret sprawl.** This stores Keychain-backed OAuth material in Agentos files. The feature is intentional, but artifact permissions, output redaction, and event redaction must be strict.
- **False freshness.** `claude auth status` alone is not sufficient. Only a successful provider API interaction or a known-good manually registered payload should activate an artifact.
- **Identity ambiguity.** The same Claude account may appear in multiple homes. Reconcile must match by `oauthAccount.emailAddress` / `accountUuid`, not by home path.
- **Provider internals may change.** Claude Code may change Keychain service naming or secure-storage JSON shape. Keep the storage reader isolated and tested.
- **Interactive run side effects.** A post-run hook must not make interactive Claude runs brittle. If needed, implement the refresh hook first only in account-status/monitor paths.

## Deviation Triggers

- If secure-storage payload cannot be read without exposing secrets in process args or logs beyond current `security` CLI usage, stop and redesign the reader/writer boundary.
- If a target home has a mismatched `.claude.json` identity, do not materialize over it unless `--force` is explicit and the behavior is documented.
- If multiple fresh artifacts are observed for one account and no ordering metadata can determine freshness, register all but do not silently switch active; emit a warning.
- If macOS Keychain writing requires UI prompts or fails under noninteractive test conditions, keep the writer behind an injectable adapter and test the adapter boundary.

## Acceptance Signals

- Ambient Claude accounts in `~/.agentos/accounts/claude-code/accounts.json` can carry non-null `active_artifact_id`.
- `artifacts.jsonl` records `ambient-browser-login` artifacts without containing raw secure-storage payloads inline.
- Artifact files are immutable, content-addressed, and retained historically.
- `agentos agent accounts reconcile --provider claude-code --check --json` works.
- `agentos agent accounts reconcile --provider claude-code --json` can sync stale/missing Claude homes without browser login.
- A successful monitor statusLine run can update the active artifact when Claude refreshes the Keychain credential.
- Existing Codex account reconcile tests still pass.

## Validation Commands

```sh
cd /Users/pereiro/projects/agentos-project/agentos-py
uv run pytest tests/test_claude_account_reconcile.py tests/test_codex_account_reconcile.py -q
uv run pytest tests/test_agent_account_registry_commands.py -q
uv run ruff check src/agentos/claude src/agentos/agent tests/test_claude_account_reconcile.py
agentos agent accounts reconcile --provider claude-code --check --json
agentos agent accounts monitor --once --json
```

## Impl.Log

- 2026-06-09: Impl.Req created from discussion after successfully copying Claude Code browser-login secure-storage payloads between path-hashed Keychain services for `browser-br`. No implementation performed in this artifact creation pass.
