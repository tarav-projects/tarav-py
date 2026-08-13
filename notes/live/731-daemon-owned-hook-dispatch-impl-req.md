# 731 — Daemon-owned hook dispatch

## Impl.Abstract

- **Scope:** make the Agentos daemon the universal execution owner for hook callbacks, submit every valid `agentos hook` invocation to it, and add `--wait` for callers that require dispatch completion.
- **Status:** approved for autonomous execution. ^c20260813-27u
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

- **Status:** pending.
- **RED:** registry tests reject execution-lane assumptions and assert one exact-name sequential callback list.
- **GREEN:** remove execution metadata and lane selection from callback registration and dispatch; update all subsystem registrars.
- **Check:** focused hook and consumer tests.

### Vertical.Slice 2 — Universal daemon submission

- **Status:** pending.
- **RED:** CLI tests assert valid known and unknown hooks are submitted once, no callback runs locally, default delivery failure is isolated, and `--wait` delivery failure becomes a CLI error.
- **GREEN:** make the hook command a validation/submission boundary and expose `--wait`.
- **Check:** `tests/test_hooks.py` and hook CLI end-to-end tests.

### Vertical.Slice 3 — Completion protocol

- **Status:** pending.
- **RED:** daemon tests prove default submission returns after acceptance while `wait=True` blocks until serial dispatch completes.
- **GREEN:** carry the wait request in the local protocol, queue an optional completion signal, and answer `completed` after worker dispatch.
- **Check:** `tests/test_daemon.py`.

### Vertical.Slice 4 — Composition and live verification

- **Status:** pending.
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
