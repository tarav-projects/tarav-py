# Notebook grounding through Context

<!-- tarav.sessions
0f5bad01 = codex:01a15483-94e8-7fe0-86ad-ddd83e2bae52 @0f5bad0131260477b4cf3d712a95871496c3db92d67eaa7910243e312f7b552a
-->

## Impl.Abstract

Implement read-only Notebook grounding through Lines' Context contributions,
Context's existing SPARQL query engine, and a small `tarav notebook` CLI.
The companion skill request is [868](../../../tarav-md/notes/live/868-notebook-grounding-skill-impl-req.md).
Knowledge.Surface: wiki
Alignment.Mode: Interactive
Status: executing

Grounding finds Blocks relevant to the current conversation. Infer the Project,
start at its ModelBlock, and collect the complete Model subtree before querying.
The optional hint focuses the conversation-driven search. Preserve ancestor
context while allowing the agent to choose which payloads to read closely.
<!-- tarav.breadcrumb 47b758dccba8 -->
<!-- tarav.breadcrumb d8b5c2c265a4 -->

Lines must contribute triplets to Context; do not create a Notebook text-search
engine or separate query language. The User explicitly requested development
through the skill surface, ready for later interactive use.
<!-- tarav.breadcrumb 337e7353846e -->
<!-- tarav.breadcrumb aeb27f7d376b -->

No Notebook writes, new captured design data, persistent session View, lineage,
alignment engine, semantic ranking engine, or extension migration in this pass.

## Design

Data shape first: Lines own a small IRI vocabulary for text, authoring scope,
Block parent and containment. RDF ordinal membership predicates preserve mixed
content order in the graph. Class hooks retain the inherited rdf:type triple;
instance hooks contribute their direct facts through the current ObjectContext.

A cross-workflow NotebookContext service in l2 combines existing ProjectNotebook
selection, Notebook loading, and ContextExplorer. It opens every Block/Line in
the selected subtree and each ancestor with its direct Lines. Ancestor siblings
may be visible as relationship targets; their payloads are not collected.
The explorer remains focused at the selected Block. ContextExplorer.query
continues to be the only query execution engine.

Default selection is ModelBlock. Explicit branch selection permits Discussion,
Archive or the Project root; an explicit Block Ship selects a subtree under that
Project. Reads never create storage. Missing/ambiguous roots, branches, identities
or unsupported queries fail clearly. No automatic global broadening.

Identity integration: register a Notebook resolver with ContextQueryService so
known Block/Line Ships can open through `tarav context --id`. A runtime-local
external Context hook links an existing Project notebook to its Project without
provisioning it. Integrations live above Lines/Notebook/Project and do not make
lower layers import runtime composition.

CLI choices: `tarav notebook ls`, `read`, `query`, with inferred `--project`,
optional explicit `--branch`/`--block`, `--root` storage override, and `--json`.
`ls` returns a compact map of all selected Blocks and counts. `read` returns
ordered direct content and ancestor Lines. `query --sparql` accepts SELECT/ASK
through Context and returns literal values or identified object hints. Commands
rebuild an ephemeral graph for each call; no session repository is needed.

Inspected: l1/lines, l1/notebook, l1/context (construction, query and explorer),
l1/search, l2/project/notebook.py, l3/runtime.py, l3/context/commands.py and their
tests. Existing extension filtering is extension-owned and remains for a later
consumer migration. Subtract before adding: no old Ground/Model code is revived.

## Impl.Req.Wiki

Product: tarav-py. Durable design owner: tarav-md/notes/wiki/.
Relevant Notes: line-notebook.md, lines-workflow.md and context-graph.md.
The older Context view-based sections are historical; current source uses
ObjectContext hooks and a cumulative RDF ContextExplorer. Capture the accepted
default scope and query ownership in the Notebook topic and daily Note.

## Execution.Plan

1. Feature: Lines Context hooks and subtree collection. Check literal graph
   facts, RDF membership order, full selected subtree, ancestor context, sibling
   payload exclusion, SELECT/ASK, focus and ordinary Context navigation.
