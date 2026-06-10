# Chatlas Skip Linked Session Targets - impl-req

## Impl.Abstract

- **scope:** prevent Chatlas and shared agent session discovery from indexing provider sessions whose native session target is a symlinked directory.
- **status:** ready for implementation.
- **source:** after linking `~/.claude-br/projects -> ~/.claude/projects`, the user wants Chatlas to skip sessions that are pointed through a symlink so linked Claude homes do not duplicate the same underlying transcripts.
- **goal:** keep Claude runtime symlink behavior intact while making Chatlas native scans ignore linked session roots.
- **target repository:** `/Users/pereiro/projects/agentos-project/agentos-py`
- **related package:** `agentos-chatlas-py` consumes this shared discovery path through `agentos.agent.sessions`.

## Impl.Index

### Current.State

- Claude Code session discovery is rooted at `home/projects`.
- `agentos.providers` defines the Claude Code home spec with:

```text
direct_relpaths=("projects",)
direct_anchor_roles=("projects_root",)
```

- `ClaudeAgent.discover_session_refs()` calls `agent_session_paths(self)` and then `discover_claude_session_refs(targets=direct_targets)`.
- `agentos.agent.sessions._discover_direct_provider_sessions(...)` wraps provider-native refs into provider-neutral `ProviderSessionRefEntry` objects.
- Chatlas calls `_discover_instance_sessions(...)` in `agentos_chatlas.delta_scan`, which calls `instance.agent.discover_session_refs()`.
- With `~/.claude-br/projects` symlinked to `~/.claude/projects`, Python glob/session discovery follows the symlink target and surfaces `.claude` transcripts as if they came from `.claude-br`.

### Accepted.Design

Skip linked session roots at the shared agent session discovery boundary.

Preferred implementation point:

```text
src/agentos/agent/sessions.py
```

Inside or adjacent to:

```python
def _discover_direct_provider_sessions(context: ProviderAgentContext) -> list[ProviderSessionRefEntry]:
```

Semantics:

- If a configured direct session target itself is a symlink, skip that direct target for discovery.
- For Claude Code, this means a linked `home/projects` contributes zero sessions.
- Non-linked provider homes continue to discover normally.
- Do not error. This is a skip guard for scanners, not a user-facing failure.

### Scope.Boundary

This is about scanner/dataset hygiene, not Claude runtime behavior.

Do not modify:

- Claude CLI launch behavior
- account auth or credential reconciliation
- provider profile home selection
- raw Chatlas archive layout
- existing already-indexed Chatlas rows

Do not make Chatlas follow symlinks and dedupe later. The desired behavior is to avoid accepting linked provider-home artifacts as native scan input.

### Why Shared Session Discovery

The guard belongs in `agentos.agent.sessions`, not `agentos_chatlas.raw_archive`.

Reasons:

- Chatlas should not need provider-home topology knowledge.
- Raw archive happens after a provider-native session has already been accepted.
- `_copied_source_path(...)` resolves source paths, which is exactly the behavior that makes linked homes appear to point outside their configured home.
- Shared discovery protects Chatlas update, Chatlas provider query, and generic agent session listing consistently.

### Reporting.Shape

The minimal accepted behavior can silently skip linked direct targets.

If useful and low-cost, provider diagnostics may expose skipped symlink targets later, but this implementation does not require a new CLI reporting surface. Do not add warning plumbing unless it is already easy in the current structures.

### No.Legacy.Allowed

Do not add compatibility aliases or a mode flag to re-enable symlink scanning.

Do not preserve linked-home duplicate indexing behavior behind a config option.

Do not add migration code for old indexed rows; cleanup of existing duplicates is a separate task.

## Execution.Plan

### Slice 1 - Add Linked Direct Target Filter

Status: pending.

Add a focused helper in `src/agentos/agent/sessions.py`, expected shape:

```python
def _discoverable_direct_targets(context: ProviderAgentContext) -> tuple[Path, ...]:
    ...
```

or equivalent.

Behavior:

- return direct targets excluding paths where `target.is_symlink()` is true.
- use the filtered targets for discovery.
- if all direct targets are symlinks, discovery returns an empty list.

Observable result:

- a provider context whose only direct target is a symlink produces no session refs.

Check:

- write a unit test that creates a Claude-like `projects` directory, links another home's `projects` to it, builds a configured Claude agent for the linked home, and verifies generic session discovery returns zero sessions for that linked home.

### Slice 2 - Preserve Normal Claude Discovery

Status: pending.

Ensure the same test module proves non-linked Claude `projects` discovery still works.

Behavior:

- a real `projects/<encoded>/<session-id>.jsonl` target is discovered normally.
- a symlinked `projects` target is skipped.

Observable result:

- normal Claude direct targets still emit session refs.

Check:

- paired RED/GREEN tests in the relevant existing agent session test file, or a new focused file if no adjacent one exists.

### Slice 3 - Chatlas Boundary Smoke

Status: pending.

Run a read-only Chatlas/provider discovery smoke against the current linked home setup if feasible.

Useful commands:

```sh
agentos chatlas provider query --provider claude-code --session-id 67b706eb-d233-446f-96ce-926f52560eab
agentos chatlas index update --provider claude-code --output-mode json --scan-cache false --session-index-cache false
```

Use care with mutating index update. If the executor chooses not to run an update against the real Chatlas root, validate through unit tests and a read-only command only.

Required validation:

```sh
uv run pytest tests/test_agent_sessions.py -q
uv run pytest tests/test_agent_session_copy.py tests/test_agent_sessions.py -q
uv run ruff check src/agentos/agent tests/test_agent_sessions.py
git diff --check
```

If the actual adjacent test filename differs, use the current nearest session-discovery test file and record that choice in `Impl.Log`.

## Acceptance Signals

- Linked Claude `projects` homes are ignored by shared agent session discovery.
- Normal non-linked Claude `projects` homes still discover session JSONL files.
- Chatlas native scan no longer receives sessions from `~/.claude-br` when `~/.claude-br/projects` is a symlink to `~/.claude/projects`.
- The implementation does not alter Claude runtime execution or account credential behavior.
- Tests and Ruff pass for the touched agent session discovery surface.

## Impl.Log

- 2026-06-09: Created from the linked Claude homes / Chatlas duplicate-indexing discussion. The design intentionally skips symlinked native session roots at discovery time instead of adding Chatlas-specific dedupe or raw archive path special cases.
