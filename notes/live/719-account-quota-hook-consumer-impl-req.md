# 719 — account quota hook consumer

## Impl.Abstract

- **Scope:** make `agent.turn.stop` publish Codex quota observations into the normal Agentos usage registry, keep hook-context sampling independent, and let account monitoring use fresh registry observations before launching a provider usage probe.
- **Status:** implemented and verified.
- **Source:** autonomous `$agentos-hugentics --impl --dev --AUTO` execution gate. ^c20260811-47u
- **Out of scope:** account-wide token accounting, non-Codex provider adapters, usage-registry retention redesign, daemon delivery, and new hook wildcard or priority mechanics.

## Impl.Index

### Hook.Consumer.Ownership

- `Agentos.Hook` dispatches exact names to subsystem callbacks sequentially; `agent.turn.stop` is the accepted semantic boundary after an agent turn terminates.
- The quota callback belongs to account usage, not the running monitor loop. It must execute through the ordinary one-shot `agentos hook` composition even when no monitor process exists.
- `ctx_type=codex` selects the provider adapter inside the callback; the provider-neutral dispatcher continues treating `ctx` as opaque.

### Sampling.Independence

- Development sampling is an `agent.prompt.submit` consumer with its own private bounded persistence.
- It must not import account usage reporting, resolve provider homes, or write the usage registry.
- Remove the obsolete direct `agent accounts usage-report` sampling surface instead of retaining two ingress paths.

### Codex.Quota.Observation

- Codex Stop-hook JSON identifies the session but does not carry quota data directly. The adapter uses `transcript_path`, or the validated `session_id` plus provider-home hint, to locate the rollout and read its latest `event_msg.payload.type=token_count` rate-limit snapshot.
- The adapter validates the rollout session identity and the Codex home credential identity, resolves the owning registered Agentos account, normalizes the native snake-case snapshot into the existing Codex rate-limit payload shape, and appends it with distinct `session_hook` provenance.
- The observation carries quota percentage, duration, and reset time only. `account/usage/read` token-history data is outside the account monitor contract and should leave the Codex live-fetch hot path.

### Monitor.Registry.First

- The usage registry is the shared observation surface. Codex hook records are account-scoped observations even when the observing home differs from the monitor target home.
- Monitor setup selects the newest compatible record across live-probe and hook sources. A scheduled refresh reuses a valid record younger than the configured refresh interval and whose carried windows have not reset; otherwise it calls the existing provider account-status path.
- Existing live fetching and registry fallback remain the path for idle accounts, missing/invalid hook observations, and stale windows.

## Impl.Agendix

- **Touched:** `Agentos.Hook`, `Agentos.Hook.Invocation`, and `Agent.Hook` in `agentos-pkg/design/113-design.md`, especially exact callback registration, opaque context, and `agent.turn.stop`. ^c20260811-5u ^c20260811-13u ^c20260811-32u
- **Touched:** `Normalization.Pipeline::Account.Usage.Model` in `agentos-pkg/design/104-design.md`: provider-native usage artifacts normalize into lists of `Usage.Limit`s.
- **Touched:** `Account.Management` in `agentos-pkg/design/104-design.md`: account identity, not home aliases, binds provider state to the owning account.
- **Execution gate:** implement the agreed quota callback and registry-first monitor behavior. ^c20260811-47u

## Execution.Plan

### Vertical.Slice 1 — Independent bounded hook sampler

- **Status:** complete.
- **Targets:** `src/agentos/hooks/sampling.py`, sampler tests, CLI composition documentation, and removal of the obsolete sampling/report command.
- **RED:** assert prompt sampling needs only the invocation and retains a bounded private sample set without provider-home environment state.
- **GREEN:** move sampling persistence fully under `agentos.hooks` and remove its dependency on `agentos.agent.usage_report`.
- **Check:** focused sampler and hook CLI tests.

### Vertical.Slice 2 — Codex Stop quota consumer

- **Status:** complete.
- **Targets:** provider-owned Codex hook adapter, usage registry account-level lookup support, CLI registrar composition, and provider tests.
- **RED:** dispatch a Codex `agent.turn.stop` fixture and assert one normalized `session_hook` usage record is written for the credential-resolved account.
- **GREEN:** locate and validate the rollout, extract the latest quota snapshot, resolve account identity, normalize it, and append it.
- **Check:** consumer tests cover explicit transcript path, session lookup fallback, irrelevant context types, and invalid/unregistered identity failure isolation.

### Vertical.Slice 3 — Registry-first account monitor

- **Status:** complete.
- **Targets:** usage registry reader and `limits-tracking` workflow.
- **RED:** assert fresh hook quota skips `resolve_account_runtime_agent`, while stale or reset observations retain the live fetch.
- **GREEN:** select the newest compatible account observation, parse it through the existing Codex limit normalizer, and apply the monitor freshness policy.
- **Check:** focused usage-registry and monitor workflow suites.

### Vertical.Slice 4 — Codex native wiring and verification

- **Status:** complete.
- **Targets:** Codex live account-status request sequence, installed CLI, and `~/.codex/hooks.json` Stop mapping.
- **Change:** remove the unused `account/usage/read` request, install the `agent.turn.stop` Agentos handler beside existing Stop hooks, and exercise a native Codex hook path.
- **Check:** full `agentos-py` and `agentos-cli` tests, Ruff, diff check, editable CLI reinstall, and a monitor/registry smoke test that does not disclose raw hook context.

## Impl.Log

- **Decision:** keep quota acquisition in a provider-owned callback and monitoring in the account subsystem; the hook dispatcher remains provider-neutral.
- **Decision:** registry freshness is the monitor refresh interval; a carried quota window whose reset has passed is not reusable even when the registry write is recent.
- **Decision:** quota observations are resolved to an Agentos account by credential identity; provider home is retained only as observation provenance.
- **RED:** the independent sampler initially failed because it still imported `agentos.agent.usage_report`; the Codex consumer and registry-first monitor tests then failed before their callback and freshness paths existed.
- **GREEN:** `agent.prompt.submit` now writes only a private bounded opaque-context log; `agent.turn.stop` writes normalized Codex `session_hook` quota observations; the monitor reuses fresh compatible registry data and falls through to the existing provider probe when data is absent, invalid, stale, or reset.
- **Provider-home refinement:** `CODEX_HOME` identifies the credential/account provenance, but a harness-owned transcript may live under the default `~/.codex` tree. Transcript resolution therefore validates candidates from both the hinted and default Codex session roots instead of treating the environment hint as proof of transcript ownership.
- **Native timing observation:** Codex may persist a first turn's first `rate_limits` event after its `Stop` hook. Such a first-turn callback produces no observation; later stops see the prior/latest persisted snapshot, and the monitor's absent-data fallback remains authoritative.
- **Verification:** `agentos-py` full suite: 949 passed; `agentos-cli` full suite: 75 passed; focused changed-file Ruff and format checks passed; both diffs pass `git diff --check`; `~/.codex/hooks.json` parses; installed `agentos hook` and account-monitor help surfaces match the design.
- **Live verification:** a native Codex Stop hook wrote a `session_hook` record for the credential-resolved `tk` account, and `agentos agent accounts monitor --once --json` consumed that record with `refresh_count=0` instead of launching another provider quota request.
- **Codex configuration:** both Agentos hook commands use a 5000 timeout value, aligned with the installed Codex hook configuration's millisecond-scale values. Current official OpenAI documentation does not expose this field, so the local Codex convention is the operational authority.
- **Repository lint note:** repository-wide `agentos-py` Ruff is currently blocked by four unrelated errors in concurrent tournament/workspace files; no unrelated files were changed to conceal them.