2. Feature: Project/Notebook integration, identity resolution and CLI. Check
   real subprocess discovery, default Model scope, explicit branches, ordered
   reads, arbitrary SELECT/ASK, identity recovery, malformed/mutating queries,
   empty Model and missing Notebook with no data writes. Run architecture tests,
   reinstall the installed tool and exercise it against the live Project.
3. Dependency handoff: execute tarav-md request 868; then run broader Project
   checks and close scoped product/Wiki evidence commits.

## Impl.Log

- Todo: capture/cold-reload; start checkpoints; implement/verify slice 1;
  implement/verify slice 2; reinstall; implement skill; capture Wiki; close.
- Existing Neighborhood changes in runtime, pyproject, architecture and tests
  will be checkpointed as found. They are independent of this vocabulary.
- Known storage behavior: Notebook.load resolves a connected component, which
  can include sibling objects in memory. This request bounds collected graph
  contributions and presented content; it does not claim selective disk I/O.

+- Cold-reloaded requests 933 and 868 before product edits; no design-reality
+  mismatch found. Baseline: 39 relevant Lines/Notebook/Context tests passed.
+- Start checkpoints: external 14160e9dafe73c00d892e556f99e0285bfd9ddf0;
+  request 11141d8c47a9ada8bfe3e6c948f43155e79d4119. Markdown counterpart
+  checkpoints: external 207d6140568f61e838a0d1474817ddcbff1c8234 and request
+  290c03dc49036144a51d51676f914a8404ade525.
+
+- Slice 1 verified: 29 Lines/Context tests passed and focused Ruff passed.
+  Type identity assertions compare Ships; class projection objects are not
+  promised to be the same Python allocation. Context collection remains
+  storage-independent and uses the existing Explorer query/follow methods.
+- Slice 1 inline capture submitted five surfaces with six new Breadcrumbs;
+  audits resolved them. Older label positions on the two edited Lines files
+  were refreshed. No capture registration is pending.
+
+- Slice 1 commit: 88ca4dd9da9978b7663f08a3da0b4b35fd31e636.
+- Slice 2 verified: 84 focused/architecture tests passed before the harness
+  regression addition; 36 focused tests passed afterwards, including five
+  Notebook integration tests with actual CLI subprocesses. Ruff passed.
+- Runtime registration initially attempted to register two non-Record service
+  Types in the Record registry; removed that incorrect registration rather than
+  inventing persistence. Runtime composes their resolver/hook instances instead.
+- Architecture graph check now distinguishes l1 Notebook storage from its
+  higher-level integration, following the existing foundation convention.
+  Import-order and no-upward-layer checks still pass. The generic Context run
+  assertion includes the newly installed Notebook hook's observed no-op run.
+- Real-Project verification reproduced a global interpreter missing the custom
+  harness Type. Notebook commands now use the ordinary Project harness launcher,
+  preserving the Project Type and environment. A regression fixture has a Type
+  installed only in its own interpreter; a direct caller fails to import it,
+  while the Notebook command succeeds. No fallback Type or implicit provisioning.
+- Installed CLI reinstalled with uv tool install --reinstall --editable .;
+  ls/query on the live umbrella Project succeeded. Its current Model has only
+  the seed explanatory Line: one Block and 19 collected triplets including
+  ancestor contributions. No current design content was fabricated or imported.
+- Slice 2 capture: l2 Notebook integration, CLI, integration tests, architecture
+  test and architecture document submitted eight labels. Existing labels in
+  runtime, Context command help and tests were audited/refreshed. AGENTS was
+  changed at its SKW source and produced/compiled; JSON has no native inline
+  convention. The header-only CLI module has no separate semantic attachment.
+- Broader --all run completed 1,204 checks with zero incomplete, zero pytest
+  POIs. It observed in-flight skill routing freshness changes; the skill's final
+  generation recording and closing routine status follow in request 868.
+