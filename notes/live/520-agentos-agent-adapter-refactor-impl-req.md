# Agentos Agent Adapter Refactor - impl-req

## Impl.Abstract

- **scope:** refactor `agentos-py` agent infrastructure toward `Agentos.Agent.Adapter` while preserving current runner, monitor, account, profile, and Chatlas/session functionality.
- **status:** ready for implementation.
- **source:** 2026-06-13 design discussion and code alignment report after removing legacy `agent.instances`.
- **goal:** keep Agentos behavior at the same functional level while (1) removing the structural duplication and faked polymorphism in the agent primitive layer, (2) letting each provider adapter declare only the capabilities it actually implements, and (3) renaming the relevant objects and fields to express the `Agentos.Agent.Adapter` model directly in code.
- **primary structural debt (the real reason for this refactor):** the agent primitive layer carries one broad shape three times — `AgentConfig`, `AgentBase`, and the `Agent` protocol each restate the same ~21-field surface — and fakes capability support by having `AgentBase.run`/`account_status`/`_build_command` raise "does not support". This contradicts the stated concept model (`102-Agentos.Agent.Model.md`), where providers need not share fields and only satisfy the tasks they support.
- **canonical design home:** `/Users/pereiro/projects/agentos-project/agentos-md/skills/agentos-pkg/index/104-index.md#Agentos.Agent.Adapter` is the durable index where this model lives; `agentos-py/notes/index/102-Agentos.Agent.Model.md` is the downstream local note that must follow it.
- **target repository:** `/Users/pereiro/projects/agentos-project/agentos-py`

## Impl.Index

### Agentos.Agent.Adapter

- `Agentos.Agent.Adapter` is the Agentos-facing adapter object pattern for representing an agent on a named operational surface
- concrete adapters are named `<Something>.Agent`
- `<Something>` names the surface served by the adapter, not a fixed ontology layer
- `<Something>.Agent` binds the configuration and behavior needed by that surface
- `<Something>.Agent` may be partially configured
- capability execution validates only the requirements of the invoked capability
- missing configuration is acceptable until a capability needs it
- `.Agent` is the public promise boundary; `<Something>` remains free to vary
- implementations may share stable primitives without inheriting a forced common model
- supporting primitives may include `Agent.Profile`, `Provider.Account`, `Provider.Home`, `Provider.Family`, credential artifacts, session references, run requests, and run results
- design examples from the canonical index: `Claude.Runner.Agent`, `Codex.Chatlas.Agent`, `Account.Monitor.Agent`, `Credential.Reconcile.Agent`; `<Something>` may be provider-, subsystem-, capability-, or workflow-shaped, or composed
- the design keeps provider-specific and subsystem-specific complexity below the `.Agent` boundary

### Design.Considerations

- this section exists so an implementer with no prior context can act; read it before touching code.
- **why the current shape is unhealthy:**
  - the same ~21-field surface is declared three times: `AgentConfig` (input), `AgentBase` (carrier), and the `Agent` protocol (contract), bridged by `agent_base_kwargs_from_config`. One field change touches three places.
  - every provider subclasses the single frozen `AgentBase`, so a session-only provider like `GeminiAgent` inherits `run`, `account_status`, `homes`, `accounts`, `sqlite_db_paths`, `ping`, etc. whether or not it uses them.
  - capability support is faked by raising: `AgentBase.run`/`account_status`/`_build_command` raise `CliError("does not support …")`. The type system claims every provider is a full agent; runtime disagrees. This is the core thing to remove.
- **what is already healthy and must be preserved:** the concept model in `102-Agentos.Agent.Model.md` (provider-native `<Provider>.Agent` / `<Provider>.SessionRef` / `<Provider>.Session`, normalize to `Session.Model` via explicit normalizers, `Relocation.Function` discipline for provider-local impl bodies). Provider modules (`claude/agent.py`, `codex/agent.py`) are well-organized and keep quirks below the boundary. Do not redesign these.
- **scope of this refactor:** this is a targeted repair of the agent primitive layer plus vocabulary alignment, not a re-architecture of the provider model or the session model. Do not invent new subsystems.

### Open.Decisions.Resolved

