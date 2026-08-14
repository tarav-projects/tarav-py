# Claude statusLine hook attributed usage by environment, not by context - issue

## Issue.Abstract

- **symptom:** `tarav agent accounts monitor` showed byte-identical rows for two different
  claude-code accounts — same percentages, same reset *instants*.
- **status:** fixed 2026-08-14; contaminated records remain in the registry (see Residue).
- **severity:** the monitor is the surface used to decide which account to spend. One account's
  consumption was recorded under another's name and presented as fact.
- **related:** `732-agent-account-identity-unverified-issue.md` — the read-side counterpart. This
  note is the write side. Neither alone explains the symptom; together they do: wrong attribution at
  write time, no verification at read time.

## Evidence

Records for account `jp`, written by the statusLine hook from `home=/Users/pereiro/.claude`, tracked
**om's** numbers in lockstep:

```
jp  08:57:30  statusline_hook          5h 27%  resets 13:10:00   7d 71%  resets 14 Aug 15:00
om  08:57:56  statusline_rate_limits   5h 27%  resets 13:10:00   7d 71%  resets 14 Aug 15:00
br  08:57:52  statusline_rate_limits   5h  0%  resets 13:40:00   7d 18%  resets 20 Aug 06:00
```

Two independent accounts cannot share a five-hour window boundary to the second. The `jp` stream is
also visibly a *mixture* — one record in the same minute carries `7d resets 15 Aug 10:00`, a window
belonging to no other account in the set. `br` read clean only because no interactive br session was
running.

Counts for the month, claude-code records by writing home:

| records | account | source | home |
|---|---|---|---|
| 601 | jp | `statusline_hook` | `~/.claude` |
| 14 | jp | `statusline_hook` | `~/.claude-jp` |
| 2 | om | `statusline_hook` | `~/.claude-om` |
| 1 | br | `statusline_hook` | `~/.claude-br` |

601 against 17 — the fallback was the rule, not the exception.

## Root.Cause

`agent/providers/claude_code/usage_hooks.py`, `_claude_home()`:

```python
configured = os.getenv("CLAUDE_CONFIG_DIR") or os.getenv("CLAUDE_HOME")
if configured:
    return Path(configured).expanduser().resolve()
return (Path.home() / ".claude").resolve()
```

The hook resolved *whose* usage it was holding from the **environment**, then mapped that home to an
account. Claude Code does not pass `CLAUDE_CONFIG_DIR` into the statusLine child process, so every
session fell through to `~/.claude` — which is the `jp` account. All four homes share one
`settings.json` (they are symlinks to the same file) and one `~/.claude/statusline` script, and
nothing on that path carries the home.

The invocation context already named the home three times over (`transcript_path`, `cwd`,
`workspace.project_dir`). The hook did not look at it.

## Fix

**A hook attributes only from its context.** `_claude_home()` is replaced by
`_claude_home_from_ctx(ctx)`, which derives the home from `transcript_path` —
`<home>/projects/<project-slug>/<session>.jsonl` — and raises `HookError` when the context has no
transcript path or the path is not under a provider home. There is no environment read and no
default; an unattributable context writes nothing rather than guessing.

`cwd` and `workspace.*` were rejected as sources: they name the *working directory*, which for a
statusline-refresh session sits under the home but for an ordinary session is an arbitrary project
path.

## Why the suite did not catch it

`tests/test_claude_usage_hooks.py` set `CLAUDE_CONFIG_DIR` in its fixture and passed
`transcript_path: "/private/session.jsonl"` — a path with no relationship to the home. The tests
encoded the defective mechanism, so they could only ever confirm it.

The fixture now points `CLAUDE_CONFIG_DIR` at a **decoy home owned by a different account**, so every
test in the file asserts environment-independence as a side effect. Three tests added:

- two homes reporting in the same dispatch sequence land on two accounts with their own numbers
- a context without `transcript_path` raises and writes nothing
- a `transcript_path` outside a provider home raises and writes nothing

Suite: 1897 passed.

## Live verification

The daemon holds the hook callbacks in memory, so the fix does not take effect until it is
restarted — the first post-edit probe still landed on `jp`. After `tarav daemon stop && start`:

| probe transcript | account | home recorded |
|---|---|---|
| `~/.claude-om/projects/-probe/probe-2.jsonl` | om | `~/.claude-om` |
| `~/.claude-br/projects/-probe/probe-3.jsonl` | br | `~/.claude-br` |

The clearest evidence is an unsynthetic one: the *same* live session (`a80aca81-…`) wrote
`account=jp home=~/.claude` at 09:10:25 and `account=om home=~/.claude-om` at 09:10:30 — the restart
falls between them. The monitor now reports three distinct rows (`jp` 11% / `br` 44% / `om` 32%)
where it reported two identical ones.

Two synthetic probe records (`probe-2`, `probe-3`) are in the registry carrying invented percentages.
They are superseded as *latest* by the next genuine refresh for those homes.

## Residue

The ~601 mis-attributed `statusline_hook` records under `jp` with `home=~/.claude` are still in
`~/.tarav/agent/usage-registry/202608-usage.jsonl`. They are not deleted — the registry is an
append-only record and the monitor reads the *latest* record per account, so the contamination clears
itself as fresh correctly-attributed records arrive.

Not addressed here: nothing verifies that a record's account matches the session that produced it.
That is note 732, and it is what would have surfaced this within one frame instead of by a human
noticing duplicate numbers twice.
