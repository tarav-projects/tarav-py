# 731 — Daemon-owned hook dispatch

## Impl.Abstract

- **Scope:** make the Agentos daemon the universal execution owner for hook callbacks, submit every valid `agentos hook` invocation to it, and add `--wait` for callers that require dispatch completion.
- **Status:** implemented and verified. ^c20260813-27u
- **Out of scope:** durable delivery, inline fallback, callback concurrency, callback result aggregation, protocol authentication beyond the private Unix socket, or CLI startup optimization.

## Impl.Index

### Daemon.Ownership

- The hook CLI is an ingress client: it validates and isolates one `Agentos.Hook.Invocation`, submits it to `Agentos.Daemon`, and never executes subsystem callbacks in its own process. ^c20260811-12u ^c20260725-115u
- Every valid hook name is submitted, including names with no callbacks in the CLI process; callback discovery and sequential dispatch belong to the daemon's composed runtime.
- The registry has one callback class. The former `inline` and `daemon` lanes are retired.

### Acceptance.Default

- Without `--wait`, success means the daemon accepted the invocation into its in-memory serial queue; the CLI returns without waiting for consumers.
- If submission fails, the default command records the existing secret-free delivery failure and returns successfully. There is no inline retry or durable inbox. ^c20260725-175u

### Completion.Wait

- `agentos hook --wait` keeps the local socket request open until the daemon has dispatched every registered callback for that invocation.
- `--wait` changes observation, not execution ownership: callbacks still run only in the daemon and in registration order.
- If the daemon is unavailable or the completion connection fails, the waiting command fails clearly.
- Isolated callback failures retain current semantics: they are logged, remaining callbacks run, and completed dispatch satisfies the wait. ^c20260811-6u ^c20260811-7u ^c20260811-8u

## Execution.Plan

### Vertical.Slice 1 — One registry lane

- **Status:** complete.
- **RED:** registry tests reject execution-lane assumptions and assert one exact-name sequential callback list.
- **GREEN:** remove execution metadata and lane selection from callback registration and dispatch; update all subsystem registrars.
- **Check:** focused hook and consumer tests.

### Vertical.Slice 2 — Universal daemon submission

- **Status:** complete.
- **RED:** CLI tests assert valid known and unknown hooks are submitted once, no callback runs locally, default delivery failure is isolated, and `--wait` delivery failure becomes a CLI error.
- **GREEN:** make the hook command a validation/submission boundary and expose `--wait`.
- **Check:** `tests/test_hooks.py` and hook CLI end-to-end tests.

### Vertical.Slice 3 — Completion protocol

- **Status:** complete.
- **RED:** daemon tests prove default submission returns after acceptance while `wait=True` blocks until serial dispatch completes.
- **GREEN:** carry the wait request in the local protocol, queue an optional completion signal, and answer `completed` after worker dispatch.
- **Check:** `tests/test_daemon.py`.

### Vertical.Slice 4 — Composition and live verification

- **Status:** complete.
- Update runtime composition and project guidance, run focused and full validation, reinstall the monolith, restart the login daemon, and smoke-test both acceptance and completion paths.

## Acceptance.Signals

- `agentos hook` never calls a subsystem callback in the CLI process.
- Every valid invocation is offered to the daemon exactly once.
- Default mode returns after daemon acceptance; `--wait` returns after dispatch completion.
- The daemon invokes callbacks sequentially and isolates/logs callback failures.
- Existing Chatlas, Codex quota, Claude statusLine, and development sampler consumers run through the same daemon path.
- Daemon unavailability never causes inline callback execution.

## Deviation.Triggers

- Stop if completion requires a second execution path or arbitrary remote callable transport.
- Stop if the daemon cannot keep accepting new connections while one client waits.
- Do not add persistence or callback-result semantics to solve completion signaling.

## Impl.Log

- **Execution authorization:** autonomous implementation is authorized by ^c20260813-27u.
- **Design basis:** `Agentos.Daemon` is already the sole background-work owner with one serialized lane, while `Agentos.Hook` already defines exact-name sequential failure-isolated dispatch. This change removes the accidental split execution model instead of adding another runtime.
- **Pre-change latency baseline:** the installed CLI was measured for 10 runs after two warm-ups while the daemon was running. `benchmark.noop` had a 0.4001-second median (0.3865–0.4096); a no-op `agent.statusline.context` had a 0.4411-second median (0.3899–0.6008). The same commands will be repeated after installation.
- **Checkpoint:** commit `b26c356` captured the completed Claude statusLine work and this approved implementation request before execution edits began.
- **GREEN:** the registry now has one callback lane; the CLI submits every valid invocation exactly once; the daemon owns exact-name sequential dispatch for every consumer; and `--wait` holds the request connection until that event completes without creating an inline fallback.
- **Failure behavior:** ordinary delivery failure remains secret-free, logged, dropped, and successful in default mode; waiting delivery failure is logged and returned as a CLI error. Callback failures remain isolated and do not prevent dispatch completion.
- **Verification:** 42 focused hook/daemon/provider/Chatlas tests pass; the complete 1,894-test monolith suite passes; Ruff, formatting, `git diff --check`, and strict project Skw checks pass with no POIs on changed code surfaces.
- **Live installation:** the working tree was installed, the launchd-owned daemon was force-restarted as PID 9819, a live `--wait` invocation completed, and operational logs show acceptance, dispatch start, and dispatch completion under the new process.
- **Post-change latency:** the identical 10-run benchmark produced a 0.2349-second median for `benchmark.noop` (0.2249–0.2481) and 0.2290 seconds for the no-op `agent.statusline.context` (0.2239–0.2890), approximately 41% and 48% below their pre-change medians. The architecture removes consumer latency from the default path; the measured CLI-startup improvement is beneficial but not a protocol guarantee.
- **Reconciliation POI:** the reviewed Agentos Index still says callbacks register during CLI composition. The implementation now composes the same registry for daemon execution while the CLI is submission-only; that index wording should be captured through its separate approval-gated workflow.
