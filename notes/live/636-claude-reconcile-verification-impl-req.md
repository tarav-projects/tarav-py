# Impl.Req: Claude Reconcile Verification Semantics

## Impl.Abstract

Status: ready for execution

Source context:
- Claude ambient auth artifacts now exist for `ambient-browser-login` accounts.
- The user clarified the intended semantics:
  - collect/archive any newly observed credential payload for the sake of collection
  - separately track which credentials are verified by a real successful provider request
  - `active_artifact_id` means latest successful/verified credential, not latest observed credential
  - passive reconcile should scan known homes and collect new artifacts, but should not perform live provider calls
  - `reconcile --ping` should run cheap live checks and use successful checks to mark credentials verified/active
  - the implementation must be callable as core Python functions; CLI is only a wrapper
- Incident evidence: `~/.claude-br` reported `claude auth status` as logged in but failed a live Claude request with `401`; the managed system home succeeded and had to be explicitly promoted/materialized.

Primary implementation repository:
- `agentos-py/`

Scope:
- Add a provider-neutral account credential verification ledger under account storage.
- Add Claude-specific verified promotion helpers that register observed artifacts, append verification evidence after real success, set the account active pointer, and sync known homes from the active artifact when safe.
- Update Claude passive reconcile to collect all observed artifacts and consume existing verification evidence to select active credentials.
- Add `agentos agent accounts reconcile --provider claude-code --ping` as a CLI wrapper around a core callable reconcile option that verifies candidate homes with real pings.
- Integrate successful Claude `agent.run`, `agent ping`, account-status/monitor, and monitor auto-prime paths through the same core verification/promotion API.

Out of scope:
- Changing `oauth-token-env` semantics.
- Making passive reconcile perform live network/provider calls.
- Promoting unverified observed credentials just because they are new.
- Encrypting stored ambient auth artifacts beyond existing local file permissions.
- Generalizing Codex/Copilot behavior unless a small provider-neutral ledger helper is useful to avoid Claude-only storage duplication.

## Impl.Index

### Block 1: Observed, verified, and active are separate states

Claim:
Claude reconcile must distinguish credential collection from credential validity.

Hard.Evidence:
- `src/agentos/claude/account_reconcile.py` currently classifies homes by reading `.claude.json` plus secure storage through `inspect_claude_account_home(...)`.
- `src/agentos/claude/account_registry.py` currently stores immutable ambient artifacts and account `active_artifact_id`.
- `claude auth status` reported `loggedIn: true` for `~/.claude-br` while a real Claude request failed with `401 Invalid authentication credentials`.
- The managed system home for `browser-br` completed a real Claude request successfully with a different artifact id.

Design consequence:
Keep archive collection append-only and opportunistic, but make activation require verification evidence. Treat `active_artifact_id` as "latest verified successful artifact", not "newest observed artifact".

### Block 2: Verification evidence belongs in account storage, not only events

Claim:
Reconcile needs durable, queryable verification evidence, not only command events.

Hard.Evidence:
- `src/agentos/agent/account_registry.py` has provider account storage roots, `artifacts.jsonl`, and dated account event logs.
- `record_account_event(...)` is useful audit history but is date-partitioned under `~/.agentos/accounts/events/`, making provider/account artifact lookup awkward.
- `src/agentos/claude/account_reconcile.py` needs to decide active artifacts from evidence during passive reconcile.

Design consequence:
Add a provider-neutral verification ledger, for example:
- `~/.agentos/accounts/<provider>/verifications.jsonl`
- helpers in `agentos.agent.account_registry` or a narrow adjacent module:
  - `verification_records_path(provider)`
  - `read_verifications(provider)`
  - `append_verification(provider, entry)`

Entries must contain only safe metadata:
- provider
- account
- artifact_id
- auth_kind
- home
- verified_at / recorded_at
- source, such as `agent.run`, `agent.ping`, `account.status`, `accounts.reconcile.ping`, `monitor.auto_prime`
- optional success metadata, never secure storage or tokens

### Block 3: Claude needs a core promotion function

Claim:
Successful Claude paths should not each implement their own registration/activation behavior.

