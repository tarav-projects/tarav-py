# Agentic Development Philosophy - core-design

## Motivation

We are defining the conceptual model for a design-session system that can separate conceptual design, TODO design, and execution planning.

The model is being developed from a discussion of Matt Pocock's agentic development workflow, but adapted to this project's design-session style: nonlinear concept work, user-gated settlement, appendable artifacts, and later TODO design on top of the core design.

## Items Index

- Design.Alignment.Core: [closed] surfaced design judgments explicitly settled with the user
- Design.Alignment.Fundamentals: [closed] minimum expected dimensions of the core
- Alignment.Sufficiency: [converging] agent judgment of enough settled alignment for the current task
- Design.Open.Space: [closed] unsettled part of the current design state
- Delegation Frontier: [closed] boundary between settled core and open space
- Design.Session: [in-progress] overall model for design-session work
- Design.Session.Core.Design: [in-progress] native concept-design layer of a design session
- Design.Session.TODO.Design: [in-progress] task-design layer for what must be done about the core design
- Design.Session.Exec.Plan: [in-progress] execution plan derived from TODO design
- User.Gated.Writing: [closed] exact proposed text or diff must be shown before writing
- User.Gated.Trigger: [closed] write path starts only after explicit user trigger

## Items

### Design.Alignment.Core

`Design.Alignment.Core` is the set of design judgments that have been surfaced and explicitly settled with the user.

It represents the part of the design universe that the user has explicitly shaped.

`Design.Alignment.Fundamentals` are the minimum expected dimensions of the core: intent, scope, behavior, taste, tradeoffs, acceptance, risk, and ownership boundaries. A task may introduce additional dimensions, but these fundamentals are the default areas the agent should consider when looking for significant design judgment from the user.

Design material enters `Design.Alignment.Core` only when the user explicitly accepts or requests its inclusion. The material may originate from the user, the agent, the codebase, or another source, and may appear through answering, choosing, accepting a recommendation, rejecting an option, defining a boundary, clarifying intent, or naming a tradeoff. But surfacing judgment is not the same as settling it into the core.

The core is user-gated in that sense. The agent can propose candidate material, but only the user can settle it into the core.

`Design.Alignment.Core` is useful because the more relevant settled judgment it contains, the more aligned and useful the agent's later decisions can be.

Example: during a design discussion, the agent should usually try to grow `Design.Alignment.Core` by surfacing significant questions and recommendations. The agent should be strategic: it should focus on significant design judgments, not ask every possible question.

#### Usage History

- Used to distinguish user-settled design material from material merely proposed by the agent or surfaced in conversation.
- Used to clarify that inclusion in the core is explicitly user-gated.

### Design.Alignment.Fundamentals

`Design.Alignment.Fundamentals` are the minimum expected dimensions of `Design.Alignment.Core`: intent, scope, behavior, taste, tradeoffs, acceptance, risk, and ownership boundaries.

A task may introduce additional dimensions, but these fundamentals are the default areas the agent should consider when looking for significant design judgment from the user.

#### Usage History

- Originally explored as a broad checklist for design alignment.
- May need refinement or replacement under the newer `Design.Session` layered model.

### Alignment.Sufficiency

`Alignment.Sufficiency` is the agent's judgment of whether enough relevant human alignment has been settled for the current task.

It is an agent-side expectation, not a user gate. The user defines the actual delegation frontier and may override the agent's sufficiency judgment at any time.

Example: during a design discussion, the agent may use its sufficiency judgment to provide a well-timed recommendation, warning, or status message without interrupting the flow. For instance: "I'll proceed with a minimal implementation. One note: taste is still lightly specified, so I'll keep the UI conservative and follow existing patterns."

#### Usage History

- Introduced to distinguish the agent's expectation frontier from the user's actual authority over whether to continue, defer, or proceed.

### Design.Open.Space

`Design.Open.Space` is all design material that has not been settled into `Design.Alignment.Core`.

It includes undecided, unexamined, implicit, deferred, or agent-assumed design material. It is the unsettled part of the current design state.

`Design.Open.Space` is not necessarily a problem. It simply marks what has not yet become settled human-shaped design material.

