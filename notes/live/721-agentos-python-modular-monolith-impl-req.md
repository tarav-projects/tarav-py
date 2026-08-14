# 721 — Agentos Python modular-monolith migration

## Impl.Abstract

- **Scope:** consolidate the maintained Agentos Python runtime, feature packages, CLI, daemon entrypoints, and tests into the single `agentos-py` distribution while retaining subsystem namespaces and library-native composition.
- **Status:** implemented and verified.
- **Source:** autonomous `$tarav-hugentics --impl --dev --AUTO` execution gate. ^c20260811-53u
- **Baseline:** six Python repositories, 1,786 passing tests: Agentos 973, CLI 76, Chatlas 483, Canvas 4, Iterante 148, Iterante v2 102.
- **Out of scope:** merging Markdown or JavaScript projects, redesigning subsystem behavior, perfecting every public import on the first pass, removing preserved Git history, and adding cross-language distribution machinery.

## Impl.Index

### Distribution.One

- `agentos-py` becomes the one maintained Python distribution and owns the `agentos`, `agentos-daemon`, `iterante`, and `iterante2` entrypoints.
- Chatlas, Canvas, CLI composition, and both current Iterante harnesses move beneath `src/agentos/` as `agentos.chatlas`, `agentos.canvas`, `agentos.cli`, `agentos.iterante`, and `agentos.iterante2`.
- Internal imports use the monolith namespaces directly. No compatibility packages or CLI-spawn bridges are added.
- Feature boundaries remain deep library namespaces; one distribution does not mean one module or one undifferentiated dependency direction.

### Runtime.Composition

- `agentos.runtime` is the library composition root. It creates the shared `HookRegistry` and applies foundation and feature consumer registrations in one deterministic order.
- The CLI is an adapter over importable command registrars and runtime composition. It does not own subsystem behavior.
- The daemon has a dedicated library-native process entrypoint. Manual detached start and launchd invoke `agentos-daemon`, never `agentos daemon run` as a subprocess.
- The daemon and CLI each construct the same runtime through `agentos.runtime`; neither process shells out to the umbrella CLI to perform Agentos work.

### Migration.Preservation

- Before implementation, every nested repository receives a checkpoint commit, including an empty checkpoint when clean. This preserves the exact pre-monolith state and includes the current daemon/login work.
- Superseded Python repositories retain their complete `.git` directories and move only after monolith test parity to `_DEPRECATED/` under the umbrella workspace.
- Markdown and JavaScript repositories remain active in their current locations. `agentos-py` remains active and is never moved.
- A migration manifest records each source repository, checkpoint commit, destination namespace, baseline suite, and eventual archived path.

### Verification.Parity

- The imported suites run from `agentos-py` without path dependencies on the superseded repositories.
- The minimum behavioral parity target is the 1,786-test green baseline; test collection may be reorganized but no source suite is silently omitted.
- Installed-tool smoke verifies all public entrypoints import code from `agentos-py` and the real LaunchAgent points to the dedicated daemon executable.
- Only after parity and installed-runtime verification may the superseded repositories move to `_DEPRECATED`.

## Impl.Agendix

- **Touched:** `Agentos.Hook` and `Agentos.Daemon`: their existing semantics stay intact; only their composition and process entrypoint ownership move into the monolith.
- **Touched:** `Chatlas.Update.Pipeline`: implementation moves under `agentos.chatlas` without changing targeted refresh behavior.
- **Touched:** Iterante package identity: the canonical harness becomes `agentos.iterante`; the active v2 experiment is preserved as `agentos.iterante2` until a separate product decision retires or merges it.
- **Design rule:** monolithic distribution, modular internals. Subsystems may collaborate through the runtime composition root while lower-level modules retain directional imports.
- **Execution gate:** `$tarav-hugentics --impl --dev --AUTO` on 2026-08-11. ^c20260811-53u

## Migration.Manifest

| Source repository | Pre-migration HEAD | Baseline | Monolith destination | Archived repository |
|---|---:|---:|---|---|
| `agentos-py` | `bdd4da5` | 973 | `src/agentos/` | active; not archived |
| `agentos-cli` | `fd91c9d` | 76 | `src/agentos/cli/` | `_DEPRECATED/agentos-cli` |
| `agentos-chatlas-py` | `56c6163` | 483 | `src/agentos/chatlas/` | `_DEPRECATED/agentos-chatlas-py` |
| `agentos-canvas-py` | `88d5c82` | 4 | `src/agentos/canvas/` | `_DEPRECATED/agentos-canvas-py` |
| `agentos-iterante-py` | `0054a7a` | 148 | `src/agentos/iterante/` | `_DEPRECATED/agentos-iterante-py` |
| `agentos-iterante-2-py` | `866c56f` | 102 | `src/agentos/iterante2/` | `_DEPRECATED/agentos-iterante-2-py` |