- the canonical index leaves open "whether capability contracts are modeled as protocols, methods, or separate agent subtypes". This impl-req resolves it as follows so the implementer does not re-open it:
  - **capabilities are modeled as small typed protocols** that a concrete adapter may or may not satisfy (structural typing), not as methods on a forced base that raise.
  - callers depend on the narrowest protocol they need; a provider that lacks a capability simply does not satisfy that protocol, and the unsupported path fails at the call site / capability resolution, not via a raising stub buried in a base class.
  - **`<Something>` is frozen to provider for this refactor.** Concrete provider classes (`<Provider>.Agent`) are the first and only adapter family delivered here. Subsystem-/capability-/workflow-shaped adapters (e.g. `Account.Monitor.Agent`) remain valid design directions but are explicitly out of scope; do not build them now.
  - **naming is decided:** base contract is `AgentAdapter`; capability facets use the `*Capable` suffix (`RunCapable`, `AccountStatusCapable`, `SessionDiscoveryCapable`). The base names the adapter; facets name traits. Concrete classes stay `<Provider>.Agent` (`ClaudeAgent`, `CodexAgent`, …). Do not reintroduce `*Agent` for protocols.
  - **`AgentBase` is removed.** It is neither kept as a data carrier (that preserves the duplication being killed) nor as a behavior-only base (the capability protocols remove the need for an inheritance layer). `AgentConfig` becomes the single field surface; concrete adapters hold/compose an `AgentConfig` and expose hot fields (`provider`, `home`, `account`, `profile_id`, `env`, …) via read-through accessors; shared behavior (command build, account-scope check, run-config resolution, fingerprint/identity/summary) moves to module-level helpers operating on the config.
  - if any of these decisions proves wrong during implementation, record the deviation in `Impl.Log` rather than silently diverging.

### Current.State

- provider-specific agent classes already exist: `src/agentos/claude/agent.py`, `src/agentos/codex/agent.py`, `src/agentos/copilot/agent.py`, `src/agentos/gemini/agent.py`, `src/agentos/opencode/agent.py`, `src/agentos/pi/agent.py`, `src/agentos/openclaw/agent.py`
- those classes already behave like adapters: they carry config and own provider-specific run, account, session-discovery, credential-refresh, and environment behavior
- `src/agentos/agent/primitives.py` still defines a broad `Agent` protocol and `AgentBase` data carrier with run, dry-run, account status, identity, homes, accounts, session paths, and ping fields on one shape
- the same ~21-field surface is restated three times — `AgentConfig`, `AgentBase`, and the `Agent` protocol — and bridged by `agent_base_kwargs_from_config`; this triple duplication is the primary structural debt
- `AgentBase.run`, `AgentBase.account_status`, and `AgentBase._build_command` raise `CliError("does not support …")`; every provider subclasses `AgentBase`, so session-only providers (e.g. `GeminiAgent`) inherit runner/account methods they cannot fulfil (faked polymorphism)
- `AgentConfig.instance_id`, `AgentBase.instance_id`, `AgentConfigEntry.raw_instance`, `select_agent_configs(selected_instance_ids=...)`, and multiple JSON payload fields still expose old instance vocabulary
- `src/agentos/agent/sessions.py` uses `ProviderAgentContext` but its fields and output still say `provider_instance_*`
- `agentos-py/notes/index/102-Agentos.Agent.Model.md` still describes the older provider-native model and mentions `ProviderInstance` as transitional
- current profile config is already file-backed under `~/.agentos/profiles/*.json`; `agent.providers` remains only for provider-global defaults such as `cli_command`

### Accepted.Direction

- **sequence matters:** collapse the structural duplication and remove the raising stubs *before* introducing the capability-protocol taxonomy. Do not build new protocols on top of the god-base; reduce the god-base first, then express capabilities. This avoids replacing one over-broad abstraction with several over-fine ones.
- collapse the three parallel field surfaces (`AgentConfig`, `AgentBase`, `Agent` protocol). `AgentConfig` becomes the single field surface; **`AgentBase` is removed** (concrete adapters hold/compose an `AgentConfig` and expose hot fields via read-through accessors; shared behavior moves to module-level helpers); the contract is derived from capability protocols, not a restated field list.
- remove the raise-on-unsupported stubs (`AgentBase.run`/`account_status`/`_build_command` raising `CliError`); replace with capability protocols a provider either satisfies or does not.
- split the current broad `Agent` protocol into small capability protocols (see `Capability.Contracts`).
- keep shared helper code only where it removes real duplication without forcing every adapter into one data model.
- make `Agent.Profile` a supporting primitive, not the root concept.
- keep concrete provider classes as the only adapter family in this change (see `Open.Decisions.Resolved`).