Hard.Evidence:
- `src/agentos/claude/account_status.py` currently calls `register_claude_ambient_auth_from_home(...)` after successful statusline usage.
- `src/agentos/claude/agent.py` currently calls `register_claude_ambient_auth_from_home(...)` after a successful run.
- Manual repair required registering the known-good system home and then linking/materializing it into `~/.claude-br`.

Design consequence:
Add a Claude core API, for example:
- `promote_verified_claude_ambient_auth_from_home(home, account, source, start_path=".", sync_homes=True, check=False, argv=())`

It should:
- read the home's current ambient auth info
- register/archive the artifact if new
- append verification evidence for the artifact
- update `active_artifact_id` / `artifact_file` / `last_verified_at` / `last_verified_source`
- optionally sync known homes for the account from that active artifact
- return safe metadata only

Existing status/run/ping/monitor code should call this API after real success instead of directly calling artifact registration.

### Block 4: Passive reconcile collects and consumes evidence but does not verify

Claim:
`agentos agent accounts reconcile --provider claude-code` should remain passive and non-networking.

Hard.Evidence:
- User explicitly wants passive reconcile to scan all known homes, read Keychain/files, collect new artifacts, and use existing ping/run evidence.
- Current `reconcile_claude_accounts(...)` already discovers configured homes and system homes, inspects secure storage, registers artifacts, and syncs active artifacts.
- Current conservative behavior avoids choosing between multiple new observed artifacts.

Design consequence:
Change passive Claude reconcile to:
- inspect every known home
- register every newly observed artifact as history with `register_only=True` unless verified evidence says it should become active
- read verification ledger
- select latest verified artifact per account as active
- sync stale safe homes from active
- report observed, registered, verified, activated, and synced actions separately
- do no live Claude calls

### Block 5: `reconcile --ping` is an optional verification mode on the core API

Claim:
The CLI `--ping` flag should be a thin wrapper over core reconcile verification behavior.

Hard.Evidence:
- `src/agentos/agent/commands.py` already wraps `reconcile_claude_accounts(...)` in `_cmd_agent_accounts_reconcile(...)`.
- `src/agentos/agent/providers.py` exposes `build_registered_account_agent(...)`, which monitor auto-prime already uses to build account/home scoped agents.
- `src/agentos/agent/commands.py` has `_cmd_agent_ping(...)` and ping validation logic.
- `src/agentos/agent/monitor/workflows.py` has `_run_account_prime_ping(...)`, currently a separate live success path.

Design consequence:
Extend the core `reconcile_claude_accounts(...)` signature with a provider-domain option such as `verify_with_ping: bool = False` or `ping: bool = False`.

When enabled:
- run a cheap configured/default Claude ping for candidate homes/artifacts
- if ping succeeds, append verification evidence and promote that artifact active
- if ping fails, keep the artifact archived but do not activate it
- continue safely across independent homes/accounts, reporting per-home verification failures as warnings/actions
- support `check=True` by reporting `would_ping` / `would_verify` / `would_activate_verified` without making provider calls or mutations

CLI adds `--ping` only for providers that support it; initially Claude.

### Block 6: Agent run/ping/monitor should share success evidence

Claim:
Successful provider interactions outside reconcile should refresh verification evidence and active credentials.

Hard.Evidence:
- User wants ping commands and monitor/provider workflows to feed the active credential state.
- `src/agentos/claude/agent.py` sees provider process exit code after `execute_agent_command(...)`.
- `src/agentos/agent/commands.py` validates ping success in `_cmd_agent_ping(...)`.
- `src/agentos/claude/account_status.py` knows when statusline usage is fresh vs registry fallback.
- `src/agentos/agent/monitor/workflows.py` runs auto-prime pings through `build_registered_account_agent(...)`.

Design consequence:
After live success:
- Claude `Agent.run(...)` calls the core promotion API with source `agent.run`.
- Claude account-status statusline success calls it with source `account.status`.
- `agent ping` can rely on `ClaudeAgent.run(...)` post-success if run is enough, or explicitly call promotion after `_validate_agent_ping_result(...)` so the source records as `agent.ping`.
- monitor auto-prime should either rely on `ClaudeAgent.run(...)` or explicitly record source `monitor.auto_prime`; the plan should choose one and test it.
- registry fallback usage must not verify credentials.

