# 720 — daemon hook dispatch and Chatlas refresh POC

## Impl.Abstract

- **Scope:** add a provider-neutral Agentos daemon POC with a Unix-socket acceptance boundary, explicit inline/daemon hook callback lanes, a small `agentos daemon` control namespace, persistent secret-free operational logging, and a Chatlas-owned deferred `agent.turn.stop` session refresh consumer.
- **Status:** ready for execution.
- **Source:** autonomous `$agentos-hugentics --impl --dev --AUTO` execution gate. ^c20260811-50u
- **Out of scope:** scheduler frequencies, durable inbox/retry delivery, exactly-once guarantees, launchd installation, arbitrary remote commands, wildcard hook subscriptions, cross-lane completion ordering, and automatic semantic `Chat.Index.Delta` capture.

## Impl.Index

### Hook.Execution.Lanes

- `HookRegistry` remains the one exact-name callback registry, but each registration declares `inline` or `daemon` execution; existing registrations default to `inline`.
- The hook CLI validates one `HookInvocation`, runs inline callbacks sequentially, then submits the same opaque invocation once when daemon callbacks exist. It waits only for a local acceptance acknowledgement.
- Daemon callback completion is intentionally outside the harness thread. Sequential registration order applies within each execution lane; no completion ordering is promised across lanes.

### Daemon.Acceptance.And.Work

- The daemon is one local process reached through a permission-restricted Unix socket under the Agentos home. Socket requests are a closed protocol for ping, stop, and validated hook submission; they cannot name arbitrary shell commands.
- Socket handlers accept and acknowledge quickly. One in-memory worker queue dispatches daemon callbacks serially through the shared registry.
- Accepted work is best-effort process memory. If delivery fails, the hook records a persistent operational event and returns successfully; there is no inline fallback, retry, or durable spool in this POC.
- `agentos daemon run|status|stop` is the initial control namespace. `run` is the foreground process entrypoint intended for later OS-service-manager ownership.

### Daemon.Operational.Log

- Daemon lifecycle, acceptance, delivery failure, dispatch completion, and consumer failure use a private daily JSONL log under `~/.agentos/daemon/`.
- Records carry event id, hook name, context type, callback identity, stage, and exception type when applicable. Complete hook context and exception text are excluded.

### Chatlas.Deferred.Consumer

- `agentos-chatlas-py` owns a daemon callback on `agent.turn.stop`; `agentos-cli` composes it into the shared registry.
- For supported Chatlas providers, the callback validates `ctx.session_id`, uses `ctx_type` as the provider family, uses a valid `ctx.cwd` only as discovery start-path context, and calls the existing targeted `Chatlas.Update.Pipeline` with one-session `Scan.Scope`.
- Repeated unchanged events remain cheap through existing Chatlas signatures and caches. Chatlas semantic Index capture is not part of refresh.

## Impl.Agendix

- **Touched:** `Agentos.Hook`, `Agentos.Hook.Invocation`, and `Agent.Hook` in `agentos-pkg/design/113-design.md`: exact-name registration, opaque context, sequential failure-isolated dispatch, and `agent.turn.stop` semantics.
- **Touched:** `Agentos.Daemon`, `Background.Job`, and `Daemon.Trigger` in `agentos-pkg/design/104-design.md`: one local OS-managed process, registered work only, one serialized work lane, shared core-library work bodies, and no inline daemon fallback.
- **Touched:** `Chatlas.Update.Pipeline`, `Scan.Scope`, and `Delta.Normalization::Chatlas` in `agentos-chatlas-pkg/design/100-design.md`: targeted refresh is the ordinary pipeline at one-session scope and remains incremental.
- **Current design deviation:** the existing daemon block says serialization needs no queue; non-blocking hook acceptance requires one bounded implementation separation between socket acceptance and the serial worker. This POC uses only an in-memory queue and records the design mismatch for later Index reconciliation.
- **Execution gate:** implement the daemon and deferred Chatlas turn-stop POC. ^c20260811-50u

## Execution.Plan

### Vertical.Slice 1 — Explicit hook execution lanes

- **Status:** pending.
- **RED:** prove daemon callbacks do not run in inline dispatch and that one validated hook command submits only when the selected hook has daemon consumers.
- **GREEN:** add explicit callback execution metadata, lane-filtered dispatch, daemon-callback discovery, and injectable hook submission while preserving existing default-inline behavior.
- **Check:** hook model/registry/command tests and existing hook consumer tests.

### Vertical.Slice 2 — Daemon acceptance and serial worker

- **Status:** pending.
- **RED:** prove a hook submission receives acceptance while its daemon callback remains blocked, and prove multiple deferred callbacks execute serially in registration order.
- **GREEN:** add the private Unix-socket protocol, quick acknowledgement, one in-memory worker lane, run/status/stop commands, secure paths, lifecycle cleanup, and secret-free operational JSONL logging.
- **Check:** daemon client/runtime/command tests, including unavailable-daemon logging and consumer failure isolation.

### Vertical.Slice 3 — Deferred Chatlas session refresh

- **Status:** pending.
- **RED:** dispatch a daemon-lane Codex `agent.turn.stop` invocation and assert the existing targeted Chatlas update receives provider, session id, and discovery start path; irrelevant providers remain no-ops.
- **GREEN:** add the Chatlas hook registrar and compose it in `agentos-cli` after provider callbacks.
- **Check:** Chatlas callback tests plus CLI composition tests.

### Vertical.Slice 4 — Installed CLI and live POC

- **Status:** pending.
- **Change:** update repository guidance, refresh the editable umbrella CLI, verify daemon help/status/control, and exercise hook acceptance plus Chatlas processing against a bounded session fixture or current session without exposing raw context.
- **Check:** full relevant suites, Ruff, format, `git diff --check`, and one end-to-end daemon/hook smoke.

## Impl.Log

- **Decision:** v1 daemon delivery is best-effort and non-blocking. Failure is persistently logged and the harness-facing hook command still succeeds.
- **Decision:** the protocol carries registered hook events, never arbitrary commands.
- **Decision:** foreground `daemon run` establishes the runtime boundary now; launchd installation and scheduled `Background.Job`s remain follow-ups.
- **Execution authorization:** autonomous implementation is authorized by ^c20260811-50u.
