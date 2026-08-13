# 730 — Claude statusLine hook ingestion

## Impl.Abstract

- **Scope:** add `agent.statusline.context` as a provider-neutral Agentos hook semantic, map Claude Code's native `statusLine` callback onto it, normalize Claude quota snapshots into the shared usage registry, and let account monitoring reuse fresh hook observations before probing the provider.
- **Status:** execution pending.
- **Source:** autonomous `$agentos-hugentics --impl --dev --AUTO` authorization. ^c20260813-26u
- **Out of scope:** changing `agent.turn.stop`, persisting complete statusLine contexts, daemon dispatch, registry retention redesign, or adding equivalent mappings for other providers.

## Impl.Index

### StatusLine.Hook.Semantic

- `agent.statusline.context` means an agent harness has published its current native status-line context.
- The hook foundation treats the JSON object as opaque and dispatches exact-name callbacks sequentially; `ctx_type` selects provider behavior inside consumers, never inside dispatch. ^c20260811-5u ^c20260811-13u
- Claude Code maps its native `statusLine` callback directly to this semantic instead of pretending quota data exists in `agent.turn.stop`.

### Claude.Usage.Consumer

- The Claude provider callback accepts only `ctx_type=claude-code`, validates the supported `five_hour` and `seven_day` `rate_limits`, and stores only normalized quota facts plus safe session/observation metadata.
- The provider home is an environment hint from the native Claude process and must be validated by reading its auth identity; the identity resolves the owning Agentos account. ^c20260811-62u
- Complete statusLine context—including workspace, cost, model, and path data—is never persisted in the usage registry.

### Callback.Throttle

- Throttling belongs inside the Claude callback; the provider script always submits the complete context.
- A changed quota/reset snapshot is appended immediately.
- An unchanged snapshot is appended only when the previous account observation is at least 60 seconds old, keeping monitor data fresh without recording every status-line render.

### Monitor.Registry.First

- The hook observation is account-scoped even when its observing Claude home differs from the monitor's managed home.
- Limits tracking considers the new Claude hook source beside its existing exact-home statusline probe source, selects the newest compatible observation, and retains the existing freshness/reset validation and provider fallback.

## Impl.Agendix

- **Touched:** `Agentos.Hook` and `Agentos.Hook.Invocation`; exact-name sequential dispatch and opaque provider context. ^c20260811-5u ^c20260811-13u
- **Touched:** `Agent.Hook`; provider integrations map native callbacks onto the nearest Agentos semantic. ^c20260811-22u
- **Touched:** `Normalization.Pipeline::Account.Usage.Model`; Claude statusline JSON is a native usage artifact normalized into `Usage.Limit`s.
- **Touched:** `Account.Management`; account identity, not a home alias, binds the observation to an Agentos account.
- **Execution gate:** implement the accepted semantic and callback-side regulation. ^c20260813-26u

## Execution.Plan

### Vertical.Slice 1 — Claude hook consumer

- **Status:** pending.
- **RED:** provider tests assert valid Claude statusLine context writes one safe account-scoped usage record, unrelated context types no-op, and invalid/unregistered homes fail through ordinary hook isolation.
- **GREEN:** add the Claude provider registrar, quota normalization, credential-identity account resolution, and 60-second changed-value-aware throttling.
- **Check:** `uv run pytest tests/test_claude_usage_hooks.py`.

### Vertical.Slice 2 — Registry-first monitor integration

- **Status:** pending.
- **RED:** monitor tests assert a fresh Claude hook observation bypasses provider resolution even when observing and target homes differ.
- **GREEN:** add the hook source to account-scoped candidate selection and reuse the existing Claude statusline parser.
- **Check:** focused monitor limits-tracking tests.

### Vertical.Slice 3 — Runtime and native Claude mapping

- **Status:** pending.
- **RED:** runtime composition test asserts the new exact hook has an inline consumer.
- **GREEN:** compose the registrar, replace the obsolete Claude statusline `usage-report` call with `agentos hook`, and remove shell tracing from the configured statusLine command.
- **Check:** installed CLI smoke invocation with a minimized fixture and local settings JSON validation.

### Vertical.Slice 4 — Documentation and verification

- **Status:** pending.
- Update `AGENTS.md` logging/hook documentation and this artifact.
- Run focused suites, relevant hook/account tests, Ruff, formatting checks, and `git diff --check`.

## Acceptance.Signals

- Claude statusLine invokes `agent.statusline.context` with the complete native JSON object.
- The callback writes only recognized quota facts and safe observation metadata.
- Identical observations produce at most one registry row per 60 seconds; changed quota/reset values write immediately.
- A fresh Claude hook record prevents the monitor from spawning a Claude usage probe.
- Existing Codex hooks, Claude live probing, and registry fallback remain intact.

## Deviation.Triggers

- Stop if accurate Claude quota fields are absent from observed statusLine context.
- Stop if account resolution requires a provider network request.
- Do not persist raw context or move throttling into the provider shell script.

## Impl.Log

- **Design evidence:** observed local Claude statusLine samples carry `session_id`, `transcript_path`, and `rate_limits.{five_hour,seven_day}.{used_percentage,resets_at}`; Claude Stop context and transcript do not carry account quota snapshots.
- **Existing-path finding:** `~/.claude/statusline` still calls the removed `agentos agent accounts usage-report` command, so live statusLine ingestion is currently ineffective.
- **Execution authorization:** autonomous implementation is authorized by ^c20260813-26u.