### Block 7: Sync should follow verification, not observation

Claim:
Homes should be repaired from active only after active is verified.

Hard.Evidence:
- The broken `~/.claude-br` artifact was newly observed but invalid.
- Syncing from observed-but-invalid credentials would spread bad credentials.
- Manual repair worked by promoting the successful system-home artifact and materializing it into `~/.claude-br`.

Design consequence:
Keep `link_claude_account_to_home(...)` materialization behavior, but only call it automatically from reconcile/success hooks when active is backed by verification evidence. Passive reconcile can sync from existing active if it has verification evidence; otherwise it should warn or skip rather than spreading unverified active state.

## Execution.Plan

### Slice 1: Provider-neutral verification ledger

Status: pending

Change:
- Add account verification ledger helpers near `src/agentos/agent/account_registry.py` or a focused adjacent module.
- Define safe JSONL records and helper payload validation.
- Add read/append tests.
- Ensure no secure storage payloads are accepted or emitted.

Path exercised:
- A test appends a verification for `claude-code/browser-br` artifact `abc123`, reads it back, and duplicate behavior is deterministic.

Observable result:
- `~/.agentos/accounts/claude-code/verifications.jsonl` can persist and return safe verification records.

Validation:
- Add focused tests, likely in `tests/test_agent_account_registry.py` or a new small registry test.
- `uv run pytest <new-test-file> -q`

### Slice 2: Claude verified promotion core API

Status: pending

Change:
- Add a Claude helper such as `promote_verified_claude_ambient_auth_from_home(...)`.
- It should archive the current home artifact, append verification evidence, update account active fields, and optionally sync known homes for that account.
- It should be callable without CLI args; CLI argv is optional event metadata only.
- Adjust existing direct post-success registration calls to use this helper.

Path exercised:
- A test home with an observed credential is promoted as verified; account record active points to that artifact and verification ledger contains the source.

Observable result:
- Account record includes active artifact plus verification metadata such as `last_verified_at` and `last_verified_source`.
- Safe output includes verification metadata and no secure storage.

Validation:
- Extend Claude registry/status tests.
- `uv run pytest tests/test_claude_account_registry.py tests/test_claude_account_status.py -q`

### Slice 3: Passive Claude reconcile consumes verification evidence

Status: pending

Change:
- Update `reconcile_claude_accounts(...)` so passive reconcile registers every observed new artifact, but activation is driven by verification ledger evidence.
- If several observed artifacts exist and only one has latest verification, activate that one.
- If no verified artifact exists, register history but do not activate.
- If active points at an artifact without verification evidence, do not spread it automatically; report a warning or skipped sync action.

Path exercised:
- Two homes have different observed artifacts; one artifact has verification evidence. Passive reconcile archives both, activates the verified one, and syncs stale homes.

Observable result:
- `--check` reports planned register/activate/sync actions from evidence.
- Non-check mutates registry/homes accordingly.

Validation:
- Extend `tests/test_claude_account_reconcile.py`.
- Include the previously observed failure mode: broken newly observed artifact must not become active.

### Slice 4: Reconcile ping verification mode

Status: pending

Change:
- Extend core `reconcile_claude_accounts(...)` with a ping/verify option.
- Add CLI `agentos agent accounts reconcile --provider claude-code --ping`.
- Use `build_registered_account_agent(...)` or an equivalent core helper to run cheap live checks for candidate homes.
- In check mode, do not run provider calls; report intended `would_ping`.
- On success, append verification and activate the successful artifact.
- On failure, leave artifact archived and report a safe warning/action.

Path exercised:
- Two candidate homes exist. Mock ping success for one and failure for the other. `reconcile_claude_accounts(..., ping=True)` activates only the successful artifact.

Observable result:
- CLI JSON output reports ping/verification actions.
- Passive mode remains non-networking.

Validation:
- Add unit tests for core function and CLI argument dispatch.
- `uv run pytest tests/test_claude_account_reconcile.py tests/test_agent_account_registry_commands.py -q` if command tests exist; otherwise add/extend an appropriate command test file.

### Slice 5: Successful run, ping, status, and monitor evidence integration

Status: pending

