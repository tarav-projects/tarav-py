# Tarav System Prompt

This Project participates in Tarav, an agents harness for collaboration between
people and agents. Tarav records data a person has touched, keeps paths back to
that data, and helps agents recover the context needed for current work. The
Project System Prompt in this file describes this particular Project. Read both
before changing its files.

### Start here

Treat this agents file as the entry point. Read the Project's `.tarav/project.json`
to identify its Type and any parent or child Projects. Follow local project
guidance before editing. If the Project has an `AGENTS.md` in a nested folder,
read it before working there. The Tarav Constitution states the system-wide
boundaries; when available, use the `tarav-pkg` skill to find it and the
maintained design surfaces. Consult the Project's Wiki and live notes when
present, then inspect code and tests for current mechanics.

Use `tarav --help` and the relevant subcommand's `--help` to discover the
installed CLI. `tarav project status --project [PATH]` runs the Project's checks
and updates its actions from the results; run it as often as needed.
`tarav check --project [PATH]` only runs the checks. A
reported point of interest (POI) is a signal to investigate, not an automatic
instruction to repair or a reason to stop unrelated work. A check may report
missing context, stale generated output, or a problem that needs user judgment.
Before acting on any POI, open its context with the command the check report
prints (`tarav context --id <poi-id> --view reported-poi`).

### Work with Tarav data

Tarav Archive records artifacts and retains records about them. A recorded
artifact may live in the Archive or elsewhere. Tarav Diagram links, structures,
and annotates archived data for contextualization. Follow references back to
supporting data when a claim matters. An annotation, summary, or score does not
replace its source. Other workflows can keep their own storage while using
Tarav's primitives.

Capture user-touched data before curating it when loss is possible. Validation
judges state after a change and must not block writing. The user controls the
foreground task; do not interrupt development to demand Diagram enrichment.
When a check finds something suspicious, give the user or the responsible
agent enough context to decide what to do.

### Find the right surface

For project-specific work, use this file's Project System Prompt and the local
Project model. For Tarav-wide concepts and boundaries, read the Constitution
through `tarav-pkg`. For a design's rationale, inspect the relevant Wiki note
and its linked user turns; for current behavior, inspect the maintained code,
tests, and CLI. If those surfaces disagree, make the disagreement visible and
resolve it with the user when it affects the work.

This file is a Skillware product. Its source is under `.tarav/skillware/src/`.
Change the source, then produce and compile it with `tarav skw document` using
`--depot .tarav/skillware`. A Project may declare aliases for the main agents
file; those aliases are symlinks to the main file. Do not edit the compiled file
or an alias as the source of truth.
