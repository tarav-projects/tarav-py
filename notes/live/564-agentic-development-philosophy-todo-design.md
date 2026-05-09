# Agentic Development Philosophy - todo-design

## Motivation

This file captures what we must do about the discussed core design. It describes task objectives, guidance, validation, and boundaries before any concrete execution plan is written.

The current TODO design has two objectives:

1. Consolidate the `agentos-md` index with the design objects discussed in this session.
2. Update the design-session skill to fit the improved design.

## Items Index

- Index.Update: [closed] promote `Design.Session` into the `agentos-md` index as a durable convergence concept
- Skill.Update: [closed] update `agentos-design-session` as the single operational skill for the indexed `Design.Session` model

## Items

### Index.Update

Promote `Design.Session` from skill-level behavior and live artifact convention into a durable Agentos index concept.

The index update should position `Design.Session` as a scoped human-agent convergence surface inside `Agentos.Hugentic.Flow`. It should explicitly relate the model to the existing index concepts `Design.Target.Model`, `Current.Implementation`, `Progress.Gradient`, and `Design.Implementation.CoEvolution`.

Core rationale:

> In Agentos, development is a convergence process: humans and agents progressively align `Current.Implementation` with `Design.Target.Model`, while allowing both design understanding and implementation reality to refine each other.

Expected index changes:

- Add `111-Design.Session.md` as the main concept note.
- Update `001-ontology.md` with low-resolution entries for the new named concepts.
- Update `000-index.md` to include the new concept note.
- Update `109-Agentos.Hugentic.Flow.md` so `Design.Session` is a named Hugentic Flow concept, not only a skill/artifact component.
- Optionally update `100-Agentos.Index.Notes.md` with a small relationship note that design sessions can stage material before promotion into durable index truth.

Concepts likely needing ontology entries:

- `Design.Session`
- `Design.Session.Core.Design`
- `Design.Session.TODO.Design`
- `Design.Session.Exec.Plan`
- `Design.Alignment.Core`
- `Design.Open.Space`
- `Delegation.Frontier`
- `Alignment.Sufficiency`
- `User.Gated.Writing`
- `User.Gated.Trigger`

Guidance:

- Follow `agentos-md` index-writing guidance.
- Check the existing `agentos-md` index context before writing.
- Do not turn the new index note into a transcript or artifact-format manual.
- Capture the durable model: convergence, layers, user-gated settlement, open space, sufficiency, and flow into execution.
- Keep skill-specific behavior in the skill update unless it expresses durable design truth.

Validation:

- A future agent should be able to read the index and understand why `Design.Session` exists without reading this chat.
- The new note should make clear how `Design.Session.Core.Design` stages a fragment of `Design.Target.Model`.
- The new note should make clear that `Design.Session.TODO.Design` defines how the scoped session should move `Current.Implementation` closer to the staged target fragment.
- The index should no longer rely on the `agentos-design-session` skill as the only durable source for design-session semantics.

### Skill.Update

Update `agentos-design-session` into the single operational skill for the indexed `Design.Session` model.

The updated skill should live in:

```txt
skills/agentos-design-session/
  SKILL.md
  references/
```

Do not split the new model across a separate artifact skill for now. Artifact descriptions should live as reference files inside `agentos-design-session`.

Expected skill changes:

- Update `skills/agentos-design-session/SKILL.md` for behavior and workflow.
- Add one reference file per artifact layer:
  - `references/core-design.md`
  - `references/todo-design.md`
  - `references/exec-plan.md`
- Update existing references as needed:
  - `references/session-status.md`
  - `references/uncommitted-work.md`
  - `references/capture-audit.md`

Core workflow:

- Load all references.
- Read `notes/index/111-Design.Session.md` as the durable model when available.
- Coordinate a layered `Design.Session`, not just one design-session artifact.
- Prefer the flow `Core.Design -> TODO.Design -> Exec.Plan`.
- Track settled design material, open space, sufficiency, user gates, and layer transitions.

Artifact reference guidance:

- `core-design.md` should define `*-core-design.md`: conceptual design layer, staged `Design.Target.Model` fragment, items index, item bodies, notes, end log, and writing guidance for concepts, meanings, behaviors, relationships, settled material, open space, and usage history.
- `todo-design.md` should define `*-todo-design.md`: task-design layer, movement from `Current.Implementation` toward the staged target fragment, objectives, guidance, evidence, validation, boundaries, open questions, notes, and end log.
- `exec-plan.md` should define `*-exec-plan.md`: concrete execution layer derived from TODO design, ordered steps, validation, risks, known files/commands/tests, vertical slices where possible, and deviation handling.

Guidance:

- Do not over-design `Exec.Plan` yet. Support it, but keep the initial reference thinner than `Core.Design` and `TODO.Design`.
- Preserve the existing useful behavior: nonlinear discussion, item tracking, facilitation, capture audit, uncommitted work, and status reports.
- Replace the old single-document assumption with layered session awareness.
- Keep artifact guidance practical: not only format, but also what to write, what not to write, and how each layer should be used.

Validation:

- A future agent using only `agentos-design-session` should understand the indexed `Design.Session` workflow.
- The skill should no longer depend on `agentos-artifact-design-session` as the active artifact authority for this new model.
- The references should make clear how to write `core-design`, `todo-design`, and `exec-plan` files.
- Existing status, uncommitted-work, and capture-audit behavior should remain recognizable, but layer-aware.

## Notes

- `TODO.Design` is about task design: objectives, guidance, validation, and boundaries.
- `TODO.Design` is not the concrete execution plan.
- The concrete plan belongs in `*-exec-plan.md` only after the task design is discussed.

## End Log

- 2026-05-09: Cleared the previous middle-layer draft and replaced it with fresh `Index.Update` and `Skill.Update` task-design items.
- 2026-05-09: Finalized the file and layer as `TODO.Design`.
- 2026-05-09: Expanded `Index.Update` with the target index changes, concept list, guidance, and validation criteria.
- 2026-05-09: Executed `Index.Update` by adding `111-Design.Session.md` and updating the index router, ontology, Hugentic Flow note, and Index Notes relationship note.
- 2026-05-09: Expanded `Skill.Update` with the single-skill migration scope and reference-file plan for `Core.Design`, `TODO.Design`, and `Exec.Plan`.
- 2026-05-09: Executed `Skill.Update` by updating `agentos-design-session`, adding layer artifact references, and making status, uncommitted-work, and capture-audit behavior layer-aware.
