# 720 — daemon hook dispatch and Chatlas refresh POC

## Impl.Abstract

- **Scope:** add a provider-neutral Agentos daemon POC with a Unix-socket acceptance boundary, explicit inline/daemon hook callback lanes, a control namespace spanning foreground, manual detached, and macOS login-managed launch, persistent secret-free operational logging, and a Chatlas-owned deferred `agent.turn.stop` session refresh consumer.
- **Status:** login-start extension implemented and verified.
- **Source:** autonomous `$agentos-hugentics --impl --dev --AUTO` execution gate. ^c20260811-50u
- **Out of scope:** scheduler frequencies, durable inbox/retry delivery, exactly-once guarantees, non-macOS service managers, system-wide service installation, arbitrary remote commands, wildcard hook subscriptions, cross-lane completion ordering, and automatic semantic `Chat.Index.Delta` capture.

## Impl.Index

### Hook.Execution.Lanes

- `HookRegistry` remains the one exact-name callback registry, but each registration declares `inline` or `daemon` execution; existing registrations default to `inline`.
- The hook CLI validates one `HookInvocation`, runs inline callbacks sequentially, then submits the same opaque invocation once when daemon callbacks exist. It waits only for a local acceptance acknowledgement.
- Daemon callback completion is intentionally outside the harness thread. Sequential registration order applies within each execution lane; no completion ordering is promised across lanes.

### Daemon.Acceptance.And.Work

- The daemon is one local process reached through a permission-restricted Unix socket under the Agentos home. Socket requests are a closed protocol for ping, stop, and validated hook submission; they cannot name arbitrary shell commands.
- Socket handlers accept and acknowledge quickly. One in-memory worker queue dispatches daemon callbacks serially through the shared registry.
- Accepted work is best-effort process memory. If delivery fails, the hook records a persistent operational event and returns successfully; there is no inline fallback, retry, or durable spool in this POC.
- `agentos daemon run|start|status|stop` is the initial control namespace. `run` is the foreground process entrypoint intended for later OS-service-manager ownership; `start` launches that same entrypoint as a detached child and returns only after observing daemon readiness.
- `start` is idempotent while the daemon is already running. It is a manual convenience launcher, not keep-alive, restart-on-crash, or start-at-login lifecycle management.

### Daemon.Launchd.Lifecycle

- `agentos daemon install` writes one user LaunchAgent at `~/Library/LaunchAgents/org.agentos.daemon.plist`, bootstraps it into the current GUI domain, and verifies socket readiness. `uninstall` cleanly stops and unloads it before removing the owned plist.
- The LaunchAgent runs the same absolute `agentos daemon run` entrypoint. `RunAtLoad` supplies login startup; `KeepAlive.SuccessfulExit=false` restarts abnormal exits without respawning a clean `daemon stop`.
- Install and uninstall are idempotent. Existing unrelated files are never overwritten, and command status reports installed/loaded service state separately from socket/process availability.
- When the LaunchAgent is installed, `daemon start` asks launchd to start the loaded job; the direct detached-child path remains only for an uninstalled service.

### Daemon.Operational.Log

- Daemon lifecycle, acceptance, delivery failure, dispatch completion, and consumer failure use a private daily JSONL log under `~/.agentos/daemon/`.
- Records carry event id, hook name, context type, callback identity, stage, and exception type when applicable. Complete hook context and exception text are excluded.

### Chatlas.Deferred.Consumer

- `agentos-chatlas-py` owns a daemon callback on `agent.turn.stop`; `agentos-cli` composes it into the shared registry.
- For supported Chatlas providers, the callback validates `ctx.session_id`, uses `ctx_type` as the provider family, uses a valid `ctx.cwd` only as discovery start-path context, and calls the existing targeted `Chatlas.Update.Pipeline` with one-session `Scan.Scope`.
- After refresh, the callback materializes the selected normalized session model so transcript consumers receive a warm cache.
- Repeated unchanged events remain cheap through existing Chatlas signatures and caches. Chatlas semantic Index capture is not part of refresh.