All remaining nested repositories also received checkpoints: Canvas JS `20954ce`, Canvas MD `a029345`, Chatlas MD `b5d132a`, Iterante MD `c07f21d`, Agentos MD `3a78451`, and Projects Center MD `ec6c0f7`.

## Execution.Plan

### Vertical.Slice 1 — Evidence and repository checkpoint

- **Status:** complete.
- Register the exact execution gate, capture all repository states, and commit every nested repository before the first migration edit.
- Cold-reread this requirement after checkpoint and resolve any material ambiguity before implementation.

### Vertical.Slice 2 — Runtime and process boundaries

- **Status:** complete.

- **RED:** prove CLI and daemon construct the same registered hook set and prove daemon start/install target the dedicated executable rather than the umbrella CLI.
- **GREEN:** add `agentos.runtime`, move composition into it, add library-native CLI/daemon entrypoints, and update launchd/manual start mechanics.
- **Check:** focused runtime, CLI, daemon, hook, and launchd suites.

### Vertical.Slice 3 — Feature namespace ingestion

- **Status:** complete.

- **RED:** collect every source suite from inside the monolith and fail on unresolved legacy package imports.
- **GREEN:** ingest Chatlas, Canvas, Iterante, Iterante v2, and CLI sources/tests; rewrite imports; merge runtime dependencies, package data, and scripts into `agentos-py`.
- **Check:** each formerly independent suite passes from the monolith project.

### Vertical.Slice 4 — Installed monolith parity

- **Status:** complete.

- Run the complete combined suite, Ruff on migrated surfaces, packaging build, import checks, and all four installed entrypoint smokes.
- Reinstall `agentos-py` as the editable tool, reinstall/restart the LaunchAgent, and verify its executable path and live socket lifecycle.

### Vertical.Slice 5 — Repository retirement and documentation

- **Status:** complete.

- Move only the five superseded Python repositories, with their `.git` histories intact, into `_DEPRECATED` after parity.
- Update umbrella routing, `agentos-py` guidance, README/install documentation, manifest checkpoint hashes, and this implementation log.
- Re-run the combined suite after the move to prove no hidden path dependency remains.

## Impl.Log

- **Decision:** one release owns the coherent Python system; subsystem namespaces remain the import surface.
- **Decision:** both Iterante implementations are preserved during consolidation because migration is not product retirement.
- **Decision:** the parity floor is the complete green pre-migration Python baseline of 1,786 tests.
- **Decision:** the five old distributions are archived only after monolith-only and installed-runtime verification.
- **Execution authorization:** autonomous implementation is authorized by ^c20260811-53u.
- **Checkpoint:** all twelve nested repositories were committed before the first migration edit; clean repositories received explicit empty checkpoints.
- **Implemented:** `agentos.runtime` now creates the shared hook runtime; `agentos.cli` composes command adapters over it, and `agentos-daemon` starts the same runtime directly without routing through the umbrella CLI.
- **Implemented:** Chatlas, Canvas, Iterante, Iterante v2, umbrella CLI, their fixtures, and all six original suites now live in `agentos-py`; internal imports use `agentos.*` namespaces and the distribution owns all four executables.
- **Parity verification:** the combined suite collects and passes exactly 1,786 tests. It remained green after the five source repositories moved out of their original paths, proving the monolith has no test-time path dependency on them.
- **Packaging verification:** source and wheel builds pass; migrated Python surfaces pass Ruff; `git diff --check` passes.
- **Formatting baseline:** repository-wide format check reports 136 inherited files that Ruff would reformat. They were preserved byte-for-byte during consolidation; normalization is intentionally deferred to avoid mixing a large cosmetic rewrite into the namespace migration.
- **Installed verification:** the editable `agentos` tool owns `agentos`, `agentos-daemon`, `iterante`, and `iterante2`; installed imports resolve to `agentos-py/src/agentos`.
- **Daemon verification:** `org.agentos.daemon` is loaded and running, and its LaunchAgent contains one absolute `ProgramArguments` entry targeting the monolith-owned `agentos-daemon` executable.
- **Archived:** `agentos-cli`, `agentos-chatlas-py`, `agentos-canvas-py`, `agentos-iterante-py`, and `agentos-iterante-2-py` moved to the umbrella `_DEPRECATED/` directory with checkpointed `.git` histories intact.
