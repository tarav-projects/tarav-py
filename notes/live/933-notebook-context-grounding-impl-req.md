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
Status: ready

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
