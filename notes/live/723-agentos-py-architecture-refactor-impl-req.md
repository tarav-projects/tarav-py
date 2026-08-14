# Agentos Python Architecture Refactor — Impl.Req

## Impl.Abstract

- Status: executable
- Scope: reorganize the maintained `agentos` modular monolith around clear subsystem namespaces, dependency direction, composition boundaries, and shared infrastructure while preserving its CLI commands, four installed scripts, persisted data formats, and tested behavior.
- Source authority: the autonomous development request authorizing large scans, system moves, namespacing cleanup, common-utility consolidation, and weak-code removal. ^c20260811-62u
- Baseline checkpoint: `agentos-py` commit `2329776`; supporting Agentos catalog/canvas checkpoints `e1bf40e` and `8427eef`.
- Out of scope: new product features, compatibility packages for superseded internal import paths, changes to provider-native data formats, and speculative framework abstractions without at least two concrete consumers.

## Impl.Index

### Architecture target

- `agentos.runtime` remains the only composition root. CLI and daemon entrypoints import the runtime; subsystem foundations do not import adapters merely to obtain defaults.
- `agentos._core` owns small dependency-free infrastructure used across domains: clock, JSON/file persistence, process, path, project, sequence, and text primitives.
- `agentos.stdlib` owns reusable user-facing primitives whose CLI already lives under `agentos stdlib`: Markdown blocks, prefix allocation, Git references, and miscellaneous utilities.
- `agentos.agent` owns provider-neutral agent/account/session orchestration and a discoverable `agentos.agent.providers.<provider>` adapter tree. Provider packages no longer occupy unrelated top-level namespaces.
- Domain systems with independent contracts remain top-level (`chatlas`, `hooks`, `daemon`, `index`, `wayfinder`, `poi`, `skillware`, `anchory`, `bloberia`, `canvas`, `tournament`, `workspaces`, and similar cohesive systems).
- Integration dependencies point downward or enter through injected sockets. A foundation does not import its runtime adapter to provide a convenient default.

### Hard evidence

- Current source size is 89,176 lines. `chatlas` owns 33,356 lines and the provider/agent area owns more than 23,000 lines.
- Top-level import SCCs are: provider adapters with `agent`; `index`/`mdblocks`/`poi`/`wayfinder`; and `hooks`/`daemon`.
- Seven provider adapter namespaces (`claude`, `codex`, `copilot`, `gemini`, `openclaw`, `opencode`, `pi`), `providers.py`, `home/providers.py`, and `agent/providers.py` obscure one provider subsystem across ten locations.
- `mdblocks`, `prefix`, `refs`, and `utils` are composed beneath the `stdlib` CLI but live as unrelated top-level Python packages.
- `skw` is a small backend-neutral network layer shared by Index and Skillware; its independent namespace reflects real multi-consumer ownership.
- Iterante and Iterante v2 duplicate closely related calls, context, environment, error, harness, locking, redaction, rendering, and state mechanics.
- Atomic JSON writes, JSON-object loading, timestamp formatting, and JSON hashing are independently implemented across several subsystems.
- Baseline Ruff reports four findings; the behavior suite passes 1,786 tests and the standalone wheel builds without sibling repositories.

### Design constraints

- Preserve observable CLI behavior and script entrypoints; Python namespace changes are deliberate clean moves, not compatibility-shim migrations.
- Move code by ownership before splitting for size. A smaller file in the wrong subsystem is not an architectural improvement.
- Shared utilities enter `_core` only when semantics are truly common and callers do not lose domain-specific validation or durability guarantees.
- Large modules split by cohesive command/domain responsibility behind one public registrar or facade.
- New architecture checks test dependency and namespace boundaries, not private helper placement.
- Every moved surface leaves no stale module, import, test name, documentation route, or package artifact.

## Impl.Agendix

- touched: ^c20260811-62u — autonomous authorization and requested outcome.
- touched: `index://tarav-pkg/Deep.Modules` — prefer deep subsystems with small entry surfaces.
- touched: `index://tarav-pkg/Agent.Navigable.Codebase` — make ownership and entrypoints discoverable without reading the monolith.
- touched: `index://tarav-pkg/Dependency.Profile.Split` — cores do not import upward; runtime composition owns bridges.
- touched: `index://tarav-pkg/No.Legacy.Allowed` — remove superseded paths and stale documentation rather than aliasing them.

## Execution.Plan

### Slice 1 — architecture contract and map

