# Minimal Active Account Usage Capability - design-session

## Session.Abstract

Design a minimal active account usage/status capability for Agentos provider agents.

The capability will support the account monitor's limits-tracking workflow without restoring the deprecated `agent accounts stats` command as a whole. Deprecated account-stats code can be used as implementation evidence, but the active system is being redesigned around current Agentos provider-agent boundaries, registered accounts, linked homes, and the shared external process utility.

Current direction:

- Add account context to the provider agent object.
- Expose a direct provider-agent capability named `account_status`.
- Do not introduce an `AccountStatusRequest` object in the first design.
- Use `account_status(...)` keyword arguments for fetch-process controls.
- Reuse existing account registry, link registry, provider home inspection, and process-runner machinery instead of duplicating account setup validation.
- Treat identity mismatch, missing setup, and provider fetch problems as account-status errors that monitor workflows can render without crashing the loop.

## Design.Index

### AgentAccountContext

`AgentAccountContext` identifies the registered account a provider agent is expected to operate as.

Proposed model:

```python
@dataclass(frozen=True)
class AgentAccountContext:
    provider: str
    account: str
```

`AgentConfig`, `AgentBase`, and the `Agent` protocol should carry:

```python
account: AgentAccountContext | None = None
```

The account context is not a home. The provider agent still has its normal `home` field. The design invariant is:

```txt
agent.account = registered account identity
agent.home = provider execution context
```

A registered account may be linked to multiple homes. A home is an execution context linked to an account; it is not owned by the account.

### Registered Account Agent Construction

Monitor code should construct account-bound provider agents explicitly:

```python
agent = build_registered_account_agent(
    provider="codex",
    account="main",
    home=home,
)
status = agent.account_status(refresh_usage=True)
```

The default monitor/system home for a target remains:

```txt
~/.agentos/agent/homes/<provider>/<account>
```

This path is a default execution home for Agentos system work. It is not account-owned state.

`build_registered_account_agent(...)` should reuse existing machinery:

- `load_account(provider, account)` for registered account existence.
- existing provider/default `AgentConfig` resolution and home override behavior.
- `agent_from_config(...)` provider-agent construction.
- a small account-context attachment step.

The builder must not bootstrap, repair, or link homes.

### AccountStatus Capability

Provider agents should expose:

```python
agent.account_status(
    *,
    refresh_usage: bool = False,
    methods: tuple[str, ...] | None = None,
    config: Mapping[str, object] | None = None,
) -> AccountStatus
```

There is no `AccountStatusRequest` in the first design. Account selection and execution context live on the agent object. Keyword arguments only control the fetch process:

- `refresh_usage`: whether slow/live usage probes may run.
- `methods`: optional method narrowing, such as auth-only or auth-plus-limits.
- `config`: provider-specific fetch-method configuration, not account identity.

The common capability entrypoint should be similar in status to `run(...)` and `run_dry(...)`: a provider-agent capability with one shared interface and provider-owned implementation details.

### AccountStatus Model

`AccountStatus` should be a standard object rather than provider-shaped ad hoc dictionaries.

Settled first shape:

```txt
AccountStatus
  provider
  account
  home
  check_status
  usage_status
  link_state
  expected_identity
  fetched_identity
  identity_match
  auth_summary
  usage_summary
  limits
  errors
  usage_errors
  raw
```

Status fields preserve the useful split from the deprecated implementation:

```txt
check_status = ok | error
usage_status = ok | error | unavailable
```

`errors` captures setup/auth/check-level problems. `usage_errors` captures usage/limits fetch problems. This distinction is important because an account-status fetch can be partially useful: auth and identity may be valid while usage/limits refresh fails.

`raw` carries provider-specific status payloads and other details that should not be forced into the generic model yet.

### Account Limits Model

The new status capability should revive the useful parts of the deprecated account-limit model:

```txt
AccountLimit
  limit_class
  limit_name
  limit_label
  usage_over_time
  provider_limit

UsageOverTimeLimitData
  used_percent
  period_started_at
  period_ends_at
  period_duration_mins
  resets_at
```

The first important limit class is:

```txt
usage_over_time
```

Provider examples:

- Codex primary/secondary windows become usage-over-time limits.
- Claude subscription/live refresh limits become usage-over-time limits.
- Copilot quota windows can later become usage-over-time limits if reintroduced.

`provider_limit` remains the escape hatch for provider-specific fields such as Codex limit id/window key or Claude rate-limit type/status.

### Partial Success Semantics

`account_status(...)` should prefer returning an `AccountStatus` object over failing the whole capability when a partial result is available.

Valid partial result example:

```txt
check_status = ok
identity_match = verified
usage_status = error
usage_errors = [...]
limits = ()
```

Whole-capability exceptions should be reserved for programming errors or cases where no meaningful `AccountStatus` can be formed. Expected operational problems should be represented in `AccountStatus.errors` or `AccountStatus.usage_errors`.

### Previous Implementation Lessons

The deprecated implementation should influence the new model in these ways:

- Keep separate account/check status and usage status.
- Keep separate account/check errors and usage errors.
- Keep normalized account limits.
- Keep provider raw payloads available.
- Do not keep the old large public dict as the provider-agent capability boundary.
- Do not keep instance-id-centric account identity as the primary model.

The new model is registered-account-context-centric:

```txt
provider + account + home
```

not:

```txt
provider instance id
```

### Setup Validation Reuse

`account_status(...)` assumes the provider home is already prepared and linked. It does not bootstrap or repair setup.

Validation should reuse existing machinery:

1. `agent.account` is present.
   - New model check.
2. `agent.home` is present.
   - Existing `AgentBase.home` model.