## Impl.Agendix

- **Touched:** `Agentos.Hook`, `Agentos.Hook.Invocation`, and `Agent.Hook` in `agentos-pkg/design/113-design.md`: exact-name registration, opaque context, sequential failure-isolated dispatch, and `agent.turn.stop` semantics.
- **Touched:** `Agentos.Daemon`, `Background.Job`, and `Daemon.Trigger` in `agentos-pkg/design/104-design.md`: one local OS-managed process, registered work only, one serialized work lane, shared core-library work bodies, and no inline daemon fallback.
- **Touched:** `Chatlas.Update.Pipeline`, `Scan.Scope`, and `Delta.Normalization::Chatlas` in `agentos-chatlas-pkg/design/100-design.md`: targeted refresh is the ordinary pipeline at one-session scope and remains incremental.
- **Current design deviation:** the existing daemon block says serialization needs no queue; non-blocking hook acceptance requires one bounded implementation separation between socket acceptance and the serial worker. This POC uses only an in-memory queue and records the design mismatch for later Index reconciliation.
- **Execution gate:** implement the daemon and deferred Chatlas turn-stop POC. ^c20260811-50u
- **Extension gate:** add a non-terminal-occupying `agentos daemon start` command. ^c20260811-51u
- **Login-start gate:** install the daemon to start automatically at user login. ^c20260811-52u

## Execution.Plan

### Vertical.Slice 1 — Explicit hook execution lanes

- **Status:** complete.
- **RED:** prove daemon callbacks do not run in inline dispatch and that one validated hook command submits only when the selected hook has daemon consumers.
- **GREEN:** add explicit callback execution metadata, lane-filtered dispatch, daemon-callback discovery, and injectable hook submission while preserving existing default-inline behavior.
- **Check:** hook model/registry/command tests and existing hook consumer tests.

### Vertical.Slice 2 — Daemon acceptance and serial worker

- **Status:** complete.
- **RED:** prove a hook submission receives acceptance while its daemon callback remains blocked, and prove multiple deferred callbacks execute serially in registration order.
- **GREEN:** add the private Unix-socket protocol, quick acknowledgement, one in-memory worker lane, run/status/stop commands, secure paths, lifecycle cleanup, and secret-free operational JSONL logging.
- **Check:** daemon client/runtime/command tests, including unavailable-daemon logging and consumer failure isolation.

### Vertical.Slice 3 — Deferred Chatlas session refresh

- **Status:** complete.
- **RED:** dispatch a daemon-lane Codex `agent.turn.stop` invocation and assert the existing targeted Chatlas update receives provider, session id, and discovery start path; irrelevant providers remain no-ops.
- **GREEN:** add the Chatlas hook registrar and compose it in `agentos-cli` after provider callbacks.
- **Check:** Chatlas callback tests plus CLI composition tests.

### Vertical.Slice 4 — Installed CLI and live POC

- **Status:** complete.
- **Change:** update repository guidance, refresh the editable umbrella CLI, verify daemon help/status/control, and exercise hook acceptance plus Chatlas processing against a bounded session fixture or current session without exposing raw context.
- **Check:** full relevant suites, Ruff, format, `git diff --check`, and one end-to-end daemon/hook smoke.

### Vertical.Slice 5 — Detached manual start

- **Status:** complete.
- **RED:** prove `daemon start` returns after readiness, reports the child PID, is idempotent when already running, and fails clearly when the detached child never becomes available.
- **GREEN:** launch the installed `agentos daemon run` entrypoint with a new session and redirected standard streams, poll the existing status protocol for bounded readiness, and terminate a failed child without introducing another runtime implementation.
- **Check:** daemon command tests, installed `start/status/stop` smoke, guidance refresh, Ruff, format, and `git diff --check`.

### Vertical.Slice 6 — LaunchAgent ownership

