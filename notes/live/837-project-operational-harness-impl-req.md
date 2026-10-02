# 837 — Project operational harness for agent-written scripts

## Impl.Abstract

Knowledge.Surface: wiki
Alignment.Mode: Interactive
Status: needs alignment on the first concrete operation; design artifact saved.

Design a first application of the project Python package as an operational
interface for agents. Agents may generate scripts on the fly that compose
project-owned operations. Those operations implement project conventions and
surface Checks/POIs during work. The objective is precise, inspectable mechanics
without prescribing every reasoning step or every possible script.

This invocation requests the implementation request only. No product code,
environment provisioning, agent execution, or user-data mutation is authorized
by this Design pass. No new pipeline engine, sandbox, mandatory ProgramRun
lifecycle, or universal I/O wrapper is selected.

## Design narrative

### Redesign authority

The User explicitly clarified that this is a revisit of the design, not
necessarily an extension of the existing implementation. Existing code is
evidence and potentially reusable material, not an architectural constraint.
Keep, reshape or replace it according to the desired operational model.
Do not preserve an abstraction merely because it already exists. This authority
is for design here; product changes still belong to a later execution phase.

Grounding pending: latest visible User voice turn beginning “Yes but it is
important ... we can redesign whatever is there”. Exact Chatlas Turn resolution
is subject to the capture limitation recorded below.

### User direction from the current discussion

The project harness is a Python package specific to a project, using Tarav's
shared primitives. The analogy is Pandas: an agent can write a new Python script
for a particular task rather than select only prewritten scripts. The task's
designated operations must use the harness, while the agent remains free to
compose those operations and reason about the work.

The User emphasized that code is an efficient way to communicate precise
operational expectations, including formats and checks. The agent can inspect
the source. Functions can surface POIs while the task is performed; validation
need not be exclusively a later linter pass. Additional orchestration machinery
may be unnecessary if instructions plus an ordinary library suffice.

The User requested fundamental interface analysis, not generic reminders that
agents supply semantic judgment. The central design question is what makes
this style of interaction efficient enough to justify its overhead.

Evidence status: these paragraphs are a bounded paraphrase of visible User
voice turns in this conversation, not independently resolved Chatlas references.
Relevant exact-session locator: codex session
`01a0d86c-9538-7be1-af96-014cd4203d61`, previously resolved identity
`6734aba0b9204f614baf3987604865fa85146495877841244ad7fe1efce4104b`.
Do not treat assistant responses or voice transcript summaries as substitute
User-Turn evidence. Resolve the actual turns before completing capture.

### Agent proposals for interface design

These are proposals to exercise, not individually settled User decisions:

- Local contracts: arguments, returned objects and mutations should be
  understandable without reconstructing a hidden global call sequence.
- Composable results: outputs should feed subsequent operations without repeated
  prose parsing, identifier reconstruction or ad-hoc format conversion.
- Progressive inspection: compact entry points with deeper data/source/context
  available when requested; neither opaque success messages nor mandatory dumps.
- Convenient builders and explicit paths: support common cases without making
  special cases leave the operational API. Existing Situation/LiteRecord patterns
  are examples, not mandatory representations for all task data.
- Design the learning path alongside the API: a new project package lacks the
  model's accumulated familiarity with Pandas. A small runnable example and
  discoverable source/contracts should teach the first useful workflow.

Instructions define the required operating route; ordinary Python code provides
the mechanics. This does not claim technical prevention of direct filesystem
access. Hard isolation is a separate, unrequested feature.

### Inspected foundations

- `src/tarav/l2/project/harness.py`: ProjectHarness already provides project
  package/environment scaffolding and inspection. It is not itself the proposed
  domain-operation API. Assess whether that boundary remains useful; its
  provisioning mechanics may be reused, reshaped or replaced with justification.
- `src/tarav/l3/project/harness.py`: bootstrap/run/main supply explicit project
  runtime and process entry points. Evaluate their fit rather than presuming
  this launching path is mandatory. Avoid duplicate mechanisms without a reason.