#### Rename targets (explicit goal)

- this refactor renames the relevant objects and fields to express the adapter model directly; renaming is a deliverable, not a side effect.
- **objects:**
  - the broad `Agent` protocol → `AgentAdapter` (smallest common contract) + `*Capable` capability facets (see `Capability.Contracts`).
  - `AgentBase` → removed (see `Open.Decisions.Resolved`); `AgentConfig` is the single field surface; shared behavior moves to module-level helpers.
  - concrete provider classes remain `<Provider>.Agent` (`ClaudeAgent`, `CodexAgent`, …) and are documented as the provider adapters.
- **fields / vocabulary:**
  - `instance_id` (config, base, kwargs, summaries, errors) → `profile_id` where the value identifies `~/.agentos/profiles/<id>.json`.
  - session/diagnostic `provider_instance_*` (and `ProviderAgentContext.instance_*`) → `agent_adapter_*` or `agent_profile_*` per meaning.
  - remove stale `ProviderInstance` / `Provider.Instance` terminology from code, tests, docs, and user-facing JSON.
- **naming rule (decided):** base = `AgentAdapter`, capability facets = `*Capable`; never `*Agent` for protocols.
- do not add backward-compatibility aliases unless the implementer finds a concrete external consumer that cannot be migrated in the same change (per `agentos-py/AGENTS.md`); record any such exception in `Impl.Log`.

### Capability.Contracts

- `AgentAdapter` — the smallest common contract: provider/surface identity, summary, stable identity key or fingerprint if needed by coordination. Every concrete provider satisfies this.
- `RunCapable` — runner behavior: `run`, `run_dry`, command config, run config, ping behavior where used.
- `AccountStatusCapable` — monitor/account-status behavior: account context, account-status execution, usage recording flags.
- `SessionDiscoveryCapable` — Chatlas/session behavior: discover provider-native refs and load provider-native sessions.
- naming rule: base = `AgentAdapter`; capability facets = `*Capable`; never `*Agent` for protocols.
- profile/account/home scope checks live in shared helpers, not in every capability contract.
- a provider that lacks a capability simply does not satisfy that protocol; there is no raising stub. Callers resolve the capability and fail at the call site with a clear message when it is absent.
- providers may have additional provider-specific methods without promoting them to a common protocol.

### Subsystem.Map

- runner CLI uses adapters through `agentos agent run`, `agentos agent ping`, command construction, profile/home/account selection, and provider CLI execution
- monitor uses adapters through account status, ping/prime workflows, usage registry writes, and provider-specific account status implementations
- account commands use adapters and provider-specific registries for register, link, reconcile, status, materialize, and credential refresh
- Chatlas/session commands use adapters for provider-native session ref discovery, session loading, session copy, query, stats, and normalized export handoff
- profile commands use `Agent.Profile` primitives and should not expose provider-instance naming
- tests under `tests/test_agent_profiles.py`, `tests/test_agent_run_account_preflight.py`, `tests/test_agent_monitor_auto_prime.py`, `tests/test_agent_sessions.py`, account registry/reconcile tests, and session copy tests are the main behavior guardrails

### No.Legacy.Allowed

- do not leave a parallel broad `Agent` protocol and new capability protocols active at the same call sites
- do not leave the three-way field duplication (`AgentConfig` / `AgentBase` / `Agent` protocol) in place
- do not leave any raise-on-unsupported capability stub on a base class
- do not leave old `ProviderInstance` docs as current truth
- do not leave JSON output keys named `instances` or `provider_instance_*` unless the `Impl.Log` records a deliberate external compatibility exception
- do not keep `instance_id` as the main internal name when the value is a profile id
- avoid compatibility shims; `agentos-py/AGENTS.md` says not to add backward-compatibility aliases unless explicitly requested

### Test.Strategy

- add RED/GREEN tests at public boundaries before changing each behavior path
- prefer CLI-command functions and public library entry points over private helper tests
- preserve existing behavior first, then rename vocabulary
- run focused test groups after each slice; run broader agent tests before handoff
- update expected JSON payloads and text output deliberately when vocabulary changes

## Execution.Plan

### Slice 1 - Collapse Field-Surface Duplication And Remove Raising Stubs

Status: pending.

This slice precedes the capability protocols on purpose (see `Accepted.Direction` sequencing). Reduce the god-base first.

