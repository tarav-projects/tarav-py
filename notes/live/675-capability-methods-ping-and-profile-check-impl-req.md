# 675 — capabilities as methods: `agent.ping()` + `agent.profile_check()`

## Impl.Abstract

- **Scope:** make the `Agent.Normal.Model` interface uniform — **capabilities are
  methods on the agent** (`agent.<capability>()`), with any `_helper(agent)` function
  an internal detail, never the surface. Two coupled pieces:
  1. **Reconcile `ping`** — it currently ships as a free function `ping_agent(agent)`
     that the CLI and monitor call directly (`agent/ping.py`, added in 674). Promote it
     to `agent.ping()`; the free function becomes an internal helper.
  2. **Build `agent.profile_check()`** — the read-only pre-run fitness gate that has no
     implementation today (the design's once-"evaluate" capability). It answers "is this
     fully-specified instance fit to run *right now*?" via canonical checkpoints, without
     spawning or writing.
- **Design source:** this session's `Agent.Normal.Model` work in `agentos-md`
  (`104-index.md` `Agent.Normal.Model` + `appendix/Agent.Normal.Model-appendix.md`).
  Canonical run-time capabilities: `run / ping / profile_check / account_status`. The
  interface principle (capability = method) is the user's explicit direction.
- **Key grounding (simplifies the plan):** `account_status_report.status_for_home()`
  (`account_status_report.py:51`) is **already** the clean, read-only per-home alignment
  evaluator — it reads the home, resolves the account by identity, and returns
  `aligned | drift:* | undeterminable | error:unlisted-account`. So `home_alignment`
  needs **no extraction** — `profile_check` reuses `status_for_home` directly. This
  revises the earlier "extract home_alignment from build_status_report" idea: the
  function is already separable (`build_status_report` just maps it over all homes).
- **Status:** READY.
- **Out of scope (do NOT touch):**
  - **The structural refactor** — splitting `primitives.py`, grouping `agent/account/`
    vs run-time modules, renaming `agent/providers.py`. Explicitly deferred to a separate
    pass after the capability set is final.
  - **Account-lifecycle primitives** (capture/activate/materialize/rotate) and the
    registry — untouched.
  - **The checkpoint registry / provider-pluggable checkpoints** — premature; use a
    fixed checkpoint list (see Block C).
  - **Broadening capabilities to non-runnable adapters** (e.g. copilot, which has no
    `run`) — `ping`/`profile_check` land on the run-capable surface only.

## Impl.Index

### Block A: capabilities are methods (`Hard.Evidence`)
- `run` and `account_status` are already methods: `RunnableMixin.run`
  (`primitives.py:234`) behind `RunCapable` (`primitives.py:333`); `account_status` a
  per-provider method behind `AccountStatusCapable` (`primitives.py:344`).
- `ping` is the outlier: `ping_agent(agent, *, cwd, model, account) -> AgentPingResult`
  (`agent/ping.py`), called directly by `commands._cmd_agent_ping` and
  `monitor/workflows._run_account_prime_ping`. No `.ping()` method, no `PingCapable`.
- Target: a `ping()` method on `RunnableMixin` (ping composes `self.run` + validation,
  so it belongs with run-capable adapters) behind a new `PingCapable` protocol; the
  module keeps an internal helper, the consumers call `agent.ping(...)`.

### Block B: `profile_check` placement and shape
- `profile_check()` is a read-only fitness gate over a resolved agent
  (`self.provider` / `self.home` / `self.account`). It is provider-agnostic at the
  orchestration level — every checkpoint it needs is a module function, not a
  per-provider method — so it lands on `RunnableMixin` behind a `ProfileCheckCapable`
  protocol, mirroring `ping`.
- Result types live in a new module `agent/profile_check.py` (sibling to `ping.py`):
  `CheckpointResult` (id, passed, reason), `ProfileCheck` (checkpoints, ok). `ok` is
  true iff every checkpoint passed. **Collect-all** — never short-circuit; a fitness
  report shows every failing checkpoint at once.
- The method delegates to an internal `_profile_check(agent) -> ProfileCheck`; the
  method is the surface, the function is the helper (the capability-method principle).

### Block C: the checkpoints (fixed list, all reuse)
- `account_registered` — `auth_registry.account_exists(provider, account)` (exists). A
  `None` account is itself a fail ("no account bound").
- `home_exists` — the home path is a directory on disk (trivial new stat). A `None` home
  is a fail.
- `home_aligned` — build a `HomeTarget(home, provider, candidates={"<account>/*"})` and
  call `status_for_home` (`account_status_report.py:51`); map its status:
  `aligned` → pass; `drift:*` / `undeterminable` / `error:unlisted-account` → fail,
  carrying `status_for_home`'s own `reason` string. This single checkpoint already
  covers home-readable + account-identity-match + alignment.
- The resolve-time **legality** checks (`validate_account_override`,
  `select_allowed_home` in `profile_scope.py`) are **not** checkpoints — they run at
  resolution, the design separates legality (span) from fitness (reality).

### Block D: the CLI consumer
- New subcommand `agentos agent profile-check` (flat, mirrors `agent ping`/`agent run`,
  reusing the run-target args `--profile`/`--account`/`--home`/`--cwd`). Thin handler:
  resolve the agent (`_resolve_agent_run_target`), call `agent.profile_check()`, print
  one line per checkpoint, and **exit non-zero on any failure** (scriptable pre-flight).

## Execution.Plan

Four vertical slices, test-first. Slice 1 (ping) is independent and establishes the
capability-method pattern; slices 2–4 build `profile_check` on top. `No.Regression`:
reuse existing reads, add behavior tests only at the new boundaries.

### Slice 1 — `agent.ping()` method (ping reconciliation)
- Changes: add `PingCapable` protocol (`primitives.py`); add `ping()` to `RunnableMixin`
  delegating to the `ping.py` helper (rename `ping_agent` to an internal helper or keep
  it module-private); switch `commands._cmd_agent_ping` and
  `monitor/workflows._run_account_prime_ping` to call `agent.ping(...)`.
- Path: `agentos agent ping` and the monitor prime tick → `agent.ping()`.
- Observable result: `agent.ping()` returns an `AgentPingResult`; CLI `pong …` line and
  monitor prime behavior unchanged; nothing calls `ping_agent` from outside `ping.py`.
- Check (RED→GREEN): new test asserts `agent.ping()` on a stub runnable agent returns the
  expected `AgentPingResult`; update `tests/test_agent_ping.py` to drive the method;
  `tests/test_agent_profiles.py` (CLI pong) and `tests/test_agent_monitor_auto_prime.py`
  stay green.

### Slice 2 — result types + checkpoints (`_profile_check`)
- Changes: new `agent/profile_check.py` with `CheckpointResult`, `ProfileCheck`, the
  three checkpoint helpers (Block C), and `_profile_check(agent) -> ProfileCheck`
  (collect-all).
- Path: a resolved agent → `_profile_check` → `ProfileCheck`.
- Observable result: an aligned home with a registered account yields `ok=True`, all
  checkpoints passed; a missing/unregistered account or a drifted/undeterminable home
  yields `ok=False` with the failing checkpoints carrying reasons.
- Check (RED→GREEN): new `tests/test_agent_profile_check.py` — aligned→ok; unregistered
  account→fail on `account_registered`; missing home→fail on `home_exists`;
  drift→fail on `home_aligned` with the drift reason. Use registry/home fixtures as the
  existing account tests do (e.g. `tests/test_agent_accounts_status*`), no provider call.

### Slice 3 — `agent.profile_check()` method
- Changes: add `ProfileCheckCapable` protocol (`primitives.py`); add `profile_check()`
  to `RunnableMixin` delegating to `_profile_check(self)`.
- Path: `agent.profile_check()` → `_profile_check`.
- Observable result: `agent.profile_check()` returns the same `ProfileCheck` the helper
  produces.
- Check (RED→GREEN): test `agent.profile_check()` on a resolved fixture agent returns a
  `ProfileCheck`; isinstance against `ProfileCheckCapable` holds.

### Slice 4 — CLI `agentos agent profile-check`
- Changes: register the `profile-check` subparser (run-target args); thin handler
  resolves the agent and calls `agent.profile_check()`; print per-checkpoint; return
  non-zero on any failure.
- Path: `agentos agent profile-check --profile … [--account|--home]` → resolve →
  `agent.profile_check()` → printed report + exit code.
- Observable result: a fit agent prints all-pass and exits 0; an unfit agent prints the
  failing checkpoints and exits non-zero.
- Check (RED→GREEN): CLI test drives the handler against a fixture agent — assert the
  printed checkpoint lines and the exit code for a pass and a fail case.

### Risks / deviation triggers
- **`status_for_home` shape:** it returns a dict keyed `status`/`reason`/`account`/
  `method`. If mapping its statuses to a single `home_aligned` checkpoint loses needed
  detail, split into more checkpoints — but do not reimplement the alignment read; reuse
  `status_for_home`.
- **`ping` method home:** `ping` needs `self.run`, so it must sit on `RunnableMixin`, not
  `AgentConfig`. If a non-runnable adapter is ever asked to ping, that's correctly a
  no-capability (the method simply isn't there).
- **`cwd` for `ping()`:** the method takes `cwd` (default to `Path.cwd().resolve()` when
  omitted) so the CLI can pass its resolved cwd and the monitor can omit it — preserve
  both existing call behaviors.
- **Scope guard (hard boundary):** no structural refactor, no account-lifecycle changes,
  no checkpoint registry. A change that reshapes those aborts the slice.

### Acceptance signals
- Full suite green (`uv run pytest`), lint clean (`uv run ruff check src/ tests/`).
- `agent.ping()` and `agent.profile_check()` exist as methods behind `PingCapable` /
  `ProfileCheckCapable`; no caller invokes `ping_agent` or `_profile_check` from outside
  their modules.
- `agentos agent profile-check` reports per-checkpoint and exits non-zero on any failure.
- `agentos agent ping` output and monitor auto-prime behavior unchanged.

## Impl.Log

- (pending execution)
