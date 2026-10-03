# 852 — Workspaces: JSON manifest, worktrees, and Project integration

<!-- tarav.sessions
f5845518 = claude-code:4ee3b84e-14fa-4aa9-9c6f-8d139954fe18 @f5845518e808c6cf0496f867fc656fdad9063980a184f7c3f15c54adf8fcb31f
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Design only.
Status: ready; open questions below are not blocking.

Revisit the August `Run.Workspace` design and make it more powerful. A
workspace becomes a Tarav entity described by a JSON manifest that states its
initial configuration precisely: copied documents, symlinks, Git worktrees,
and new documents, each with its place in the workspace tree. Workspaces live
in `~/Documents/tarav/workspaces/`. The Git workflow gains worktree
operations, the workspace workflow uses them, and the Project workflow opens
an interface to create and list workspaces for a project.
<!-- tarav.breadcrumb 43e4f013b52406c442653d418d9f7705a41e25b4a6e58c8afd316a585419c46e -->
<!-- tarav.breadcrumb 2b53f5c83a365421ac704d7e19f544e8303c269628a9f9ec8c1212d6f57e6498 -->

Non-goals: the self-improvement loop itself; merge-back tooling; running a
candidate Tarav from a workspace (environment and data-root isolation);
Breadcrumb position migration; duplicating Git machinery or touching Git
configuration.

## Design narrative

### Why

The User wants a basic self-improvement system in Tarav and sees isolated
working copies as one of its foundations: Tarav provides Git workflows tied to
a project, Agents create working copies outside the project under the Tarav
folder in Documents, and work there.
<!-- tarav.breadcrumb 71460fe8a6e0bf937ba747061503dfbe05785583644e0d216b216122d6ebbbf9 -->

A bare worktree depot is not enough because a project can be an umbrella
folder holding several repositories. The User moved to a larger unit, the
workspace: a folder that holds worktrees and any other data, with a
description of the initial condition that created it. Agents work there and
commit to the repositories. The complex work is moved up to the Agent and
happens only at merge-back: adding new Breadcrumb locations and any other
migration. Merging is allowed to cost computation.
<!-- tarav.breadcrumb d28a062fa3680e64bf64a9a95d2fd6e2137830b9bf33614864d66d8c6a8b6203 -->

Workspaces are kept for a while after merging, so migration leftovers found
later can be checked against them. They are removed only when space is needed
or during a garbage collection.
<!-- tarav.breadcrumb a374be907e14f814693994fc840785d0d346119cf71dad7f8f8574d6e4fd00aa -->

### Git is a caller interface

Tarav does not duplicate Git machinery. It models the minimum the workflows
need, and every Git operation is a call to the user's `git` as configured in
the folder. Tarav does not touch independent configuration.
<!-- tarav.breadcrumb 8128ce45e4680f4a681b406403d89239f6485d2154a55735c4bb29012fed18e4 -->

Inspected: `GitRepository` in `src/tarav/l1/git/repository.py` already
calls `git -C <repo>` through subprocess and has no worktree operations.

### Manifest and setup record

The manifest is JSON, a proper Tarav object with identity, not a section of
`AGENTS.md`. It describes the initial configuration precisely enough to set
the workspace up, reset it, or clone it into another workspace. It also gives
the tree structure: where each copied file and each worktree goes.
<!-- tarav.breadcrumb 843a06c68a6d4467808d08f81d059968ce712251bced14b092fc123def81a3e5 -->

Four entry primitives:

- copied document; when its source has no repository behind it, the hash is
  stored so a later copy can show a mismatch with the original version;
- symlink;
- worktree of a repository, defined precisely (repository, commit, and what
  else defines the worktree), so that checks can verify it exists;
- new document.
<!-- tarav.breadcrumb d69c55fa2dfad7bc5154eb6c5edf87ace1ceb36c7c8aa864b86571c9bcf42fc1 -->
<!-- tarav.breadcrumb eebe42647b200bc682642df39d0574259654362f8046060ece23077c1bc0b7ff -->

A symlink is used when the workspace should react to changes of the file. Its
hash at creation is still stored, only as information for whoever wants to
know what changed.
<!-- tarav.breadcrumb a68e96f96a0915f1fdd90d44171bfc973a59b56c4331d6878670052bed6475a6 -->

The description is split in two files. The manifest says how a reset creates
the workspace. A second file describes the last reset: the hashes and other
initial conditions actually found. This is a minimal provenance
infrastructure.
<!-- tarav.breadcrumb 32f832ae4780b2ce5d8a94e30d74b9b607cda66ee5290c48ebf05d1e3ecaf90a -->

Agent proposal: the manifest is a recipe without observed state, so a
worktree entry may name a branch and the setup record pins the commit it
resolved to. Setup, reset, and "new workspace from this manifest" are the
same operation applied to a folder. Reset in place refuses when a worktree
holds uncommitted or unmerged work and reports it as a POI. Starting content
of a new document lives in a seed folder beside the manifest.

### Status and documentation

A workspace may carry documentation in `AGENTS.md`. A small vocabulary of
states, such as active or closed, gives basic filtering. Nothing more complex
is wanted.
<!-- tarav.breadcrumb 27a60ffd4e85fe41473d1d1d868d4816ec4c6ea13a421cdcbabbf14994e977d0 -->

