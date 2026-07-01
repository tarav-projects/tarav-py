# 676 — wire `profile_check` into the run path as a pre-flight gate

## Impl.Abstract

- **Scope:** make `agentos agent run` **gate on fitness before spawning**. The CLI run
  consumer calls `agent.profile_check()` first; if the check is not `ok`, it prints the
  failing checkpoints and aborts with a non-zero exit instead of running. A `--force`
  flag overrides the gate (explicit user acknowledgment). This closes the long-standing
  "hollow pre-run hook" — `run` used to spawn without any reality check.
- **Authority principle (the design's spine):** the run consumer **does not
  re-interpret** what counts as an error. `agent.profile_check()` owns the verdict — if
  it reports a failed checkpoint, the run blocks. No per-status logic (e.g. "is
  `drift:home-newer` really bad?") lives in the gate; any such refinement belongs
  **inside `profile_check`**, never here.
- **Placement (the key decision):** the gate lives in the **CLI consumer**
  (`_cmd_agent_run`), not inside `RunnableMixin.run()`. `run()` is the pure primitive and
  is also reached by `ping` / monitor auto-prime (`agent.ping → self.run`); gating inside
  it would wrongly block a prime-ping (which must run even when drifted). Policy is a
  consumer concern — matches the accepted design ("`profile_check` is pure diagnosis;
  whether run blocks is a consumer-side policy decision").
- **Source context:** builds directly on 675 (`agent.profile_check()` capability). Design
  model: `Agent.Normal.Model` (agentos-md `104-index.md` + appendix).
- **Status:** COMPLETE.
- **Out of scope (do NOT touch):**
  - **Gating inside `agent.run()`** — would gate ping/prime; the primitive stays pure.
  - **The monitor auto-prime path** (`_run_account_prime_ping`) — it must run unconditionally; no gate.
  - **Refining which checkpoints block** (the `drift:home-newer`-is-runnable nuance) —
    that is `profile_check`'s job, recorded as `Feedback.To.Design` below, not this Req.
  - **`--dry-run`** — it never spawns; it stays a command preview, no gate.
  - **`profile_check` internals / checkpoints** — unchanged; this Req only consumes it.

## Impl.Index

### Block A: the run consumer today (`Hard.Evidence`)
- `_cmd_agent_run` (`commands.py`): resolves `(agent, command_config, run_config)`; if
  `args.dry_run` prints the dry preview and returns 0; otherwise `result =
  agent.run(command_config, run_config); return result.exit_code`. No fitness check.
- `agent.profile_check() -> ProfileCheck` (675) returns `checkpoints:
  tuple[CheckpointResult, ...]` and `ok: bool` (true iff all passed). Every resolved
  runnable agent has it (`ProfileCheckCapable` on `RunnableMixin`).
- `_cmd_agent_profile_check` already renders per-checkpoint lines (`  [ok|FAIL] <id> —
  <reason>`). The gate must print the **same** shape — extract a shared renderer so the
  standalone command and the gate produce identical output.

### Block B: the gate
- Insert **after** the `--dry-run` early return and **before** `agent.run(...)`:
  call `agent.profile_check()`; when `not result.ok`, render the failing checkpoints and
  raise `CliError` (the CLI error channel → non-zero exit) with a message that names the
  failure and points at `--force`. When `ok`, proceed to `agent.run` unchanged.
- `--force` is a new flag on the **run** subparser only (not ping / profile-check). When
  set, skip the gate entirely (optionally print a one-line "pre-flight skipped" notice)
  and run. It is a user override, not a re-interpretation of the verdict.
- Shared rendering: extract the per-checkpoint line formatting used by
  `_cmd_agent_profile_check` into one helper (in `commands.py` or `profile_check.py`);
  both call sites use it. `No.Legacy.Allowed` — no duplicated formatting.

## Execution.Plan

Two vertical slices, test-first, both at the CLI boundary. First observable endpoint =
Slice 1 (a run is blocked when unfit). `No.Regression`: reuse `profile_check`; add tests
only at the new gate behaviors.

### Slice 1 — the pre-flight gate (block vs proceed)
- Changes: extract the shared checkpoint renderer; in `_cmd_agent_run`, after the
  dry-run branch, call `agent.profile_check()` and abort via `CliError` (rendering the
  failing checkpoints) when `not ok`; proceed when `ok`. Point the error message at
  `--force`.
- Path: `agentos agent run …` → resolve → `agent.profile_check()` → (abort | `agent.run`).
- Observable result: an unfit agent (`profile_check().ok is False`) makes `run` print the
  failing checkpoints and exit non-zero **without calling `agent.run`**; a fit agent runs
  as before and returns the child exit code.
- Check (RED→GREEN): new `tests/test_agent_run_preflight.py` — monkeypatch
  `_resolve_agent_run` (or the resolved agent) so `agent.profile_check()` returns a
  failing `ProfileCheck` and `agent.run` records if called: assert non-zero/`CliError`,
  the failing checkpoint text is printed, and `agent.run` was **not** called. Second
  case: `ok` check → `agent.run` **is** called and its exit code is returned. RED before
  the gate exists (run is called unconditionally today).

### Slice 2 — `--force` bypass
- Changes: add `--force` to the run subparser; when set, skip the gate and run.
- Path: `agentos agent run --force …` with an unfit agent → skips the check → `agent.run`.
- Observable result: `--force` on an unfit agent calls `agent.run` (gate bypassed);
  without `--force` the same agent is blocked (Slice 1).
- Check (RED→GREEN): extend the preflight test — `--force` + failing check → `agent.run`
  called and `profile_check` either not consulted or its failure ignored. RED before the
  flag/bypass exists.

### Risks / deviation triggers
- **`run()` reached by ping/prime:** confirm the gate is only in `_cmd_agent_run`; do not
  touch `RunnableMixin.run`, `agent.ping`, or `_run_account_prime_ping`. If a design urge
  appears to gate the primitive, stop — that is out of scope and wrong for prime.
- **Renderer extraction:** keep the printed shape byte-identical to today's
  `_cmd_agent_profile_check` output; if a test pins that output, it is the contract.
- **Error channel:** a blocked run must surface as a clean non-zero exit (via `CliError`),
  not a traceback.
- **Scope guard:** no changes to `profile_check` checkpoints, the monitor, or dry-run.

### Acceptance signals
- Full suite green (`uv run pytest`), lint clean (`uv run ruff check src/ tests/`).
- `agentos agent run` on an unfit profile prints the failing checkpoints and exits
  non-zero without spawning; `--force` runs anyway; a fit profile runs unchanged.
- The per-checkpoint rendering exists once and is shared by the standalone
  `profile-check` command and the run gate.
- `agent.run`, `agent.ping`, and monitor auto-prime behavior unchanged.

## Feedback.To.Design

- **Runnable vs aligned:** `profile_check`'s `home_aligned` checkpoint currently fails on
  *every* non-aligned status, including `drift:home-newer` — a home whose credential is
  **fresher** than the registry, which would actually run fine. Under the authority
  principle the gate must not special-case this; the correct home is **inside
  `profile_check`**: a later refinement may let `home_aligned` pass `drift:home-newer`
  (home ahead) while still failing `drift:home-older` / `undeterminable` /
  `error:unlisted-account`. Tracked as a follow-up to 675, not actioned here.

## Impl.Log

- Both slices done test-first (RED→GREEN). Suite 240→243 (+3 preflight tests: block,
  proceed, force-bypass), lint clean. **No deviations** — the plan fit reality.
- Gate lives only in `_cmd_agent_run` (after the dry-run branch, guarded by `not
  args.force`); `RunnableMixin.run`, `agent.ping`, and the monitor prime are untouched —
  verified: `agent.profile_check()` is called only from `commands.py`.
- Renderer extracted to `_render_profile_checkpoints`, shared by the standalone
  `profile-check` command and the gate (identical per-checkpoint output).
- **Still open (Feedback.To.Design, not this Req):** the runnable-vs-aligned refinement
  — `profile_check`'s `home_aligned` should later pass `drift:home-newer` (home ahead is
  runnable). It lives inside `profile_check`, per the authority principle; the gate needs
  no change when that lands.