Change:
- Replace Claude post-run direct artifact registration with the verified promotion helper.
- Ensure account-status live statusline success records verification; registry fallback does not.
- Ensure `agent ping` records verification evidence with source `agent.ping` for Claude account-backed homes, either through an explicit hook after ping validation or through a source-aware run hook.
- Ensure monitor auto-prime successful ping records source `monitor.auto_prime` or a clear equivalent source.
- After promotion, sync known homes for the account when safe.

Path exercised:
- A mocked successful Claude run/ping/status promotes the artifact verified, updates active, and reconciles/syncs homes through core APIs.

Observable result:
- Verification ledger contains source-specific records.
- Passive reconcile after these successes sees no work or only expected safe sync actions.

Validation:
- Extend `tests/test_claude_account_status.py`.
- Add/extend agent ping/run tests in `tests/test_agent_run_account_preflight.py` or a Claude-specific test.
- Add monitor auto-prime coverage if the source is explicitly recorded there.

### Slice 6: Local smoke and command refresh

Status: pending

Change:
- Refresh installed CLI if command parser changes: install from `agentos-cli`, not `agentos-py`.
- Run safe local checks.

Path exercised:
- `agentos agent accounts reconcile --provider claude-code --check --json`
- `agentos agent accounts reconcile --provider claude-code --check --ping --json`
- Optional non-check `--ping` only if user approves live provider calls.

Observable result:
- Check mode never performs live calls.
- Passive reconcile collects/syncs from verified evidence only.

Validation:
- `uv run pytest -q`
- Targeted Ruff for changed files.
- Installed `agentos --version` still works after CLI refresh.

## Risks

- **Accidental credential spread.** If activation still follows observation in any path, broken credentials can be materialized into working homes.
- **Network side effects.** `--ping` must be explicit, and `--check --ping` must not perform provider calls.
- **Source ambiguity.** If `agent.run`, `agent.ping`, and monitor share the same run hook without source metadata, the verification ledger becomes less useful. Prefer explicit source values where practical.
- **Over-broad provider abstraction.** The ledger can be provider-neutral, but Claude verification/ping behavior should remain provider-specific until other providers need it.
- **Secret leakage.** Verification entries, command output, warnings, and events must not include `secure_storage`, access tokens, refresh tokens, or raw Keychain payloads.

## Deviation Triggers

- If adding a provider-neutral verification ledger would require broad registry rewrites, keep the ledger helper minimal and provider-root scoped.
- If ping verification cannot be implemented as a core callable without coupling to CLI parser objects, stop and redesign the boundary.
- If monitor auto-prime cannot record a source-specific verification without substantial monitor workflow churn, keep promotion via `ClaudeAgent.run(...)` and log the source limitation in `Impl.Log`.
- If a verified artifact cannot be tied unambiguously to an account identity, do not activate it.

## Acceptance Signals

- Passive Claude reconcile archives new observed credentials without live calls.
- Passive Claude reconcile uses stored verification evidence to select active credentials.
- `active_artifact_id` means latest verified successful artifact.
- `reconcile --ping` verifies credentials explicitly and can promote the successful artifact.
- Successful Claude run/status/ping/monitor paths append verification evidence through shared core APIs.
- CLI is a thin wrapper over callable reconcile functions; workflows can call reconcile directly without shelling out.
- Existing Claude ambient auth tests and Codex reconcile tests continue to pass.

## Validation Commands

```sh
cd /Users/pereiro/projects/agentos-project/agentos-py
uv run pytest tests/test_claude_account_reconcile.py tests/test_claude_account_registry.py tests/test_claude_account_status.py -q
uv run pytest tests/test_agent_run_account_preflight.py tests/test_agent_monitor_auto_prime.py tests/test_codex_account_reconcile.py -q
uv run pytest -q
uv run ruff check src/agentos/agent src/agentos/claude tests/test_claude_account_reconcile.py tests/test_claude_account_registry.py tests/test_claude_account_status.py
agentos agent accounts reconcile --provider claude-code --check --json
agentos agent accounts reconcile --provider claude-code --check --ping --json
```

## Impl.Log

- 2026-06-09: Impl.Req created from user-approved reconcile semantics: collect all observed credentials, verify only through real successful provider calls, and make active mean latest verified successful credential. No implementation performed in this design pass.