Agent proposal: the JSON manifest owns status; keep the existing values
`open`, `harvested`, `abandoned` and the `extracted` field. `AGENTS.md`
becomes prose that points to the manifest.

### Worktrees, checks, and breathing room

Real Git worktrees are required, so that a project or a set of projects can
be worked on independently. The workspace must have checks, for example that
its worktrees actually exist.
<!-- tarav.breadcrumb 1b1cecddf61c816382f096e88fb924c53af25c3d14f929ea36b14b4f179307a4 -->

The August rule that nothing stable may reference a path inside a workspace
no longer holds as a prohibition. Stable-to-stable references remain a goal.
A reference into a workspace is allowed and raises a reminder POI: link it
properly when you finish. Tarav must breathe and stay open; it cannot be a
prison that adds friction to development.
<!-- tarav.breadcrumb 8217932fae1d18f5fb07b93f6a09129dacf06ede9959024a39a7ea5b652fab87 -->

Agent proposal, checks through the existing Checks workflow, each a POI and
none blocking: a worktree entry missing on disk or not registered in its
repository; a worktree on a different branch than the manifest states; a
copied document whose source no longer matches the recorded hash; a symlink
that no longer resolves. Removing a workspace removes its worktrees through
Git so the repository's registration is cleaned.

### Organization inside Tarav

The discussion is about how the workflows are organized in the library; the
CLI is a consumer and may have its own commands. The workspace workflow uses
the Git workflow for everything Git-concerned. It has its own way to visit and
list workspaces. Project access is an interface the Project workflow opens
onto the workspace workflow, an integration between two independent
workflows, for organization: a project can create workspaces and be aware of
those created under its link.
<!-- tarav.breadcrumb 10c76e9c3462aa5f8a9d929ae79ff100887dc2e59545e7bd3d9c180e7e7b0a96 -->
<!-- tarav.breadcrumb b6a478f9f103b32f4feff02f9cd5e2e0513cff05efc2d97b46e7fad5b2bbfd47 -->

An earlier idea in the same discussion was a worktree depot with one folder
per project, organized with core Tarav objects and exposed through a depot
class inherited from the standard project base type.
<!-- tarav.breadcrumb e969942f62105ab8fc7279a7fe6a544e784994b106cd5a85257f14bb9199e5f4 -->

Agent proposal:

- `tarav.l1.git`: `GitRepository` gains worktree add, list, remove, prune.
- `tarav.l1.workspaces`: `Workspace` entity, `WorkspaceManifest`,
  `WorkspaceSetupRecord`, the four entry types, a depot (create, open, list,
  filter by status or project, reset, remove), and the checks.
- `tarav.l2.project`: create a workspace for a project and list a project's
  workspaces. For an umbrella project, discover nested repositories and write
  one worktree entry each in the same relative layout. The project stores
  nothing; listing filters the depot by an optional project reference in the
  manifest. The depot folder is flat, since a workspace may involve several
  projects or none.

### Current implementation (inspected)

`src/tarav/l1/workspaces/` (547 lines) implements `Run.Workspace`: root
`~/.tarav/workspaces/<date>-<slug>/`, a manifest parsed from an
`AGENTS.md` section (kind, created, status, extracted), one Git repository
per workspace, a refusal to create one inside a worktree, and the commands
`tarav workspace guide|init|list|show|sweep`. No workspace exists on this
machine, so there is nothing to migrate.

### Open questions

1. Default branch name for a worktree entry; the Agent suggests deriving it
   from the workspace label.
2. Whether `tarav workspace guide` and its unlock token survive the revisit.

## Impl.Req.Wiki

Product project: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Capture of
this design: `workspaces.md`. Related: `projects.md`, `checks-workflow.md`,
`poi-system.md`. Supporting chat: session `f5845518` above. The August
design is anchored in the source as `^c20260809-87u`; its chat was not
re-read for this request.

## Execution.Plan

1. Scoped start evidence checkpoint.
2. Git: worktree operations on `GitRepository`, tested against temporary
   repositories.
3. Workspaces: entity, manifest, setup record, and the four entry types;
   setup and reset; depot in `~/Documents/tarav/workspaces/`. Tests: each
   entry kind sets up; the record pins hashes and commits; reset refuses on
   unmerged work; a second workspace from the same manifest matches.
4. Checks and their POIs, including the reminder for references into a
   workspace where mechanically detectable. Tests for each check.
5. Project integration, tested on an umbrella fixture with two nested
   repositories.
6. CLI: adapt `tarav workspace` to the new library; rewrite `GUIDE.md`.
7. Architecture tests and `ARCHITECTURE.md`; Inlined Capture; Wiki capture;
   completion commit.

Acceptance: a workspace for `taravangian-project` can be created with one
worktree per nested repository; its checks pass; deleting a worktree folder by
hand raises a POI; removal through the depot leaves no stale registration.

## Impl.Log

- 2026-10-03 Design: note written from the discussion in session `f5845518`.
  Inspected `l1/workspaces/*`, `l1/git/repository.py`, `l1/project/base.py`.
  The User chose worktrees over the Agent's recommendation of local clones.
  No product code changed.
