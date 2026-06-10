# Session Discovery Filter Ownership Cleanup - impl-req

## Impl.Abstract

- **scope:** clean up the shared linked-session-target guard so agent replacement/session-path override behavior lives with agent primitives instead of `agentos.agent.sessions`.
- **status:** ready for implementation.
- **source:** post-implementation cleanup after `642-chatlas-skip-linked-session-targets-impl-req.md`.
- **goal:** keep the linked direct-target skip behavior while tightening ownership and adding coverage for mixed linked/non-linked direct targets.
- **target repository:** `/Users/pereiro/projects/agentos-project/agentos-py`

## Impl.Index

### Current.State

- `src/agentos/agent/sessions.py` filters symlinked `ProviderAgentContext.direct_targets` before calling provider-native `discover_session_refs()`.
- Provider agents recompute home-derived paths through `agent_session_paths(self)`, so `sessions.py` currently imports `dataclasses.replace` and creates a temporary agent with `home=None`.
- That implementation is correct but leaks knowledge that concrete agents are frozen dataclasses into the shared session-discovery scanner.
- `tests/test_agent_sessions.py` proves:
  - a linked Claude `projects` target returns zero sessions.
  - a normal Claude `projects` target still returns sessions.
- No test currently proves the documented partial-filter semantics where one direct target is linked and another direct target remains discoverable.

### Accepted.Design

Move temporary filtered-agent construction into the agent primitive layer.

Preferred shape:

```python
class AgentBase:
    def with_session_discovery_paths(
        self,
        *,
        direct_targets: tuple[Path, ...],
        sqlite_db_paths: tuple[Path, ...],
    ) -> Self:
        ...
```

or an equivalent primitive-owned helper.

Semantics:

- `agentos.agent.sessions` may decide which direct targets are discoverable.
- `agentos.agent.primitives` owns how an agent is copied with explicit session discovery paths and no home-derived session paths.
- Providers should continue using their existing `discover_session_refs()` implementations.
- No user-facing CLI behavior changes.

### Scope.Boundary

Do not modify:

- provider runtime command construction.
- account/auth behavior.
- Chatlas raw archive layout.
- already-indexed Chatlas rows.
- provider-specific discovery implementation internals unless required by the ownership cleanup.

Do not add compatibility flags or a mode to scan symlinked direct targets.

### No.Legacy.Allowed

Remove the misplaced `dataclasses.replace` usage from `agentos.agent.sessions`.

Do not leave two parallel filtered-agent construction paths.

## Execution.Plan

### Slice 1 - Move Filtered Agent Copy To Primitives

Status: pending.

Change:

- Add a primitive-owned method/helper that returns an agent copy with:
  - `home=None`
  - provided `direct_targets`
  - provided `sqlite_db_paths`
- Update `agentos.agent.sessions` to call that primitive-owned behavior.
- Remove the `dataclasses.replace` import from `sessions.py`.

Observable result:

- Shared session discovery no longer knows that agents are dataclasses.
- Existing linked-target behavior remains unchanged.

RED.GREEN.Test.Suite:

- Existing `tests/test_agent_sessions.py` should stay green after the implementation.

### Slice 2 - Cover Mixed Direct Targets

Status: pending.

Change:

- Add a focused test where a Claude context has:
  - one linked direct target containing a session.
  - one normal direct target containing a different session.
- Shared discovery must return only the session from the normal target.

Observable result:

- Partial filtering semantics are verified directly.

RED.GREEN.Test.Suite:

- Add the test before implementation if Slice 1 has not already covered it.
- Run `uv run pytest tests/test_agent_sessions.py -q`.

### Slice 3 - Validation

Status: pending.

Run:

```sh
uv run pytest tests/test_agent_sessions.py tests/test_agent_session_copy.py -q
uv run ruff check src/agentos/agent tests/test_agent_sessions.py
git diff --check
```

## Acceptance Signals

- `agentos.agent.sessions` filters direct targets but no longer imports or calls `dataclasses.replace`.
- The agent primitive layer owns filtered session-discovery agent construction.
- Linked-only Claude direct targets still produce zero sessions.
- Normal Claude direct targets still discover sessions.
- Mixed linked/non-linked direct targets discover only the non-linked target.
- Focused tests and Ruff pass.

## Impl.Log

- 2026-06-09: Created by autonomous codebase cleanup after implementing linked session target skipping. Cleanup target is intentionally narrow: ownership of temporary discovery-agent construction and missing mixed-target test coverage.