Change:

- Remove the three-way field restatement: `AgentConfig` is the single field surface. Remove `AgentBase`; concrete adapters hold/compose an `AgentConfig` and expose hot fields via read-through accessors, and shared behavior (command build, account-scope check, run-config resolution, fingerprint/identity/summary) moves to module-level helpers. Stop maintaining the broad `Agent` protocol as a parallel field list.
- Remove the raise-on-unsupported stubs (`AgentBase.run`/`account_status`/`_build_command` raising `CliError`). Where a provider genuinely lacks a capability, the capability must be absent rather than a raising override.
- Keep all provider behavior byte-for-byte; this is structure-only.

Observable result:

- The agent primitive layer no longer declares the same field surface three times.
- No base class carries a raising "does not support" capability method.
- All existing agent tests still pass with unchanged behavior.

RED.GREEN.Test.Suite:

- Add a focused test asserting a session-only provider object does not expose a runnable/account-status capability (instead of exposing one that raises).
- Run `uv run pytest tests/test_agent_profiles.py tests/test_agent_sessions.py tests/test_agent_run_account_preflight.py -q`.

### Slice 2 - Establish Adapter Capability Contracts

Status: pending.

Change:

- Introduce the capability protocols from `Capability.Contracts` (`AgentAdapter` base + `RunCapable`, `AccountStatusCapable`, `SessionDiscoveryCapable`) in the agent primitive layer or a new nearby module.
- Make concrete provider classes satisfy the protocols they implement via structural typing; do not force unimplemented capabilities onto a provider.
- Replace the broad protocol at the session-discovery boundary first (lowest-risk: most providers implement it and it has clean tests), then runner resolution.

Observable result:

- At least one public path depends on a narrow capability protocol instead of the broad `Agent` protocol.
- Existing provider classes still load from profiles and run the same behavior.

RED.GREEN.Test.Suite:

- Add or update a focused test proving a provider that only supports session discovery type-checks against `SessionDiscoveryCapable` but not against `RunCapable`/`AccountStatusCapable`.
- Run `uv run pytest tests/test_agent_profiles.py tests/test_agent_sessions.py -q`.

### Slice 3 - Rename Objects And Profile Identity To Adapter Vocabulary

Status: pending.

This slice executes the `Rename targets` deliverable. Behavior is already preserved by Slices 1-2; this is vocabulary alignment.

Change:

- Rename the contract objects: broad `Agent` protocol → `AgentAdapter` + `*Capable` capability protocols. (`AgentBase` is already gone after Slice 1.) Keep concrete `<Provider>.Agent` class names.
- Rename internal profile identity fields and variables from `instance_id` to `profile_id` where they refer to `~/.agentos/profiles/<id>.json` (config, base/helper, `agent_base_kwargs_*`, selector messages, summaries, error strings, fake test agents, profile-scope helpers).
- Keep the profile JSON field `id` unless a separate schema change is explicitly needed.
- Apply one consistent suffix across the contract family; do not mix `*Agent` and `*Adapter`.

Observable result:

- The contract layer reads as the adapter model; no object is named to imply a forced common root.
- Profile commands, run commands, and tests pass while code no longer treats profile ids as instances.

RED.GREEN.Test.Suite:

- Add a public-boundary test that profile list/show/run error messages use profile vocabulary for unknown or unsupported profiles.
- Run `uv run pytest tests/test_agent_profiles.py tests/test_agent_run_account_preflight.py -q`.

### Slice 4 - Runner Adapter Boundary

Status: pending.

Change:

- Make `agentos agent run`, `agentos agent ping`, dry-run rendering, model/prompt handling, account override checks, and provider CLI command execution depend on `RunCapable`.
- Keep Claude and Codex provider-specific run behavior intact: Claude token injection, `CLAUDE_CONFIG_DIR`, Codex preflight/materialization, `CODEX_HOME`, non-interactive command translation, credential refresh.
- Keep provider-global `agent.providers.<provider>.cli_command` behavior intact.

Observable result:

- Existing run and ping behaviors work through the smaller runner contract.
- Unsupported run providers fail at run execution with a clear capability error.

RED.GREEN.Test.Suite:

- Add/update tests for unsupported run provider behavior through the public run path.
- Run `uv run pytest tests/test_agent_profiles.py tests/test_agent_run_account_preflight.py tests/test_claude_account_status.py tests/test_codex_account_reconcile.py -q`.