#### Usage History

- Used to avoid treating every unanswered design question as a blocker.
- Used to establish that unsettled material can remain available for pragmatic agent judgment when later work requires it.

### Delegation Frontier

`Delegation Frontier` is the current boundary between `Design.Alignment.Core` and `Design.Open.Space`.

It describes the current state of the design: what has been settled with the user, and what remains unsettled. The frontier moves when design material enters or leaves `Design.Alignment.Core`.

The frontier is not the same as an instruction, prompt, permission rule, or workflow gate. Those may influence how the agent behaves, but the frontier itself describes the current settled/open shape of the design.

#### Usage History

- Used to describe the current settled/open shape of the design without turning it into a workflow permission rule.

### Design.Session

`Design.Session` is the overall model for the current discussion style: a nonlinear, appendable design session where concepts can be named, revised, settled, left open, or later adapted into implementation work.

In Agentos, development is a convergence process: humans and agents progressively align `Current.Implementation` with `Design.Target.Model`, while allowing both design understanding and implementation reality to refine each other.

`Design.Session` is one of the main tools for managing that convergence without pretending everything is known upfront. It gives the human a place to settle design judgment, gives the agent a place to track open space and sufficiency, and gives execution a clean path from design into action.

The session has three major layers:

- `Design.Session.Core.Design`
- `Design.Session.TODO.Design`
- `Design.Session.Exec.Plan`

#### Operating Principles

##### Alignment Before Execution

Design work should precede execution work. The expected order is `Core.Design -> TODO.Design -> Exec.Plan`.

This does not make the process rigid or waterfall. It means execution should be downstream of some explicit design/alignment surface, not raw chat impulse.

##### Vertical Implementation Slices

Execution design should prefer successive end-to-end slices over horizontal phases.

A slice should produce something verifiable through the relevant interface or artifact boundary. This follows the tracer bullet idea: get feedback across the whole path early instead of building one layer at a time.

##### Feedback Loops

Execution design should include how the work will be checked.

Feedback can be tests, type checks, manual QA, artifact inspection, review, user approval, or interface behavior checks. Vertical slices and feedback loops reinforce each other: one strong way to validate a change is to implement a thin end-to-end path and test the observable behavior.

##### Human Taste / Judgment Is Preserved

The system should preserve space for human judgment without prescribing one interaction style.

The agent may use discussion, interview, recommendations, status warnings, or other interaction patterns. At this level, the principle is only that human taste and judgment remain part of the design system.

##### Context Discipline

Execution should depend, in principle, on artifact data rather than fragile chat memory.

This pressures the system to produce good artifacts: settled design items, TODO design, execution plans, summaries, issues, or other durable surfaces.

##### Evidence-Based Analysis

The agent should rely on source-of-truth evidence for claims that can be checked.

If the question is about the codebase, inspect the codebase. If it is about the current artifact, inspect the artifact. If it is about the transcript, inspect the transcript or working summary. Do not rely on stale descriptions when the source is available.

#### Usage History

- Introduced after the design started circling between the user's design-session model and Matt Pocock's implementation workflow.
- Used to separate conceptual design from TODO design and execution planning.
- Used to connect the session model with existing Agentos index concepts: `Design.Target.Model`, `Current.Implementation`, `Progress.Gradient`, and `Design.Implementation.CoEvolution`.

### Design.Session.Core.Design

`Design.Session.Core.Design` is the native design layer of a session. It contains the named concepts, meanings, behaviors, relationships, open questions, and settled judgments produced through discussion.

This layer is similar to the current design-session artifact style. It is not primarily an implementation workflow. It is where the design is clarified and where material may enter `Design.Alignment.Core` or remain in `Design.Open.Space`.

The `*-core-design.md` file should use this structure:

- `## Motivation`
- `## Items Index`
- `## Items`
- `### <Item>` sections
- `## Notes`
- `## End Log`

#### Usage History

- Used to define the file format for the conceptual design layer.
- Updated to use `Items Index` for status/navigation and `Items` for item bodies.

### Design.Session.TODO.Design

