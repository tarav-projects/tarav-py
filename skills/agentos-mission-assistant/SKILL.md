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

### Protocol-level validation

For spec, protocol, or contract work, validation does not have to be an end-user feature check.

It is valid for a mission's validation to point at a mechanistic repo-local validation surface such as:
- a `doctor` command
- a linter
- a schema or protocol checker
- another explicit `check` command

Prefer concrete validation commands when they exist. Examples:
- `paperson doctor <project-id>`
- `agentos mdblocks lint`

When this kind of command exists, treat it as a strong validation surface for mission progress and mission closure.

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
- If the mission is about specs or protocol-level behavior, suggest rerunning the relevant `doctor`/lint/check command and capturing the result.
- Keep it lightweight — one-line suggestions, not a ceremony.

## Mission Templates

Mission templates are project-local skills that define conventions for recurring kinds of missions. They live in the project's `skills/` directory like any other skill.

### What a template is

A skill with `type: mission.template` in its frontmatter. It contains guidance for the agent on how to create a specific kind of mission — goal phrasing, default todos, notes conventions, validation patterns, links to relevant surfaces.

Templates can be named however makes sense for the project. Discovery is done by frontmatter type, not by naming convention.

### Template frontmatter

```yaml
---
name: bug-fix
type: mission.template
description: Template for bug fix missions
---
```

### Discovering templates

```sh
agentos mission templates --list
agentos mission templates --list --json
# equivalent to: agentos skills query type=mission.template
```

### How to use templates

When creating a mission:
1. Check if a relevant template exists (`agentos mission templates --list`)
2. If found, read the template SKILL.md and follow its guidance
3. If not found, create the mission freeform as usual

The user may also ask to create a new template from an existing mission pattern.

## Conventions

- Mission names are kebab-case and filesystem-safe.
- Notes are the catch-all. Relations between missions, links to plans, context, decisions — all go in notes as plain text.
- Forks prefixed with `FORK:` in notes are unresolved ideas. They can be triaged into todos, new missions, or discarded.
- The active mission (via `_active.json`) is the default target for todo/note/fork commands.