- `src/tarav/l1/programs/__init__.py`: TaravProgram is an identified placeholder.
  `src/tarav/l2/project/programs/__init__.py` provides ProjectProgram without
  execution or attachment semantics. Do not infer an implemented ProgramRun.
- `src/tarav/l1/checks/__init__.py` and `src/tarav/l1/poi/` already supply
  checks, situation-based evaluation and notifications. Reuse or revise them
  where appropriate; not every operation must become a Check or a Program.

Programs can later represent reusable undertaking definitions and particular
runs, but ordinary harness composition does not require settling that ontology
first. This request focuses on the recent operational-library discussion.

### First slice proposed for alignment

Choose one real project and one bounded task with a meaningful existing
read/transform/write convention. The conversation used extracting decisions
into a Wiki as an assistant illustration, not a User-selected pilot. Do not
silently implement that illustration as the product requirement.

Once selected, implement a small project-local API with a composable read and
write/registration path, one normal result path, and a visible POI path. Let an
agent compose it using a short ad-hoc Python script. Keep domain policy in the
project package; promote common mechanics only when reuse justifies them.

The first slice should answer whether the existing Tarav tools are enough.
Avoid inventing a generic Operation/Step/Process class hierarchy or workflow
DSL before the pilot exposes a concrete need.

## Impl.Req.Wiki

Product owner: tarav-py for general library work; pilot project ownership must
be selected before project-local implementation.
Wiki owner/root: `tarav-md/notes/wiki`.
Relevant context: `tarav-harness.md`, `programs.md`, `checks-workflow.md`,
`caller-declared-identity-inputs.md`.
Capture status: pending. Daily destination when grounded capture can run:
`daily/2026-10-02.md`. Topical additions should describe this general pattern
under `tarav-harness.md`, without claiming a new Program lifecycle was chosen.

## Execution.Plan

1. Align on the pilot project, task and operations that must use its harness.
   This is the outstanding implementation choice, not a demand to design a
   universal interface in advance.
2. Inspect that project's instructions, package, existing operations and data
   formats. Compare the desired model with the current one; explicitly identify
   what to retain, reshape or replace, including runtime/environment interfaces.
3. Define and implement the smallest useful operational API. Document inputs,
   effects and returned values beside the code. Surface meaningful POIs through
   existing Tarav mechanics without forcing an unrelated return-contract change.
4. Supply one executable usage example and concise agent instructions pointing
   to that interface and its source. Preserve freedom to write different scripts.
5. Exercise normal operation and a problematic-input case through agent-written
   code. Record friction and API gaps before generalizing any new primitives.
6. Add focused checks for the pilot's actual contract, capture User-grounded
   product Breadcrumbs, and update the request with results.

### Acceptance and evaluation

- A short script can import the project package and complete the selected task
  through its designated operations without reimplementing its storage formats.
- Operation results compose without parsing human-oriented CLI output.
- The agent can locate required types, effects and examples without reading the
  whole package; document what it actually needed, rather than claiming a token
  or cost saving without measurement.
- A relevant POI is inspectable by the calling agent during the exercise.
- Different compositions remain possible; no fixed-script-only or hidden global
  initialization requirement is introduced beyond documented runtime setup.
- Retained behavior is deliberate, not mandatory compatibility. Where redesign
  changes discovery, launch or another existing contract, specify the replacement
  and affected consumers before execution. No new engine is assumed necessary.

## Impl.Log

2026-10-02 — Design request created from the visible discussion after inspecting
existing ProjectHarness and Programs foundations. No product code changed.
The shared worktree contains substantial unrelated edits; none were included.

The User then explicitly authorized rethinking the existing design rather than
assuming extension. Revised the request to remove mandatory preservation of
current provisioning/launch boundaries and require deliberate reuse decisions.

Chatlas exact-session refresh failed with PermissionError writing
`/Users/pereiro/Documents/tarav/chatlas/cache/session-index-derivations-v2/.../sessions.json`.
Current permissions allow workspace edits but not the retained Chatlas/Breadcrumb
stores. Exact-turn resolution, Breadcrumb submission, Wiki capture and the scoped
evidence-commit bracket remain pending. No hashes or grounding labels were
fabricated, and no alternative store was created to bypass that boundary.
