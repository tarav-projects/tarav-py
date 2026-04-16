# Action.Graphs (WIP)

## Why This Note Exists

This note captures a general agent-protocol idea that emerged from PaperSON work, but is likely broader than PaperSON itself.

Extracted from `PaperSON/notes/live/502-action-graphs-wip.md` into agentos because the pattern applies to Mission Control and any CLI+skill harness system.

It is an incubation note kept here so the idea can be:

- discussed concretely against real work
- pressure-tested on real Projects and missions
- connected to the Mission Control meta-harness design

---

## Working Name

- `Action.Graphs`

This is a working name.

The current meaning is:

- a structured graph that defines legal agent movement over the evolution of an `Identity`
- with graph topology represented structurally
- and action semantics described in natural language

---

## Core Idea

`Action.Graphs` are not just diagrams.

They are a structured prompt protocol for agents.

The graph says:

- what kinds of objects are being tracked
- what states those objects may legitimately be in
- what actions may move them between states
- when an agent is allowed to step outside the graph

The key behavioral rule is:

- the agent should respect and follow the graph topology
- if asked to move an `Identity` from current state `A` toward desired state `X`, it should find a legal path in the graph
- it should not invent an unlisted shortcut
- if no suitable graph path exists, it should report that gap or use `Escaping` if explicitly allowed

So the graph is an outer policy:

- the agent is free inside each action
- but not free to ignore the graph topology

---

## Minimum Concepts

### `Identity`

The object whose evolution is being tracked.

Examples:

- a publication figure panel
- a supplementary dataset
- a project
- a note
- a software artifact

An `Identity` is the thing that can have state.

### `State.Node`

A named state descriptor that can be attached to an `Identity`.

Important properties:

- an `Identity` may have more than one `State.Node`
- `State.Node`s are not necessarily exclusive
- `State.Node`s may be nested or compositional, such as `invalid.paperson.record`
- the meaning of a `State.Node` is defined in natural language
- the criterion for judging that an `Identity` is in that state is also defined in natural language

Examples:

- `source.available`
- `normalized.available`
- `paperson.record`
- `reconstruction.available`
- `invalid.paperson.record`

### `Action`

A legal transition object in the graph.

An `Action` has two layers:

- structured topology
- natural-language execution semantics

The topology says:

- from which state set the action may be invoked
- to which outcome state set or sets it may lead

The instructions say:

- what the action means
- what the agent should do
- how the agent should think about success

### `Escaping`

`Escaping` is not part of graph topology.

It is an agent mode.

Meaning:

- the user or protocol explicitly tells the agent to stop obeying the `Action.Graph` for a moment
- the agent may then do whatever is necessary outside graph semantics

This is important because the system should guide agents without over-rigidizing them.

Recommended obligations when escaping:

- record why graph semantics were insufficient
- record what was done outside the graph
- record whether the graph should be updated later

### `Evaluation.Action`

An explicit action used to check whether an `Identity` really satisfies a declared `State.Node`.

It is conceptually different from ordinary transformation actions.

It does not primarily create a new artifact.

It checks whether a state claim is actually valid.

Typical pattern:

- self-loop on success
- branch to a nested invalid state on failure

Example:

- `paperson.record -> paperson.record`
- or `paperson.record -> invalid.paperson.record`

---

## Structured Topology, Natural-Language Semantics

The topology should be structured.

For example, JSON can define:

- identities
- state nodes
- actions
- allowed state-set transitions

The action body can remain natural language.

That natural language explains:

- what to do
- how to do it
- how to judge completion

So:

- legality is structured
- execution is agentic

This is a key design point.

The graph should not rely on prose alone to determine whether an action is topologically allowed.

---

## Basic Shape

Minimal structured shape:

```json
{
  "identities": [
    { "id": "fig-1b" }
  ],
  "state_nodes": [
    {
      "id": "source.available",
      "definition": "The identity has at least one usable authority source surface."
    },
    {
      "id": "paperson.record",
      "definition": "The identity is exposed as a public semantic PaperSON.Record."
    },
    {
      "id": "invalid.paperson.record",
      "definition": "The identity was claimed to be a PaperSON.Record but does not satisfy that state definition."
    }
  ],
  "actions": [
    {
      "id": "direct.parsing",
      "from_all": ["source.available"],
      "outcomes": [
        {
          "id": "success",
          "to_all": ["paperson.record"]
        }
      ],
      "instructions": "Create a public PaperSON.Record from the available source surfaces, preserving paper-faithful naming and semantics."
    },
    {
      "id": "evaluate.paperson.record",
      "from_all": ["paperson.record"],
      "outcomes": [
        {
          "id": "valid",
          "to_all": ["paperson.record"]
        },
        {
          "id": "invalid",
          "to_all": ["invalid.paperson.record"]
        }
      ],
      "instructions": "Check whether the identity truly satisfies the state definition of paperson.record."
    }
  ]
}
```