### Slice 5 - Account And Monitor Adapter Boundary

Status: pending.

Change:

- Make account status, monitor workflows, auto-prime, usage registry recording, and account-state rendering depend on `AccountStatusCapable`.
- Preserve current provider behavior for Claude, Codex, and Copilot account status.
- Keep monitor execution on the correct system/provider home when a profile has multiple homes.
- Preserve existing account registry/reconcile behavior and credential materialization behavior.

Observable result:

- `agentos agent accounts monitor --once --json` still works.
- Account status commands still surface provider-specific errors only when account-status capability is invoked.

RED.GREEN.Test.Suite:

- Add/update one monitor boundary test proving monitor accepts only account-status-capable adapters.
- Run `uv run pytest tests/test_agent_monitor_auto_prime.py tests/test_agent_account_registry.py tests/test_agent_account_events.py tests/test_claude_account_reconcile.py tests/test_codex_account_reconcile.py tests/test_claude_account_status.py -q`.

### Slice 6 - Chatlas And Session Discovery Adapter Boundary

Status: pending.

Change:

- Make session list/query/stats/copy/export support use `SessionDiscoveryCapable`.
- Rename `ProviderAgentContext` fields from instance vocabulary to adapter/profile vocabulary.
- Rename session URI/query fields and diagnostic JSON keys away from `provider_instance_*`.
- Preserve provider-native `SessionRef` and `Session` ownership: provider adapters discover refs and load sessions; normalizers produce provider-neutral `Session.Model`.
- Coordinate with `agentos-chatlas-py` if current Chatlas code consumes these JSON fields from `agentos-py`.

Observable result:

- Session discovery, session copy, and Chatlas-facing selection still work with provider-native refs.
- Diagnostic JSON no longer presents provider instances as the current model.

RED.GREEN.Test.Suite:

- Add/update tests for session list/query/copy JSON vocabulary and selection behavior.
- Run `uv run pytest tests/test_agent_sessions.py tests/test_agent_session_copy.py -q`.
- If Chatlas integration tests are available from this repo or sibling package, run the focused Chatlas query/export tests that consume agent session output.

### Slice 7 - Provider-Specific Adapter Modules

Status: pending.

Change:

- Review each concrete provider adapter and keep provider-specific quirks below its `.Agent` boundary.
- Remove empty `validate_profile()` stubs unless they are replaced by real provider-profile validation.
- Keep shared code for command construction, profile scope, home specs, provider family specs, and account contexts as primitives only.
- Do not force providers into identical fields if a provider does not need a capability.

Observable result:

- Provider modules remain navigable and provider-specific behavior is easier to locate.
- No provider-specific account/session/run behavior is moved into generic coordination code without a clear primitive boundary.

RED.GREEN.Test.Suite:

- Run `uv run pytest tests/test_agent_profiles.py tests/test_agent_sessions.py tests/test_agent_account_registry.py -q`.

### Slice 8 - Documentation And Index Realignment

Status: pending.

Change:

- Canonical first: in `agentos-md/skills/agentos-pkg/index/104-index.md`, make `Agentos.Agent.Adapter` the current truth and demote/remove the stale `Provider.Instance` block (it is currently only marked "candidate replacement"). This is the durable home and must lead.
- Then align the downstream local notes to follow it: update `agentos-py/notes/index/102-Agentos.Agent.Model.md` (drop the `ProviderInstance` "transitional" framing) and `agentos-py/notes/index/001-ontology.md` and any note still presenting `ProviderInstance` or a broad `<Provider>.Agent` as the current root model.
- Ensure docs still explain `<Provider>.SessionRef`, `<Provider>.Session`, and `Session.Model` normalization boundaries.

Observable result:

- Durable design docs tell the same story as the code.
- A future agent reading only the index does not reintroduce `ProviderInstance`.

Checks:

- Run the agentos-pkg index linter for `agentos-md/skills/agentos-pkg/index` (canonical surface).
- Run `agentos index linter --index /Users/pereiro/projects/agentos-project/agentos-py/notes/index --json` if the local index linter supports project-local indexes.

### Slice 9 - No Legacy Sweep And Full Validation

Status: pending.

Change:

- Search for remaining active-code uses of `instance`, `instances`, `ProviderInstance`, and `provider_instance`.
- Remove or rename remaining current-surface uses that conflict with the adapter model.
- Leave archived notes alone unless they are referenced as current truth.
- Update tests and snapshots to the final vocabulary.

