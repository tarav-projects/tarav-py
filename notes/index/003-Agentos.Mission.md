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
- **todos** — lightweight checklist (micro-missions, goals/validations can be implicit)
- **notes** — append-only freeform text list: relations, links, decisions, context

## Storage

```
.agentos/missions/
  _active.json              # {"active": "mission-name"} or {"active": null}
  auth-rewrite.mission.json
  rate-limiter.mission.json
```

One file per mission. Flat directory. No nesting.

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
```

## Agent Behavior

When connected to a mission:
- Check `mission status` to load context
- Ideas that fork: suggest `mission fork` or `mission new` + a relation note
- Progress: suggest `mission todo done` or adding notes with links
- Completion: check validation text, suggest `mission done`

When NOT on a mission:
- Normal work, no overhead
- If something feels like it should be tracked, suggest creating a mission