This is intentionally minimal.

It does not yet define:

- whether states are added, replaced, or removed
- whether some actions are preferred over others
- whether traversal traces are mandatory

Those can be layered later if needed.

---

## State Semantics

`State.Node`s are defined in natural language.

At minimum, each state should say:

- what the state means
- what it means for an `Identity` to be in that state

This matters because the graph is not only structural.

It is a normative prompt system.

An agent must be able to read a state definition and judge:

- whether the state is already satisfied
- whether an action can legally target it
- whether an evaluation action should confirm or reject it

Important property:

- an `Identity` may carry multiple `State.Node`s at once

This is not a strict single-state machine.

It is a tagged-state graph.

---

## Action Semantics

Actions can have higher arity.

This means an action may map:

- from a set of required `State.Node`s
- to one or more possible resulting state sets

So actions are not restricted to:

- one input state
- one output state

This supports:

- conjunctive preconditions
- branching outcomes
- evaluation failures
- richer project evolution without requiring an overly rigid FSM

The instructions of an action remain natural language.

That is intentional.

This keeps the system agent-centered:

- graph legality is explicit
- action execution remains flexible

---

## Evaluation Versus Domain Validation

`Evaluation.Action` should be kept distinct from ordinary domain validation.

Two different questions exist:

- state evaluation:
  - does this `Identity` truly satisfy the declared `State.Node`?
- domain validation:
  - is this artifact scientifically, mechanically, or semantically acceptable?

Example in PaperSON terms:

- evaluating `paperson.record`
  - checks whether the identity really is a valid public `PaperSON.Record`
- validating a `PaperSON.Record`
  - checks whether the record faithfully matches source evidence or expected behavior

So:

- evaluation is graph-internal state checking
- validation may be one family of domain action inside a graph

---

## Escaping Mode

`Escaping` is the explicit answer to the problem of over-rigidity.

It means:

- the graph is useful
- but the graph is not absolute

When `Escaping` is enabled, the agent may:

- temporarily ignore graph topology
- perform work outside graph semantics
- later return to normal graph-guided behavior

The important point is that this should be explicit.

The system should not silently permit graph violations.

Instead:

- normal mode means graph obedience
- escaping mode means graph suspension

This keeps the graph meaningful while preserving flexibility.

---

## Why This Is Useful

This pattern is useful because it acts as:

- a language for modeling the evolution of systems, projects, and data
- a map of where we are and where we may legally go
- a structured prompt that constrains agent movement without micro-managing execution

It is intentionally compatible with ambiguity.

A graph may be:

- highly specific and strongly structured
- weakly structured, with natural-language-heavy actions
- incomplete, while still remaining operational

The important thing is not full formalization.

The important thing is that the agent can treat the graph as a real protocol.

---

## PaperSON-Flavored Example

A PaperSON identity such as `fig-1b` might evolve through states like:

- `source.available`
- `normalized.available`
- `paperson.record`
- `reconstruction.available`
- `validation.recorded`

Actions might include:

- `normalization`
- `digitization`
- `direct.parsing`
- `reconstruction`
- `validation`
- `evaluate.paperson.record`

In that setting:

- `validation` should be about the `PaperSON.Record`
- source, normalized, and reconstruction artifacts are evidence surfaces for validation

This PaperSON example is only one consumer of the pattern.

The pattern itself appears broader than PaperSON.

---

## Connection to Mission Control

Mission Control is an instance of this pattern:

| Action.Graphs | Mission Meta-Harness |
|---|---|
| Identity | A mission |
| State.Node | Mission status (`active`, `done`, `parked`) |
| Action | CLI command (`activate`, `done`, `park`, `todo add`, `fork`) |
| Action instructions | Skill guidance (mission-assistant) |
| Evaluation.Action | Mission validation check |
| Escaping | Agent editing JSON directly, bypassing CLI |
| Graph topology | Available CLI commands + active skills |

The CLI enforces legal transitions. The skill provides natural-language semantics. The help system provides progressive disclosure of field-level context.

---

## Current Boundaries

This note does not yet define:

- a canonical storage schema for `Action.Graphs`
- whether graphs should be versioned independently
- whether actions add or replace states by default
- whether traversal traces are required
- whether state definitions should support machine-readable predicates
- how Mission Control could formally embed Action.Graphs per mission or template

These are later design questions.

For now, the main stabilized idea is:

- `Action.Graphs` define legal movement
- `State.Node`s define legitimate state descriptors
- `Action`s define allowed transitions over state sets
- `Evaluation.Action` checks state claims
- `Escaping` explicitly suspends graph obedience when flexibility is needed
