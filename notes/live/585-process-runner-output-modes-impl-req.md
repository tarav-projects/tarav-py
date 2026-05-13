# Process Runner Output Modes - impl-req

## Impl-Req State

Implemented: a small generic process runner now supports explicit `terminal`, `capture`, and `stream` output modes, separate from provider command resolution.

## User Intent

Agentos needs a simple, reliable process-running system that can serve provider-agent capabilities without reimplementing provider CLIs.

The user wants a clear separation:

```txt
command resolution != process execution != output presentation
```

Provider agents should own which provider CLI command or protocol to use. A generic runner should own only how a prepared process is executed.

The accepted mode names are:

- `terminal`
- `capture`
- `stream`

## Why This Exists

Recent `agent run` / `agent ping` work clarified that human-facing provider commands should run as naturally as possible:

```txt
AgentConfig -> build argv/env/cwd -> subprocess.run(argv, inherited stdio) -> exit code
```

That is still the right default for `run(...)` and `ping(...)`.

Account status and other provider-agent capabilities have a different need: they often run provider CLI probes and parse machine-readable output. Some probes are quick one-shot commands. Others may be long-running enough that callers need progress events while still capturing output.

Agentos should support those needs through a generic runner, not by adding ad hoc subprocess code in every provider and not by making `Agent.run(...)` capture by default.

## Current Situation

Relevant current code surfaces:

- `src/agentos/agent/run_runtime.py`
  - currently runs agent commands in the natural terminal mode through `subprocess.run(...)`.
  - no longer has capture or PTY behavior.
- `src/agentos/agent/account_runtime.py`
  - has account-probe helpers that call `subprocess.run(..., text=True, capture_output=True, timeout=..., check=False)`.
  - this is useful but account-specific and not a general process surface.
- Provider account modules use mixed process patterns:
  - `src/agentos/codex/accounts.py` uses captured one-shot CLI calls and `subprocess.Popen(...)` for `codex app-server` JSON-RPC.
  - `src/agentos/claude/accounts.py` uses captured CLI calls, stream-json refresh, and a PTY/statusline refresh path.
  - `src/agentos/copilot/accounts.py` uses captured CLI calls and HTTP requests.
- `notes/live/570-provider-agent-account-capability-refactor-impl-req.md`
  - already moved account behavior toward provider-owned agent capabilities.

There is no generic low-level runner that makes execution mode explicit and reusable across agent runtime, account probes, and future provider capabilities.

## Requested Change

Add a generic process runner, preferably under:

```txt
src/agentos/_core/process.py
```

The runner should execute already-prepared commands using explicit output modes:

```txt
terminal
  subprocess owns stdin/stdout/stderr directly.
  No captured output.
  Best for human-facing agent runs and ping.

capture
  runner owns stdout/stderr pipes and returns final stdout/stderr after process exit.
  Best for short machine-readable provider probes.

stream
  runner owns stdout/stderr pipes, emits output events while the process runs, and returns final stdout/stderr.
  The runner must not print to the terminal by itself.
  Caller decides whether to print, parse, buffer, ignore, or transform output events.
```

Suggested core API shape:

```python
ProcessMode = Literal["terminal", "capture", "stream"]

@dataclass(frozen=True)
class ProcessOutputEvent:
    stream: Literal["stdout", "stderr"]
    text: str

@dataclass(frozen=True)
class ProcessResult:
    exit_code: int
    stdout: str | None = None
    stderr: str | None = None

def run_process(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    env_overrides: Mapping[str, str] | None = None,
    mode: ProcessMode = "terminal",
    timeout_sec: int | None = None,
    on_output: Callable[[ProcessOutputEvent], None] | None = None,
) -> ProcessResult:
    ...
```

Exact names may follow local style, but the mode semantics and separation of responsibilities are required.

## Constraints And Invariants

- No shell execution. Always pass argv as a sequence/list to `subprocess`.
- The runner must not know provider names.
- The runner must not build provider commands.
- The runner must not parse provider output.
- The runner must not decide which mode is appropriate; callers choose.
- `terminal` mode must preserve the normal user CLI experience by inheriting stdio.
- `capture` and `stream` are pipe-based, not terminal/PTY modes.
- `stream` must not automatically write to stdout/stderr. Output presentation belongs to the caller.
- `on_output` is only valid for `stream` mode.
- Do not reintroduce PTY capture into the generic runner.
- Non-zero provider exit codes should be returned, not raised.
- Raise only for launch/runtime failures such as command not found, timeout, or OS errors.
- Timeout should be optional; do not impose a default in the generic runner.
- Keep provider command resolution separate from this runner.
- Do not add backward-compatibility aliases.
- Do not disturb unrelated dirty worktree changes.

## Out Of Scope

- No redesign of account stats output schema.
- No full account capability refactor in this impl-req.
- No conversion of every provider subprocess call in one horizontal pass.
- No PTY support in the first generic runner.
- No terminal UI framework integration.
- No provider-specific parsing or command selection inside `_core.process`.

## Acceptance Signals

