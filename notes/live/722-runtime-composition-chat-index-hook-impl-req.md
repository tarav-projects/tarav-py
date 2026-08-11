# 722 — Runtime composition and Chat.Index turn-stop maintenance

## Impl.Abstract

- **Scope:** finish the Python monolith composition root and upgrade the daemon-owned `agent.turn.stop` Chatlas consumer from dataset refresh to semantic `Chat.Index` maintenance.
- **Status:** approved for autonomous development.
- **Source:** persistent `$agentos-hugentics --impl --dev --AUTO` execution gate. ^c20260811-54u
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

### Chat.Index.TurnStop

- `agent.turn.stop` first refreshes exactly the provider/session named by the hook and resolves its authoritative Chatlas identity.
- The daemon then maintains the real per-session `Chat.Index` through the existing semantic capture contract: scaffolded bounded evidence, agent-authored Delta/HEAD meaning, validation, and atomic apply.
- The consumer reuses Chatlas's configured production agent selection rather than inventing a second provider/profile/model configuration surface.
- Current surfaces are idempotent no-ops; append-only surfaces inspect only pending evidence; revised, diverged, or blocked surfaces fail closed through the existing capture invariants.
- The semantic producer runs as an Agentos library consumer. It may spawn the configured provider harness, but never shells out to `agentos` or hand-writes Delta files.
- Maintenance-agent subprocesses suppress Agentos hook delivery through an explicit process-control environment variable, preventing recursive turn-stop production. This variable controls dispatch only; it is never treated as provider context data.
- Failures remain daemon callback failures: they are logged and serial dispatch continues according to the existing hook/daemon semantics.

## Impl.Agendix

- **Touched:** `Agentos.Runtime`: becomes the single application composition root for both hook callbacks and CLI command integrations.
- **Touched:** `Agentos.Hook`: gains an explicit process-local suppression control solely to prevent internal maintenance agents from recursively submitting hooks.
- **Touched:** `Chat.Index.Capture`: its semantic boundary is preserved; CPU code owns evidence/envelope/validation/apply, while an agent owns Delta and HEAD meaning.
- **Touched:** `Agentos.Daemon`: remains the deferred serial executor; no durable inbox or retry policy is introduced.
- **Execution gate:** autonomous implementation and checkpoint commit are authorized by ^c20260811-54u.

## Execution.Plan

### Vertical.Slice 1 — Migration checkpoint

- **Status:** in progress.
- Verify the linter wording against the parser invariant and focused tests.
- Cold-reread this requirement, stage every current `agentos-py` change, and commit the completed monolith migration.

### Vertical.Slice 2 — Runtime-owned command composition

- **Status:** pending.
- **RED:** prove the CLI adapter delegates registration to a runtime and no longer imports feature registrars or Chatlas integration callbacks.
- **GREEN:** move deterministic registrar order and subsystem injections into a lazy runtime method; keep CLI behavior and extension hooks compatible.
- **Check:** runtime, CLI, daemon, and command-surface tests.

### Vertical.Slice 3 — Semantic turn-stop capture

- **Status:** pending.
- **RED:** prove turn-stop invokes a semantic capture producer after targeted refresh, uses the resolved identity, suppresses recursive hooks, and logs failures through ordinary daemon dispatch.
- **GREEN:** add an importable Chat.Index capture runner over the configured Agentos provider, call it from the Chatlas hook consumer, and add generic hook-dispatch suppression for that child process.
- **Check:** focused Chatlas capture/hook, agent runtime, hook, and daemon tests with all external processes replaced by fakes.

### Vertical.Slice 4 — Verification and closure

- **Status:** pending.
- Run focused suites, the full monolith suite, Ruff on touched files, `git diff --check`, packaging build, installed entrypoint smokes, and live daemon lifecycle checks.
- Update this log with authoritative evidence and leave the post-checkpoint implementation changes uncommitted for review.

## Impl.Log

- **Decision:** a warmed session cache is not a Chat.Index Delta.
- **Decision:** a mechanical or empty Delta would violate Chat.Index's semantic extraction contract; deferred maintenance therefore requires a configured semantic agent producer.
- **Decision:** the existing Chatlas `run_produce` agent selection is the initial shared configuration surface for retained agent production.
- **Review:** `_linter_structure.py` checks for a parsed trailing anchor span, so `Index.Line.Anchor` is the precise invariant name; `Support.Reference` is the broader semantic relationship and was misleading in this diagnostic.