Observable result:

- Active code, tests, and current docs use adapter/profile/provider vocabulary consistently.
- Existing user-facing functionality remains available.

Validation:

```sh
uv run pytest tests/test_agent_profiles.py tests/test_agent_run_account_preflight.py tests/test_agent_monitor_auto_prime.py tests/test_agent_sessions.py tests/test_agent_session_copy.py tests/test_agent_account_registry.py tests/test_agent_account_events.py tests/test_claude_account_reconcile.py tests/test_codex_account_reconcile.py tests/test_claude_account_status.py -q
uv run ruff check src/agentos/agent src/agentos/claude src/agentos/codex src/agentos/copilot src/agentos/gemini src/agentos/opencode src/agentos/pi src/agentos/openclaw tests
python -m compileall -q src/agentos tests
git diff --check
```

Manual smoke checks:

```sh
agentos agent list --json
agentos agent run --profile claude-jp --dry-run
agentos agent accounts monitor --once --json
agentos agent sessions list --json
```

## Risks

- JSON vocabulary changes may affect sibling packages or scripts that parse `instances` or `provider_instance_*`.
- `instance_id` is widely used in tests and fake agents; a mechanical rename can hide semantic mistakes.
- Chatlas/session code may have cross-repository consumers outside `agentos-py`; verify before removing old public fields if the consumer cannot be updated in the same implementation.
- Splitting protocols can produce over-abstraction if the executer creates too many tiny one-use interfaces; prefer capability contracts that match real subsystem boundaries.

## Deviation.Triggers

- If a public JSON compatibility boundary must remain, record the exception in `Impl.Log` and make the old field explicitly deprecated rather than silently preserving legacy vocabulary.
- If a provider cannot satisfy a proposed capability protocol without fake fields, narrow the protocol.
- If a subsystem needs a different adapter shape, create a `<Something>.Agent`-specific contract instead of expanding the common base.
- The decision is to remove `AgentBase`. If implementation proves a thin shared base is genuinely unavoidable, keep it behavior-only (never a data carrier, never the conceptual root) and record why in `Impl.Log`.

## Acceptance.Signals

- provider-specific `.Agent` classes remain the operational adapters.
- runner, monitor, account, profile, and Chatlas/session functionality remain available.
- the field surface is no longer restated across `AgentConfig` / `AgentBase` / `Agent` protocol.
- no base class exposes a raise-on-unsupported capability method.
- common contracts are capability-shaped, not one broad forced `Agent` model.
- the contract objects are named to express the adapter model with one consistent suffix; nothing is named to imply a forced common root.
- profile identity is named as profile identity in active code.
- provider-instance vocabulary is removed from active current surfaces or recorded as a deliberate compatibility exception.
- the canonical `agentos-pkg` index describes `Agentos.Agent.Adapter` as current and no longer presents `Provider.Instance` as a live model; local notes follow it.
- focused tests, lint, compile check, and manual smoke checks pass.

## Impl.Log

- 2026-06-13: Created from in-chat implementation design after code alignment review. User explicitly allowed large refactors and requested the plan preserve existing Agentos functionality while reaching a cleaner and healthier model across runners, monitor, accounts, profiles, and Chatlas/session subsystems.
- 2026-06-13: Revised after architecture review. Reframed the core problem as the three-way field duplication (`AgentConfig`/`AgentBase`/`Agent` protocol) plus raise-on-unsupported faked polymorphism. Added `Design.Considerations` and `Open.Decisions.Resolved` (capabilities = structural protocols; `<Something>` frozen to provider for this change). Made object renaming an explicit deliverable (`Rename targets`). Resequenced: collapse duplication + remove raising stubs (Slice 1) before introducing capability protocols (Slice 2); object/field renames in Slice 3. Flipped doc realignment to treat `agentos-pkg` index as canonical and local notes as downstream.
- 2026-06-13: Resolved the two remaining open mechanics on user request. Naming decided: base contract `AgentAdapter`, capability facets `*Capable` (`RunCapable`/`AccountStatusCapable`/`SessionDiscoveryCapable`), concrete classes stay `<Provider>.Agent`. `AgentBase` decided removed (not kept as carrier or behavior base): `AgentConfig` is the single field surface, adapters compose it with read-through accessors, shared behavior moves to module-level helpers.
