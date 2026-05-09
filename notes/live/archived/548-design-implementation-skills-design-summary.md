# Design Implementation Skills Redesign - design-summary

## Summary

Redesign the agentos skill ecosystem around design-to-implementation workflows. Extract artifact formats into standalone skills, eliminate `agentos-team`, and distribute its useful content into focused skills.

## Accepted Decisions

1. **`agentos-design-implementation` created** — guides disciplined implementation of designs/plans. Pairs with `agentos-design-discussion`. Uses a `references/` directory for extensible best practices (general-practices, general-preferences, language-specific, pattern-specific).

2. **"Moving Forward, Not Sideways" practice** — backward-compat shims, legacy fallbacks, regression scaffolding, and data format migration code are errors unless explicitly requested. Added to `general-practices.md`.

3. **Three standalone artifact skills** — each owns one artifact type's format, writing guidance, and example:
   - `agentos-artifact-impl-req` — extracted from `agentos-team/references/impl-req.md` + `impl-req-example.md`
   - `agentos-artifact-issue-report` — new
   - `agentos-artifact-design-summary` — new

4. **`agentos-team` removed** — its content absorbed into:
   - Designer discussion behavior → already in `agentos-design-discussion`
   - Revision scan → `agentos-design-discussion`
   - Implementer orientation, execution, post-execution → `agentos-design-implementation`
   - Shared handoff standards → `agentos-design-implementation` general practices
   - Evidence priority → both `design-discussion` and `design-implementation`
   - impl-req format → `agentos-artifact-impl-req`
   - Post-execution artifact update → `agentos-artifact-impl-req`

5. **Artifact production is user-initiated** — `design-discussion` may suggest producing an artifact at convergence, but never produces one automatically. Explicit user request required.

6. **Skills kept general but extensible** — core SKILL.md files stay lean (orchestration only). Domain knowledge lives in `references/` files loaded selectively by context.

## Content Absorption Map (from `agentos-team`)

| Source | Content | Destination |
|---|---|---|
| `designer.md` | Discussion behavior | Already in `design-discussion` |
| `designer.md` | Revision scan | Add to `design-discussion` |
| `designer.md` | impl-req writing guidance | `artifact-impl-req` |
| `designer.md` | Evidence priority | `design-discussion` + `design-implementation` |
| `implementer.md` | Orientation / understanding summary | Tighten in `design-implementation` |
| `implementer.md` | "No code during understanding" rule | Add to `design-implementation` |
| `implementer.md` | Post-execution artifact update | `artifact-impl-req` |
| `implementer.md` | Staleness check | Add to `design-implementation` |
| `implementer.md` | Evidence priority | `design-implementation` |
| `SKILL.md` | Shared handoff standards | `design-implementation` general practices |
| `SKILL.md` | Live-note coordination | Already in `live-note-base` |
| `references/impl-req.md` | Format + writing guidance | `artifact-impl-req` |
| `references/impl-req-example.md` | Example | `artifact-impl-req/references/example.md` |

## Execution Plan

### Phase 1: Create artifact skills
- Create `agentos-artifact-impl-req` (extract from `agentos-team`)
- Create `agentos-artifact-issue-report` (new)
- Create `agentos-artifact-design-summary` (new)

### Phase 2: Update existing skills
- Update `agentos-design-discussion`: add revision scan, artifact suggestion at convergence (user-initiated only), evidence priority
- Update `agentos-design-implementation`: tighten orientation with understanding summary, add staleness check, add evidence priority, absorb shared handoff standards

### Phase 3: Remove `agentos-team`
- Verify all useful content is absorbed
- Remove the skill directory

## Deferred Items

- Language-specific references (`language-python.md`, `language-dart.md`, etc.) — add as needed
- Pattern-specific references (`pattern-cli.md`, etc.) — add as needed
- Shared references across skills (symlink or shared location) — start with copies, consolidate later if duplication becomes a problem
- Grouping artifact skills under a parent if the count grows too large
