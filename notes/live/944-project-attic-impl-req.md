# Project Attics

<!-- tarav.sessions
96bd11c6 = codex:01a16464-7389-73a0-bebe-0189d9c953c3 @96bd11c6715ef7012dd7ebf6f826d3e465aae80853b9ba89380eb6614772f9f3
-->

## Impl.Abstract

Develop Project-local Attics: default `<project>/_ATTIC`, an optional configured
folder, and metadata checks included in Project checks. Adopt this umbrella's
retired `_DEPRECATED` trees into a local Attic, preserving their contents and
Git histories. Status: designed, ready for execution.
<!-- tarav.breadcrumb a230a9c8b4dc -->

Knowledge.Surface: wiki. Alignment.Mode: Interactive.

## Design

The User wants the same conservation workflow at Project scope, for convenience
when retired material should remain beside the active Project. Local and general
Attics have identical semantics: contents stay opaque, metadata is self-declared,
and live systems must not consume deposits. `_ATTIC` is the default; a Project
may select another folder. Missing unused Attics remain absent.
<!-- tarav.breadcrumb b1eff966cc0e -->
<!-- tarav.breadcrumb 31f56f161639 -->

Implementation observation: `l1.attic.AtticWorkflow.open(root)` already supports
explicit depot roots, and `AtticSuite` checks only immediate deposit manifests.
Reuse it unchanged. The featured `l2.project.Project` composes integrations;
minimal `l1.project.TaravProject` should remain independent of Attic. RootProject
already aggregates its own and its children's checks; retain that mechanism.

Data shape first: `ProjectAtticConfig` is a strict workflow config model with
`path: str = "_ATTIC"`, stored under `attic` in `.tarav/config.json`. Use the
existing `ProjectConfig` section registry and file checks, rather than adding
a competing config reader or fields to the Project identity Record. Paths are
nonblank local relative folder paths without parent traversal; absolute paths
and symlinks escaping the Project are refused. The selected root is metadata
about the Project's Attic, not a relocated Project identity.

Expose `Project.attic()` returning the existing `Attic` handler. Discovery does
not create folders. Project checks lazily resolve it, so invalid configuration
is reported by existing file checks and does not prevent unrelated suites from
running. The Attic suite keeps its established Type and root-based identity.
Status ownership remains the containing Project's existing action machinery.

Subtract before adding: remove the obsolete `_DEPRECATED` root by conserving
its nine retired trees together under `_ATTIC/deposits/<timestamp>-retired-projects/material/`.
Keep repository internals and uncommitted state untouched; verify before/after
hashes as the migration operator, outside Attic metadata checks. Update maintained
routing and historical locators. Historical narratives need not be rewritten.

Non-goals: CLI deposit automation, automatic nearest-Project destination choice,
recursive inspection, normalization, deduplication, Archive registration, or
turning deposited Projects into active children. The general Attic remains the
System Project's independent additional suite. No new Workflow or Type identity
is needed for the local Attic itself.

## Impl.Req.Wiki

Product: tarav-py. Wiki owner: tarav-md, `notes/wiki/attic.md` and today's daily
Note. Documentation request: [872](../../../tarav-md/notes/live/872-project-attic-guidance-impl-req.md).
Evidence: exact session and User Turns declared above. Capture pending.

## Execution.Plan

1. Feature: add Project Attic config, access and lazy check integration; register
   its config section. Verify public access, absent folders, override paths,
   invalid config isolation, metadata opacity, child aggregation and action
   closure with focused tests; run existing Attic/Project/architecture tests.
2. Feature/adoption: preserve `_DEPRECATED` in the local Attic; update routing
   sources and catalog locators, compile generated guidance, update architecture
   and operator guidance through request 872. Verify hashes, local metadata,
   installed behavior and Project checks. Status: pending.
3. Closure: capture implementation surfaces and Wiki, run full Project checks,
   commit verified work and report any unrelated POIs or evidence gaps.

Dependencies: configuration integration precedes local adoption. Stop for
alignment if a live dependency on retired contents is found or current mechanics
require a materially different design. Pure source-path references in historical
notes are recovery hints, not runtime dependencies.

## Impl.Log

- Start checkpoints: root `1e061208`, Python `7fc73f4`, Markdown `b35d0ab`.
  Pre-existing unrelated work was checkpointed as found under the invoked skill.
- Design inspected: Attic model/checks, featured Project and RootProject suites,
  System Project, Project config registration/file checks, architecture tests,
  and Wiki Attic Note. Baseline: no Project Attic capability exists.
