# 888 — Operator Context workflow — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Design.
Status: needs-alignment (see Open questions). Depends on request 887.

Create the Operator Context: a workflow of its own that gives whoever is
acting a place to state its context, so Tarav code can know who is calling
and react. It is a folder with a main record in the Project's `.tarav/`,
linked to the session, in which other workflows keep their own spaces.

Non-goals: a vocabulary of Directives; Harnessed Actions or Programs;
gating or refusing any action; conditioning `context()` or checks on the
operator. Those build on this and are still under discussion.

## Design narrative

Agents should act with their intention at hand so they can hook into the
machinery; otherwise the system knows nothing about the caller's intention.
<!-- tarav.breadcrumb 1bc150c325d5b876d9b29277a973d9e2cb3ceebdc9588ea563e1b3bcfc6725ce -->

The User described it as a typed context object for the operator: the operator
establishes its context and the code reacts. It is a communication protocol.
<!-- tarav.breadcrumb 3389b2be8700bbfde19137a27197783b17085ccd1914c45c88deca7cdd6c215f -->

The realization that matters: the operator context is an explicit object, so
the code finally knows who is calling. Define it and its mechanics first, then
see what follows.
<!-- tarav.breadcrumb 7abf3250fec2ee9342864f7537df914814ca440c83f7a2811d6f213379fd37ce -->

What the User fixed about it: it holds what the agent puts there for the code
to contextualize; it is linked to the session ID; it lives in the Project's
`.tarav/` and the agent maintains it; every run can read it; workflows
implement inside it what they need and can require it to be well set up;
standard checks follow, such as a session with open actions.
<!-- tarav.breadcrumb a94d14f8c0d186128d348ab45ec3da389c508e7ee2e3ba5c07cf28435853879e -->

It is a folder with a main record, described by a class. The Operator Context
is itself a workflow that others integrate with: they demand things or put
things there themselves. Each space's internal organization belongs to its
workflow.
<!-- tarav.breadcrumb 978ed0a419d8d103128c3a0a71eb9cb80e4192430a06887ad489985e38fff629 -->

It is its own workflow, not a part of Agents. It formalizes the first node of
any pipeline: the context is prepared, the pipeline runs only on the stated
context, and when something is missing the pipeline says what to configure.
<!-- tarav.breadcrumb 18e8324bb454a0c4a6d514ee8fbdf62e80f20ab112feee5f0f6bb8a20c2f3d1d -->

### Current behavior (observed 2026-10-09)

- Nothing models the running operator. A blessing stores an `actor` mapping
  supplied by the caller; that is the only place an operator is recorded.
- A Project's `.tarav/` holds tracked folders such as `poi-tracking/` and
  `skillware/`, and `.tarav/state/`, which the root `.gitignore` excludes.
- Folder-shaped Tarav objects exist (`Tarav.DirectoryRecord`, used by the
  Skillware depot, Breadcrumbs and the Chatlas Normal Model).
- The current session will be answered by the Agents workflow (request 887).

### Agent choices (proposals, not User decisions)

- **Workflow.** `tarav.l1.operator` with its identity, workflow and the
  `OperatorContext` Type; Project integration in `tarav.l2`.
- **Layout.** One folder per operator session, with a main record holding the
  session (provider and native ID) and who is acting, and one subfolder per
  integrating workflow. The Operator Context does not read those subfolders.
- **Declared and observed kept apart.** What the operator declared and what a
  workflow recorded about it live in different places, so a check can tell a
  claim from an observation.
- **Finding it.** Code obtains the context for the running session through
  the Agents entry point; an explicit session can also be given. An operator
  that cannot be identified still works and reads as unidentified.
- **Commands** to create and show the context with keyed options; agents may
  also edit the files, and a check validates them.
- **Checks.** A Project check reports contexts whose main record is invalid.
  It is the declaration that is checked; nothing is refused.
- **One proof of use**, to keep the design honest: a blessing made with a
  context present records a reference to it beside `actor`.

### Open questions

- Is the folder local to the machine (under `.tarav/state/`) or committed
  with the Project? Agent lean: local, with durable records elsewhere.
- Who may write a workflow's space: the agent, the workflow's code, or both?
- How is a non-agent operator identified (the User editing by hand, Tarav
  Center)?
- Is the folder keyed by the native session ID or by the Chatlas identity?
- Is the blessing integration in scope, or a later request?

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant notes:
`operator-context.md` (with three simulated usages), `agents-workflow.md`, `programs.md`, `daily/2026-10-09.md`. Supporting session: `claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a`. Capture status: done (Wiki notes written 2026-10-09).

## Execution.Plan

Provisional until the open questions are answered.

1. Start checkpoint. Workflow identity, `OperatorContext` Type, main record,
   create and read; tests.
2. Project integration: location, finding the running session's context,
   workflow spaces; tests with two sessions in one Project.
3. Commands and the Project check; tests through the CLI.
4. The proof of use, if in scope.
5. Full suite, Ruff, a live try in this workspace; Breadcrumbs, `AGENTS.md`
   and `ARCHITECTURE.md` for the new workflow, Wiki, completion commit.

## Impl.Log

- Designed 2026-10-09. Not executed.