- Status: completed
- Change: add a concise maintained architecture map and boundary tests that inventory allowed top-level namespaces, enforce the composition-root boundary, and expose dependency cycles as explicit evidence.
- Observable result: a new contributor can locate shared infrastructure, domains, providers, adapters, and entrypoints from one document; architecture tests fail on the current misplaced namespaces.
- RED: boundary tests name the intended provider, stdlib, skillware, and hook/daemon boundaries and fail before moves.
- GREEN: tests pass after the corresponding slices; normal CLI help remains unchanged.
- Check: focused architecture tests, Ruff, CLI help snapshot.

### Slice 2 — provider subsystem namespace

- Status: completed
- Change: move provider specs, home resolution, extractors, agents, sessions, auth, quota readers, and hooks beneath `agentos.agent.providers.<provider>` plus provider-neutral modules beneath `agentos.agent`; update all internal consumers and tests.
- Observable result: provider work is discoverable under one tree and the old top-level provider/home modules are absent.
- Check: agent/provider/account/session/hook tests plus the architecture contract.

### Slice 3 — standard-library and Skillware namespaces

- Status: completed
- Change: move `mdblocks`, `prefix`, `refs`, and `utils` beneath `agentos.stdlib`; retain `agentos.skw.network` as a backend-neutral layer shared by Index and Skillware; keep CLI command paths unchanged.
- Observable result: Python ownership matches the existing CLI namespace and shared Skw network mechanics retain one multi-consumer owner.
- Check: stdlib, Index, POI, Skillware, and CLI e2e suites.

### Slice 4 — composition and dependency direction

- Status: completed
- Change: remove Hooks' default imports of Daemon delivery/logging adapters by injecting them from `agentos.runtime`; isolate other concrete cross-domain adapters where the scan proves a real cycle.
- Observable result: `hooks` is provider/daemon neutral, Daemon consumes hooks, and the runtime wires delivery.
- Check: hook/daemon/runtime tests and import-graph contract.

### Slice 5 — shared infrastructure and weak code

- Status: completed
- Change: add narrow `_core` persistence primitives for proven-common atomic text/JSON operations and adopt them where semantics match; centralize UTC helpers; remove dead imports, stale helpers, and duplicated code made obsolete by the moves.
- Observable result: fewer independent durability implementations, zero Ruff findings, and no generic utility dumping ground.
- Check: persistence-owning subsystem tests, Ruff over `src` and `tests`, architecture tests.

### Slice 6 — large-surface decomposition

- Status: completed
- Change: split oversized command/orchestration modules by cohesive command family, starting with `chatlas.commands`; consolidate shared Iterante mechanics only where v1/v2 behavior is genuinely identical.
- Observable result: public registrars remain small entry surfaces while implementation groups match user-visible domains; duplicate runtime mechanics have one owner.
- Check: Chatlas CLI/e2e suites, both Iterante suites, import smoke tests.

### Slice 7 — completion audit

- Status: completed
- Change: update `AGENTS.md`, README, and active architecture surfaces; audit removed paths and imports; install the editable tool; build wheel/sdist; run the complete suite.
- Acceptance signals: no stale namespaces, no architecture-contract failures, zero Ruff findings, unchanged CLI command families and scripts, clean standalone package metadata, and the complete behavior suite green.

## Impl.Log

- 2026-08-11 — Execution authorization resolved through ^c20260811-62u. The autonomous mode permits architecture decisions in open space while the artifact records scope and evidence.
- 2026-08-11 — Baseline checkpoint committed before implementation edits as required by the execution workflow.
- 2026-08-11 — Provider adapters moved under `agentos.agent.providers`; stdlib Python ownership now matches the existing CLI namespace.
- 2026-08-11 — Scan evidence corrected the planned Skw move: Index and Skillware both consume the backend-neutral network model, so it remains independently owned instead of being folded into Skillware.
- 2026-08-11 — Hook/Daemon injection and the Index/POI/Wayfinder resolver composition removed all top-level subsystem import cycles; 165 focused architecture and integration tests passed.
- 2026-08-11 — Nine persistence owners adopted the shared fsynced atomic-replacement primitive; Ruff reached zero findings and 170 focused durability tests passed.
- 2026-08-11 — Chatlas parser composition separated from command behavior, and identical Iterante context/locking/error mechanics gained one shared implementation; 490 Chatlas and 250 Iterante tests passed.
- 2026-08-11 — Completion audit passed: retired runtime imports are absent, Ruff is clean, all 1,794 tests pass, wheel and sdist build, the wheel installs without sibling repositories, and all four editable entrypoints were refreshed.
