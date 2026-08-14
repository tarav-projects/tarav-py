# 722 — Runtime composition and Chatlas turn-stop maintenance

## Impl.Abstract

- **Scope:** finish the Python monolith composition root and run the canonical targeted Chatlas update from the daemon-owned `agent.turn.stop` consumer.
- **Status:** corrected and verified; the semantic `Chat.Index` producer described by the original edition was rejected and retired on 2026-08-12.
- **Source:** persistent `$tarav-hugentics --impl --dev --AUTO` execution gate. ^c20260811-54u
- **Baseline:** the migrated monolith passes the complete 1,786-test parity suite, but its migration changes are not checkpointed; `agentos.cli` still owns subsystem wiring; the Chatlas hook only refreshes and warms the normalized session model.
- **Out of scope:** redesigning Chat.Index semantics, making semantic capture synchronous with the harness, adding durable daemon retry, or retiring the preserved `_DEPRECATED` repositories.

## Impl.Index

### Monolith.Checkpoint

- Review the unrelated `_linter_structure.py` wording change before checkpointing it with every current monolith migration change.
- The change is retained only if it accurately names the actual parser invariant and focused tests remain green.
- Commit the complete migration checkpoint before follow-up implementation edits. No second commit is made by this execution workflow.

### Runtime.Composition

- `agentos.runtime` owns the deterministic application composition for hooks and CLI command registrars, including every cross-subsystem dependency injection.
- `agentos.cli` owns only the executable adapter: parser shell, argument execution, help, version, and CLI error rendering.
- The daemon continues to create the same runtime in-process and never invokes the Agentos CLI.
- Command composition remains lazy enough that daemon-only startup does not eagerly import the full CLI surface.

### Chatlas.TurnStop

- `agent.turn.stop` refreshes exactly the provider/session named by the hook through `chatlas_update(...)`.
- The targeted daemon callback uses the same incremental append trust selected by `agentos chatlas update --session-id`.
- The callback does not resolve or produce a semantic `Chat.Index`, warm a second model, or spawn an agent.
- Failures remain daemon callback failures: they are logged and serial dispatch continues according to the existing hook/daemon semantics.

## Impl.Agendix

- **Touched:** `Agentos.Runtime`: becomes the single application composition root for both hook callbacks and CLI command integrations.
- **Touched:** `Agentos.Hook`: gains an explicit process-local suppression control solely to prevent internal maintenance agents from recursively submitting hooks.
- **Touched:** `Chat.Index.Capture`: its semantic boundary is preserved; CPU code owns evidence/envelope/validation/apply, while an agent owns Delta and HEAD meaning.
- **Touched:** `Agentos.Daemon`: remains the deferred serial executor; no durable inbox or retry policy is introduced.
- **Execution gate:** autonomous implementation and checkpoint commit are authorized by ^c20260811-54u.

## Execution.Plan

### Vertical.Slice 1 — Migration checkpoint

- **Status:** complete.
- Verify the linter wording against the parser invariant and focused tests.
- Cold-reread this requirement, stage every current `agentos-py` change, and commit the completed monolith migration.

### Vertical.Slice 2 — Runtime-owned command composition

- **Status:** complete.
- **RED:** prove the CLI adapter delegates registration to a runtime and no longer imports feature registrars or Chatlas integration callbacks.
- **GREEN:** move deterministic registrar order and subsystem injections into a lazy runtime method; keep CLI behavior and extension hooks compatible.
- **Check:** runtime, CLI, daemon, and command-surface tests.

### Vertical.Slice 3 — Targeted turn-stop update

- **Status:** corrected after live verification exposed the original semantic producer as an invalid extension of the update hook.
- **RED:** prove the daemon callback narrows the canonical update to the hook provider/session and selects append trust.
- **GREEN:** remove semantic capture, child-agent spawning, model warming, and the now-unused internal hook-suppression control.
- **Check:** focused Chatlas hook, hook ingress, and daemon tests.

### Vertical.Slice 4 — Verification and closure

- **Status:** complete.
- Run focused suites, the full monolith suite, Ruff on touched files, `git diff --check`, packaging build, installed entrypoint smokes, and live daemon lifecycle checks.
- Update this log with authoritative evidence and leave the post-checkpoint implementation changes uncommitted for review.

## Impl.Log

- **Decision:** a warmed session cache is not a Chat.Index Delta.
- **Decision:** a mechanical or empty Delta would violate Chat.Index's semantic extraction contract; deferred maintenance therefore requires a configured semantic agent producer.
- **Decision:** the existing Chatlas `run_produce` agent selection is the initial shared configuration surface for retained agent production.
- **Review:** `_linter_structure.py` checks for a parsed trailing anchor span, so `Index.Line.Anchor` is the precise invariant name; `Support.Reference` is the broader semantic relationship and was misleading in this diagnostic.
- **Checkpoint:** the complete Python monolith migration was committed as `597c6e5` before follow-up implementation edits.
- **Implemented:** `AgentosRuntime.register_commands()` now lazily owns every command registrar and cross-subsystem callback injection; `agentos.cli` retains only parser/execution/error adapter mechanics.
- **Implemented:** the daemon Chatlas turn-stop callback refreshes the exact provider session, resolves its neutral identity, and invokes an importable semantic Chat.Index producer using the shared `chatlas.run_produce` provider/profile/model selection.
- **Implemented:** the producer records the source horizon before launch, suppresses Agentos hooks in the internal child process, invokes `$tarav-chatlas-pkg --capture` through the configured agent, and accepts success only when an audited landed HEAD reaches that horizon.
- **Implemented:** already-current audited surfaces are idempotent no-ops; agent, configuration, horizon, and audit failures propagate to ordinary daemon callback logging without blocking later events.
- **Lifecycle repair:** daemon reinstall now uses `launchctl kickstart -k` when replacing a loaded service, closing the socket-disappearance/process-exit race discovered during installed verification. Its readiness timeout also exceeds the LaunchAgent throttle interval.
- **Verification:** the complete monolith suite passes 1,792 tests; all touched Python files pass Ruff; `git diff --check` passes; source and wheel builds pass.
- **Installed verification:** the editable monolith owns all four executables, imports resolve to `agentos-py/src/agentos`, the LaunchAgent targets the dedicated `agentos-daemon`, and `agentos daemon install` returned a live PID after the forced-restart repair.
- **Daemon verification:** an installed `agent.turn.stop` smoke event was accepted and dispatched serially by the live daemon; an unsupported `ctx_type` intentionally exercised transport without triggering provider-specific retained production.
- **Correction:** live stop events showed that the semantic producer blocked the serial daemon for minutes and failed without materializing a surface. The hook now runs only the canonical targeted `chatlas_update(...)`; the dedicated child-agent producer and its hook-suppression environment control were removed.
