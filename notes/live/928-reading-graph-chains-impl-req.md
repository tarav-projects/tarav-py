# Reading-graph checks as Situation Chains — implementation request

<!-- tarav.sessions
3537df0a = claude-code:2bff854f-66a0-4e8c-8f96-9078af34c479 @3537df0a6015d884a94e9594478f971cb92e38df63776b87b5eea38741740d8a
-->

## Impl.Abstract

Status: design ready, 2026-10-19.
Knowledge.Surface: wiki.
Alignment.Mode: interactive.

Regroup the Skillware reading-graph checks (`l2/skw/reading_checks.py`) into
Situation Chains, after the package analysis (request 927,
`notes/live/927-skillware-analysis-chains-impl-req.md`). Today four Checks
each read the whole reading graph and raise many POI Types. After this
request, `SkwSkillSuite` runs the reading analysis once and runs one atomic
Check per situation: the graph, each declared node, each declaration target,
each source block's binding, each requirement, each reading path of a
requirement, and each declared link with a prose part.
<!-- tarav.breadcrumb 2b506809a916 -->
<!-- tarav.breadcrumb f323f8a0b4e5 -->

Non-goals: the Project's agents file; the analysis algorithm itself
(`SkillReadingGraph.__init__`, `analyze()`); the positive-result POI.

## Design

### Current behavior (inspected)

- `reading_checks(graph)` builds `ReadingDeclarationsCheck`,
  `ReadingDependenciesCheck`, `ReadingCoverageCheck` (plain `Check`s sharing
  one `analyze()` result) and `LinkProseCheck`. The first three return
  `incomplete` when the analysis is incomplete.
- Situations: `{"subject": {skill, block: <Ship or node id>, target?,
  delivery?, path?: [Ship ids]}}`; `UndeclaredBlock` puts the source's
  **absolute path** in `block` and the label in `detail` (machine-local, and
  two undeclared blocks of one source are one POI). `MissingMarkdownLink`
  is `{skill, block, href}`, without `subject`.
- No reading POI is open on tarav-md (`tarav check --project tarav-md`: the
  four checks run twice, 0 POIs).

### Evidence and decisions

- The User chose this as the next request, from the options after 927.
  <!-- tarav.breadcrumb 5a3f56acca3b -->
- MissingContext keeps the reading path in its situation: the Wiki says
  "Checks should identify an unmet dependency and the path that misses it"
  (`tarav-md/notes/wiki/reader-context-path.md`, Breadcrumb 615c8a733f67).
  This answers the question the Agent raised after 927.
  <!-- tarav.breadcrumb be8454652ea1 -->
- Agent: the reading analysis is one traversal of the whole graph;
  reachability, cycles and paths cannot be decided per block. It is the
  native report, as Gitleaks' is: the Suite runs it once
  (`ReadingAnalysis`: graph, `analyze()` result, findings indexed by subject)
  and each Check reads its own subject's part. Where a rule is local (a
  source block's binding, a link's prose), the Check runs it itself.
- Agent: the `incomplete` status stays on Checks whose answer depends on the
  traversal (graph, node, requirement, path).

## Impl.Req.Wiki

Product project: tarav-py. Wikis: `notes/wiki/` (this repository;
`situation-chains.md`, daily `daily/2026-10-19.md`) and
`tarav-md/notes/wiki/reader-context-path.md` (read only). Capture: pending.

## Execution.Plan

Data shape (added to `l2/skw/chains.py`; `reading_checks.py` is removed):

| Chain | Situation subject | POI Types |
|---|---|---|
| ReadingGraph | skill | InvalidLoadingRoot, RootHasParent, LoadingAnalysisIncomplete |
| ReadingNode | skill, block | InvalidBlockReference, UnreachableBlock, AttachmentCycle, InclusionCycle |
| ReadingDeclaration | skill, block, target | InvalidParent, InvalidContextTarget |
| BlockBinding | skill, path=source, block=label | UndeclaredBlock |
| ReadingRequirement | skill, block, target, delivery | PathDependentContext |
| ReadingPath | skill, block, target, delivery, path | MissingContext |
| LinkProse | skill, block, target=href | MissingMarkdownLink |

1. **Refactor — per-link prose in l1.** `SkillReadingGraph.link_prose_findings(identity,
   link)` for one declared link; `prose_findings()` composes it. Check:
   SKW tests green. Status: done.
2. **Feature — the reading chains.** The seven chains, `ReadingAnalysis`,
   the Suite yields them; `reading_checks.py`, `MissingMarkdownLink.from_finding`
   go. Check: new tests (MissingContext situation with its path, two
   undeclared blocks are two situations with a relative source, the
   produced reading Checks of a package), LinkProse test adapted, default
   suite green; tarav-md: 0 reading POIs, status "nothing". Status: pending.
3. **Docs.** ARCHITECTURE `skw` row, AGENTS source sentence, Wiki. Status: pending.

Deviation triggers: a reading POI appearing or disappearing on tarav-md;
a check needing a second `analyze()`.

## Impl.Log

- Design: inspected `l1/skw/loading.py` (`SkillReadingGraph`, `analyze`,
  `prose_findings`), `l2/skw/reading_checks.py`, `l2/skw/chains.py`, the
  tests, and the reading Wiki note above.
- Execute: start checkpoint 30a006a (the note only).
- Slice 1 (refactor): `prose_href(identity, link)` and
  `link_prose_findings(identity, link)`; `prose_findings()` composes them.
  Check: SKW tests (test_skw_poi, test_skw_chains, test_skills,
  test_project_agents) passed, including the LinkProse test unchanged; ruff
  clean; loading.py audit clean after position refresh. No new Breadcrumb
  (a mechanical split).