- A generic process runner exists in a non-provider-specific module.
- `terminal` mode runs a command with inherited stdio and returns only exit code.
- `capture` mode returns stdout/stderr after process exit.
- `stream` mode emits stdout/stderr events through `on_output` and also returns final stdout/stderr.
- `stream` mode does not print automatically.
- Tests prove non-zero exit codes are returned rather than raised.
- Tests prove command-not-found and timeout failures are handled explicitly.
- At least one existing call site uses `terminal` mode.
- At least one existing machine-probe call site uses `capture` mode.
- If `stream` is implemented in the first slice, tests prove hook order/behavior and final buffers.
- Existing `agent run`, `agent ping`, and account command tests pass.

## Implementation Shape

Implement in vertical slices.

### Slice 1. Add The Generic Runner With Terminal And Capture

Behavior slice:

- Add `run_process(...)` and result/event dataclasses.
- Implement `terminal` and `capture` modes first.
- Wire `src/agentos/agent/run_runtime.py` to call `run_process(..., mode="terminal")`.
- Wire one simple account-probe path, such as `run_account_command(...)`, to call `run_process(..., mode="capture")`.

Observable check:

- Focused tests cover terminal mode exit-code behavior and capture mode stdout/stderr.
- Existing `agent run` / `agent ping` tests still prove natural subprocess behavior.
- Existing account command tests still pass.

Design assumption validated:

- Command resolution remains outside the runner while execution behavior becomes shared.

### Slice 2. Add Stream Mode With Output Hook

Behavior slice:

- Implement `stream` mode using native Python subprocess pipes.
- Emit `ProcessOutputEvent(stream="stdout" | "stderr", text=...)` through `on_output`.
- Accumulate final stdout/stderr on `ProcessResult`.
- Do not write to terminal automatically.

Observable check:

- A test runs a command that writes stdout/stderr incrementally.
- The hook receives output events.
- The final result includes the captured stdout/stderr.
- The test proves no output is printed unless the hook prints it.

Design assumption validated:

- Output presentation is caller-owned; the runner only supplies events and final buffers.

### Slice 3. Tighten Error And Timeout Semantics

Behavior slice:

- Define the runner's launch/runtime error type or use project-standard `CliError` consistently.
- Preserve non-zero exit code as a `ProcessResult`, not an exception.
- Apply timeout cleanup for `capture` and `stream`.

Observable check:

- Tests cover non-zero exit code, command not found, and timeout.
- Timeout tests prove a process is not left running.

Design assumption validated:

- The generic runner is safe enough for provider-agent capabilities without accumulating ad hoc subprocess handling.

### Slice 4. Migrate Only The Obvious Shared Call Sites

Behavior slice:

- Use the runner where it reduces duplication without obscuring provider behavior:
  - `Agent.run(...)` path via `agent/run_runtime.py` in `terminal` mode.
  - account one-shot probes via `agent/account_runtime.py` in `capture` mode.
- Leave provider protocol/API/PTY paths provider-owned:
  - Codex `app-server` JSON-RPC.
  - Claude statusline/PTY refresh.
  - Copilot HTTP usage request.

Observable check:

- Existing focused tests for agent commands and account commands pass.
- No provider command selection moves into `_core.process`.

Design assumption validated:

- A shared process runner can unify execution mechanics without flattening provider capabilities into one generic command abstraction.

## Relevant Files Or Surfaces

- `src/agentos/_core/process.py`
- `src/agentos/agent/run_runtime.py`
- `src/agentos/agent/account_runtime.py`
- `src/agentos/codex/accounts.py`
- `src/agentos/claude/accounts.py`
- `src/agentos/copilot/accounts.py`
- `tests/test_agent_commands.py`
- `tests/test_agent_accounts_commands.py`
- new focused process-runner tests, likely under `tests/test_process_runner.py` or existing core tests
- `notes/live/570-provider-agent-account-capability-refactor-impl-req.md`
- `notes/live/582-agent-run-terminal-capture-impl-req.md`
- `notes/live/583-agent-ping-config-impl-req.md`
- `agentos-md/notes/index/123-Impl.Req.md`
- `agentos-md/notes/appendix/123-Impl.Req.md`

## Open Questions

- Should the first implementation expose `stream` immediately, or land `terminal`/`capture` first and add `stream` in the next slice?
- Should process launch failures use a new typed `ProcessError` or project-standard `CliError`?
- Should `env_overrides=None` mean inherit `os.environ` unchanged, while `{}` means inherit and change nothing?
- Should `stream` events be line-based or chunk-based? Recommended first pass: line-based for simplicity.
- Should `stream` mode accept separate stdout/stderr hooks, or one event hook? Recommended first pass: one event hook.

## Related Impl-Reqs

- `570-provider-agent-account-capability-refactor-impl-req.md`
- `582-agent-run-terminal-capture-impl-req.md`
- `583-agent-ping-config-impl-req.md`

## End Log

- 2026-05-13: Created after design-session alignment on a generic process runner with explicit `terminal`, `capture`, and `stream` modes. The design keeps provider command resolution separate from process execution and leaves output presentation to callers.
- 2026-05-13: Implemented `src/agentos/_core/process.py` with `terminal`, `capture`, and `stream` modes; wired `agent/run_runtime.py` through terminal mode and `agent/account_runtime.py` one-shot probes through capture mode. Added `tests/test_process_runner.py` and updated agent command tests to patch the shared runner boundary. Verified with `uv run ruff check src/agentos/_core/process.py src/agentos/agent/run_runtime.py src/agentos/agent/account_runtime.py src/agentos/copilot/accounts.py tests/test_process_runner.py tests/test_agent_commands.py` and `uv run pytest`.