- **Status:** complete.
- **RED:** prove the generated plist names the absolute Agentos entrypoint, starts at login, restarts only abnormal exits, and that install/uninstall are idempotent over an isolated LaunchAgents root.
- **GREEN:** add the macOS LaunchAgent model, atomic owned-plist persistence, GUI-domain bootstrap/bootout/kickstart operations, and structured service status without duplicating daemon runtime logic.
- **Check:** isolated launchd model/command tests, focused Ruff/format, and existing daemon tests.

### Vertical.Slice 7 — Installed login lifecycle

- **Status:** complete.
- **RED:** prove command composition exposes install/uninstall and that installed-service `start` uses launchd rather than direct child daemonization.
- **GREEN:** integrate install/start/status/stop/uninstall behavior, update guidance, install the real user LaunchAgent, and verify loaded/running state plus clean stop/start behavior.
- **Check:** full foundation and CLI suites, `git diff --check`, `launchctl print`, plist inspection, and live lifecycle smoke.

## Impl.Log

- **Decision:** v1 daemon delivery is best-effort and non-blocking. Failure is persistently logged and the harness-facing hook command still succeeds.
- **Decision:** the protocol carries registered hook events, never arbitrary commands.
- **Decision:** foreground `daemon run` establishes the runtime boundary now; launchd installation and scheduled `Background.Job`s remain follow-ups.
- **Execution authorization:** autonomous implementation is authorized by ^c20260811-50u.
- **Implemented:** the shared registry now has explicit `inline` and `daemon` lanes; hook ingress submits exactly once only when its exact name has a deferred consumer.
- **Implemented:** the closed local protocol, permission-restricted Unix socket, acceptance-only client, one serial in-memory worker, `daemon run|status|stop`, lifecycle cleanup, and secret-free daily operational log.
- **Implemented:** Chatlas owns a deferred `agent.turn.stop` callback that performs a targeted provider/session refresh and warms the normalized session-model cache; the umbrella CLI composes it into the same registry used by daemon dispatch.
- **Verification:** Agentos foundation `963 passed`, Chatlas `483 passed`, and umbrella CLI `76 passed`; touched-file Ruff and format checks plus all three `git diff --check` checks passed. Repository-wide Ruff/format checks still encounter unrelated pre-existing deprecated/dev lint and baseline-format findings outside the touched surfaces.
- **Live POC:** the installed editable CLI started PID `68580`, acknowledged the current Codex turn-stop hook in `0.37s`, recorded acceptance and completed dispatch for event `66a6bf2c784341ad8a4e07a5f6380aee`, refreshed Chatlas identity `b5708598628d83645af832f4e8628ab85211d15acd0d10d1419a0b118a1bfd4a`, warmed its model, and stopped cleanly.
- **Extension decision:** without an installed service, `start` remains a bounded manual detached launcher; installed services supersede that path with launchd ownership. ^c20260811-51u
- **Extension implemented:** `daemon start` reuses the installed `agentos daemon run` entrypoint, detaches standard streams and the process session, waits for bounded socket readiness, returns the observed PID, and reports an already-running daemon without spawning another process.
- **Extension verification:** Agentos foundation `967 passed` and umbrella CLI `76 passed`; focused Ruff, format, and diff checks passed. The installed CLI started detached PID `1977`, reported the same PID through status and an idempotent second start, then stopped cleanly.
- **Login-start decision:** use a per-user LaunchAgent with `RunAtLoad=true` and restart only after unsuccessful exit so launchd owns login/crash lifecycle while `daemon stop` remains a durable clean stop. ^c20260811-52u
- **Login-start implemented:** `daemon install|uninstall` manage one ownership-validated user LaunchAgent; status exposes installed/loaded state, and `start` delegates to launchd whenever the plist is installed.
- **Login-start verification:** Agentos foundation `973 passed` and umbrella CLI `76 passed`; the real `org.agentos.daemon` LaunchAgent loaded from the expected plist, clean stop remained stopped, explicit start returned through launchd, and forced abnormal exit of PID `39852` recovered as PID `40531`.