`Design.Session.TODO.Design` is the task-design layer built on top of core design. It defines what must be done about the discussed design before a concrete execution plan is written.

This is where Matt Pocock's workflow is most relevant: prompt, evidence, structure, validation, boundaries, vertical slices, tests, review, and readiness for agent execution.

An `*-todo-design.md` file may include task objectives, guidance, evidence, structure, validation, boundaries, and open questions.

#### Usage History

- Introduced as the layer where Matt Pocock's workflow belongs on top of this project's design-session model.
- Finalized as `TODO.Design` because the layer is about what must be done about the discussed design, while `Exec.Plan` is the actual plan.
- Split into its own `*-todo-design.md` file during the migration to the new session format.

### Design.Session.Exec.Plan

`Design.Session.Exec.Plan` is the execution layer derived from TODO design. It contains the concrete plan, tasks, issue breakdown, write steps, or agent loop needed to carry out the work.

This layer may be small for simple artifact edits or larger for feature implementation work.

#### Usage History

- Introduced as the third layer of the design session.
- Not yet split into its own file in this migration.

### User.Gated.Writing

`User.Gated.Writing` means the agent may prepare changes to a file or artifact, but must present the exact proposed text or diff to the user before writing.

The user may have already triggered the write, but the write itself is still gated by preview and approval.

Example: the user says, "add this to this file." That is a trigger. But if the file is `User.Gated.Writing`, the agent must still show the exact text or diff before applying it.

#### Usage History

- Used to define artifact mutation authority separately from design decision authority.

### User.Gated.Trigger

`User.Gated.Trigger` means the agent may write to a file or artifact only after the user explicitly triggers that write.

The agent may propose that a write would be useful, but it must not begin the write path on its own.

Example: the agent thinks a session summary should be updated. If the artifact is `User.Gated.Trigger`, the agent may suggest the update, but it must wait until the user asks it to write.

If an artifact is both `User.Gated.Trigger` and `User.Gated.Writing`, the agent needs two user gates:

1. The user must explicitly trigger the write.
2. The agent must present the exact proposed text or diff before applying it.

`User.Gated.Trigger` controls when the write path may begin.

`User.Gated.Writing` controls whether the proposed write must be previewed and approved before mutation.

#### Usage History

- Used to distinguish "the user asked for a write" from "the user approved the exact write."

## Notes

- `Design.Alignment.Core + Design.Open.Space == design universe` for the current task.
- `Design.Alignment.Core` is a concept, not a workflow.
- The core is user-gated by settlement, not by the mere existence of possible questions.
- A `Design.Session` should have at most three files: `*-core-design.md`, `*-todo-design.md`, and `*-exec-plan.md`.
- This migration currently creates only the core-design and todo-design files.
- Index relationship note: `Design.Session.Core.Design` is like a staged fragment of `Design.Target.Model`; `Design.Session.TODO.Design` defines how the session should move `Current.Implementation` closer to that target fragment; `Design.Session.Exec.Plan` is the concrete execution path for that move.

## End Log

- 2026-05-08: Created initial mixed design-session artifact.
- 2026-05-08: Added `Alignment.Sufficiency` as an agent-side expectation, distinct from the user-defined delegation frontier.
- 2026-05-08: Added and closed `Design.Open.Space` and `Delegation Frontier`.
- 2026-05-08: Rewrote and closed `Design.Alignment.Core`; added and closed `Design.Alignment.Fundamentals`.
- 2026-05-08: Added the high-level `Design.Session` model with `Core.Design`, a task-design middle layer, and `Exec.Plan`.
- 2026-05-08: Added `Design.Session` operating principles from the Matt Pocock workflow.
- 2026-05-08: Added and closed `User.Gated.Writing` and `User.Gated.Trigger`.
- 2026-05-08: Migrated from a mixed `design-session` artifact to the `*-core-design.md` file format with `Items Index`, `Items`, and per-item `Usage History`.
- 2026-05-09: Finalized the task-design middle layer as `Design.Session.TODO.Design` and migrated `501` to `*-todo-design.md`.
- 2026-05-09: Added the Agentos development-as-convergence rationale and related the session layers to existing index concepts.