3. Registered account exists.
   - Existing `load_account(provider, account)`.
4. Home is linked or inspectable for the registered account.
   - Codex: existing `inspect_codex_account_home(home=...)`.
   - Claude: existing claimed-link registry inspection, currently exposed in CLI code as claimed/unverified behavior.
5. Provider-specific status fetch can run from that home.
   - Implemented inside provider `account_status(...)`.

The first implementation should add thin adapters around existing registry/home inspection behavior where needed. It should not fork or duplicate account registration, link, artifact, or home inspection logic.

### Link Verification Semantics

Provider link proof is not uniform.

Codex can inspect `auth.json`, compare artifact/account registry data, and return strong states such as `verified`, `stale`, `missing`, `broken`, or `mismatched`.

Claude currently has metadata-only registration plus a claimed home link. Claimed links report `claimed-unverified`; they do not prove browser-login identity by themselves.

This difference is acceptable. `AccountStatus` should preserve the distinction instead of pretending every provider can produce the same link proof.

### Fetched Identity Validation

`AccountStatus` must validate fetched provider identity against the configured `AgentAccountContext` whenever the provider exposes a stable identity field.

This is a second validation layer after setup validation:

```txt
setup validation:
  agent has account
  agent has home
  registry account exists
  home link state is acceptable enough to try

fetched status validation:
  provider status fetch runs
  fetched provider identity is compared with registry identity
  mismatch becomes an account-status error
```

Provider examples:

- Codex can compare fetched `account_id` against the registered account record's `account_id`.
- Claude can compare fetched email or stable auth identity only if `claude auth status --json` exposes enough identity data.
- If a provider does not expose enough stable identity data, identity verification should be `unknown`, not `verified`.

Identity mismatch is an `AccountStatus.errors` entry. It must not crash the monitor loop.

### External Process Utility Boundary

Use the current Agentos process utility for normal one-shot provider commands:

```python
run_process(..., mode="capture")
```

Do not force specialized transports through `_core.process` when the provider needs something else:

- Codex `app-server` JSON-RPC over stdin/stdout remains provider-owned.
- Claude PTY/statusline mechanics remain provider-owned if needed.
- Copilot HTTP usage fetch remains provider-owned if reintroduced later.

The shared process utility should not know provider names, account payloads, account identity rules, or usage parsing rules.

## Session.Notes

### Evidence From Active Code

- Active `AgentBase` / `Agent` expose `run(...)` and `run_dry(...)`, but no account-status capability.
- Active `AgentConfig` / `AgentBase` already have `home`, `env`, `cli_command`, timeout, and provider execution fields.
- Active `agent_config_with_home_override(...)` can reuse provider home path derivation for direct targets and identity anchors.
- Active `load_account(...)`, `load_links(...)`, and provider account registry modules already own registration/link state.
- Active monitor config already validates registered accounts and defaults target homes to `~/.agentos/agent/homes/<provider>/<account>`.
- Active `_core.process.run_process(...)` supports `terminal`, `capture`, and `stream`.

### Evidence From Deprecated Code

- Deprecated `AccountStatsRequest` carried fetch behavior and provider config, but account identity should now live on the agent object.
- Deprecated `AccountLimit` and `UsageOverTimeLimitData` are useful model evidence for the new `AccountStatus.limits` shape.
- Deprecated account/check status and usage status were correctly separated and should remain separate in the new `AccountStatus` model.
- Deprecated account/check errors and usage errors were correctly separated and should remain separate in the new `AccountStatus` model.
- Deprecated Codex implementation used captured CLI auth plus provider-owned `app-server` JSON-RPC for rate limits.
- Deprecated Claude implementation used captured CLI auth plus provider-owned statusline/stream-json live usage mechanics.
- Deprecated Copilot implementation used CLI probing plus GitHub HTTP usage fetch.

### Open Questions

- Exact `AccountStatus` dataclass shape and whether `auth`, `limits`, and `errors` should be typed dataclasses immediately or staged as structured dictionaries.
- Exact `identity_match` vocabulary, for example `verified`, `mismatched`, `unknown`, `unavailable`.
- Whether to extract the current Claude claimed-home inspection out of CLI code into reusable provider/account-registry machinery before wiring `account_status`.
- First provider slice: Codex-only first, or Codex plus Claude setup/status skeleton.

## Session.Log

- 2026-05-14: Started new design-session scope for minimal active account usage capability.
- 2026-05-14: Researched active provider-agent APIs, account registry/link machinery, monitor target config, `_core.process`, and deprecated account-stats implementation.
- 2026-05-14: Converged that account context belongs on the agent object, not in an `AccountStatusRequest`.
- 2026-05-14: Removed `AccountStatusRequest` from the first design; `account_status(...)` keyword arguments model fetch-process controls directly.
- 2026-05-14: Converged that account homes are execution contexts linked to accounts, not account-owned homes.
- 2026-05-14: Converged that setup validation should reuse existing account registry, link registry, and provider home-inspection machinery.
- 2026-05-14: Converged that fetched provider identity must be checked against the configured account context whenever possible, with mismatch represented as an account-status error.
- 2026-05-14: Checked the deprecated account-stats implementation and adopted its useful status split: account/check status stays separate from usage status, and account/check errors stay separate from usage errors.
- 2026-05-14: Settled the first `AccountStatus`, `AccountLimit`, and `UsageOverTimeLimitData` model shapes for the active provider-agent capability.
- 2026-05-14: Created implementation handoff `596-minimal-active-account-usage-capability-impl-req.md` after execution was requested and this design-session artifact was found not directly executable by the Impl.Executer workflow.
