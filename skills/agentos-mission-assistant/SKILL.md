---
name: agentos-mission-assistant
description: Help the user work with missions — create, activate, update, close, fork, and decide where current work fits. Invoke when the user asks about missions or when mission-related decisions arise.
user-invocable: true
---

# Mission Assistant

General-purpose assistant for working with missions. See index note `003-Agentos.Mission.md` for the full concept.

## What Missions Are

A mission is a named block of work with:
- **goal** — what we're trying to achieve (one sentence, action-oriented)
- **validation** — how we know it's done (observable, checkable)
- **todos** — lightweight checklist of steps
- **notes** — freeform append-only text (relations, links, decisions, forks)

Missions are a coordination layer. They don't contain implementation details — those live in live-notes, plans, code. Missions point at those things via notes.

Not all work needs a mission. Casual, exploratory, or quick tasks are fine without one.

## CLI Reference

All commands require being inside an agentos project.

```sh
# Lifecycle
agentos mission new <name> --goal "..." --validation "..."
agentos mission activate <name>
agentos mission done [name]
agentos mission park [name]

# Read
agentos mission status [name]       # active mission if no name given
agentos mission list

# Update
agentos mission todo add "text"     # --mission <name> to target non-active
agentos mission todo done <index>   # 1-based index
agentos mission note "text"         # --mission <name> to target non-active
agentos mission fork "text"         # --as-mission <name> to also create new mission
```

All commands accept `--json` for structured output.

## Judgment Guidelines

### When to suggest creating a mission

- The user describes a coherent block of work with a clear end state.
- The work will span multiple steps or sessions.
- There's value in naming it for future reference.

Do NOT suggest a mission for:
- Quick one-off tasks (fix a typo, answer a question).
- Exploratory work where the goal isn't clear yet.
- Work that's already captured in an existing mission's todos.

### Proposing a new mission

When suggesting a mission, propose concrete values:
- **name**: kebab-case, short, descriptive. e.g. `auth-rewrite`, `fix-rate-limiter`, `add-mission-cli`.
- **goal**: one sentence, starts with a verb. e.g. "Replace session-based auth with JWT tokens."
- **validation**: observable outcome. e.g. "All existing tests pass and new JWT integration tests are green." Avoid vague validations like "it works" or "code is clean."

Present the proposal and let the user confirm or adjust before running the command.

### When to suggest activating a mission

- The user starts working on something that matches an existing mission's goal.
- Say what you see: "This looks like it fits mission X — want me to activate it?"

### When to suggest a fork

- An idea comes up during mission work that's tangential to the current goal.
- If it's small and related → suggest adding as a TODO on the current mission.
- If it's substantial or unrelated → suggest `mission fork` or creating a new mission.
- When in doubt, capture it as a fork note. Triage later is fine.

### When to suggest closing a mission

- All todos are checked off.
- The validation criteria described in the mission appear to be met.
- Say what you see: "All todos done, and [validation criteria] looks satisfied. Ready to close this mission?"

Do NOT auto-close. Always confirm with the user.

### When to suggest parking

- Work on a mission is paused but not abandoned.
- A different mission takes priority.
- The user says something like "let's come back to this later."

### Progress updates

When work advances a mission (code written, tests passing, decisions made):
- Suggest marking relevant todos as done.
- Suggest adding notes for decisions or links to artifacts (live-notes, PRs, etc.).
- Keep it lightweight — one-line suggestions, not a ceremony.

## Conventions

- Mission names are kebab-case and filesystem-safe.
- Notes are the catch-all. Relations between missions, links to plans, context, decisions — all go in notes as plain text.
- Forks prefixed with `FORK:` in notes are unresolved ideas. They can be triaged into todos, new missions, or discarded.
- The active mission (via `_active.json`) is the default target for todo/note/fork commands.
