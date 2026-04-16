# Agentos.Mission

Mission Control — a coordination surface for defining and tracking named blocks of work.

---

## What It Is

- A **named anchor point** that answers: "where does what we're doing right now fit in the bigger picture?"
- A **coordination layer**, not a project management tool
- Opt-in: you don't need to always be in a mission

## What It Is NOT

- Not a requirement for every work session
- Not where implementation details live (that's plans, live-notes, etc.)
- Not a task tracker — TODOs inside a mission are lightweight, not granular

## Core Model

A mission has a small structured header and a freeform notes section:

- **name** — short identifier (kebab-case, used as filename)
- **goal** — concise statement of what we're trying to achieve
- **validation** — how we know it's done
- **status** — `active`, `done`, or `parked`
- **last_activity** — the last time this mission was explicitly worked on or resumed; used for ranking and default selection
- **help** — self-documenting annotation layer; maps field names to help text (string) or structured objects with progressive disclosure
- **todos** — lightweight checklist (micro-missions, goals/validations can be implicit)
- **notes** — append-only freeform text list: relations, links, decisions, context

## Storage

```
.agentos/missions/
  auth-rewrite.mission.json
  rate-limiter.mission.json
```

One file per mission. Flat directory. No nesting.

Default mission selection is derived, not stored:

- when a command omits the mission name, it targets the most recently active mission with `status == active`
- the ranking signal is each mission's `last_activity`
- multiple missions may be active at once

## Key Concepts

### Forks

Ideas that emerge during a mission but may belong elsewhere. Captured immediately, triaged later:
- Becomes a TODO in the current mission
- Becomes its own mission
- Gets discarded

### Links Out

Missions reference other surfaces — they don't contain them. Implementation plans live in live-notes, specs live in index-notes. The mission just points there via notes entries.

### Relations

No structured relation system. Relations are just notes entries:
- `"Related to rate-limiter — shares the middleware layer"`
- `"Spawned from auth-rewrite fork #2"`

### Help (progressive disclosure)

The `help` field makes the mission file self-documenting. It maps field names to help text:

- **string value** → printed directly
- **object value** → has a `help` key for the summary; other keys are children accessible by drilling in

```json
"help": {
  "deploy_target": "Target environment for rollout",
  "validation": {
    "help": "Two-step: automated + manual",
    "automated": "Run paperson doctor proj-123",
    "manual": "Sign-off from security team"
  }
}
```

`agentos mission help` shows one line per field. Object entries show `[+]` to indicate children. Drill into a field name to see the full entry.

## CLI Surface

```
agentos mission new <name> --goal "..." --validation "..."
agentos mission activate <name>
agentos mission status [name]
agentos mission done [name]
agentos mission park [name]
agentos mission list
agentos mission todo add "..."
agentos mission todo done <index>
agentos mission note "..."
agentos mission fork "..." [--as-mission <name>]
agentos mission help [name] [field]
agentos mission help-set <field> "text"
agentos mission templates --list
```

`agentos mission activate <name>` does not set a singleton global pointer. It bumps that mission's `last_activity` and resumes it into `active` status so default selection can find it by recency.

## Agent Behavior

When connected to a mission:
- Check `mission status` to load context
- Ideas that fork: suggest `mission fork` or `mission new` + a relation note
- Progress: suggest `mission todo done` or adding notes with links
- Completion: check validation text, suggest `mission done`

When NOT on a mission:
- Normal work, no overhead
- If something feels like it should be tracked, suggest creating a mission
