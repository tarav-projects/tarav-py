# Skillware analysis as Situation Chains — implementation request

<!-- tarav.sessions
3537df0a = claude-code:2bff854f-66a0-4e8c-8f96-9078af34c479 @3537df0a6015d884a94e9594478f971cb92e38df63776b87b5eea38741740d8a
-->

## Impl.Abstract

Status: design ready, 2026-10-19.
Knowledge.Surface: wiki.
Alignment.Mode: interactive.

Regroup the Skillware package analysis into Situation Chains (request 926,
`notes/live/926-situation-chains-impl-req.md`). Today one Check,
`Tarav.SKW.Check.Analysis`, receives every finding of a package and raises
them all; the User called such a Check ill-conditioned. After this request a
skill's Suite loads the package once, finds the situations (one per skill,
source, product, block, consumer file, link, dependency, publication) and runs
one atomic Check per situation. Each POI Type those chains raise belongs to
one chain and names its own Action Type.
<!-- tarav.breadcrumb 1f4a7d359b56 -->

Non-goals: the reading-graph checks (`l2/skw/reading_checks.py`: four
graph-wide checks and LinkProse) are a later request; the Project's agents
file (`l1/project/agents.py`, `AgentsMdProductCheck`) keeps running `lint()`
(the Project is left out); Model publications stay disconnected; the CLI
`tarav skw document lint` keeps its output; no positive-result POI.

## Design

### Current behavior (inspected)

- `SkwSkill._all_checks()` (`l2/skw/skills.py`) runs
  `_check_without_reading()`: it loads the documents and the loading graph,
  lints every source with `Document.lint(freshness=False)`, checks the
  marker, consumer files, their Markdown links and the dependencies, and
  returns `Finding`s. One `SkwAnalysisCheck` (`l2/skw/pois.py`) raises all of
  them through `SkwPOI.from_finding`. Then come the per-entry
  `GenerationContextResolutionCheck`s (a plain `Check`), the freshness
  `SituationCheck`s and the four reading checks. The suite is a plain keyed
  `CheckSuite` (`key=skill_id`).
- `documents()` is not cached; `_checks()` loads the package a second time.
- Situations from `from_finding` are `{"subject": {skill, path?, block?,
  target?, delivery?}}`. Defects found: `OutputNotDeployed`,
  `MissingDependency` and `ProductDrift` situations hold absolute paths
  (machine-local identity); a link finding keeps the link in `detail`, outside
  the situation, so two bad links of one file are one POI.
- On tarav-md: 262 checks, 68 POIs, among them 6 `OutputChanged` from the
  analysis check and 56 `StaleContext` (`tarav check --project tarav-md`).

### Decisions (User, request 926 discussion)

- A Check is atomic; the caller creates the situation and passes it. A Check
  that reads a whole package and finds many problems is ill-conditioned.
  <!-- tarav.breadcrumb 573dfd3948da -->
- A Suite knows how to run Checks; Suites nest and have names.
  <!-- tarav.breadcrumb 568a75be1dd3 -->
- External tools: run natively, keep the report, find situations in it
  (the Gitleaks template); here the "native" analysis is Skillware's own.
  <!-- tarav.breadcrumb df37f81dfc0c -->
- Every POI Type has its own Action Type; no generic one.
  <!-- tarav.breadcrumb b3950c3bba83 -->
- The User asked for the Skillware analysis chain next and earlier left open
  choices to the Agent.
  <!-- tarav.breadcrumb 914a53972684 -->

### Agent decisions

- **The analysis stays native, split per subject.** `Document.lint()` keeps
  its result but is composed of per-subject parts in l1
  (`block_findings(label)`, `source_findings()`, the product reading); each
  chain's Check calls the part for its one subject and raises POIs with
  exactly its situation. No second implementation of a rule.
- **Shared loading is a resource**, as `GitleaksHistory` is: `SkillLoad`
  loads documents and graph once, keeps the error if loading fails; the
  Loading Check reads it. The suite reuses it for the reading checks too.
- **Situations stay "the place"** (`{"subject": {...}}`), with paths relative
  to the skill folder (product, consumer file, dependency as declared) or to
  the depot (source). The link chain adds the link as `target`.
  `ProductDrift` keeps what it compares, now
  `{"subject": {skill, path: product}, "actual", "expected"}`; the Suite reads
  both texts and the Check compares (the freshness pattern).
- **Action Types by convention, declared explicitly.** Every `SkwPOI` Type
  names `<its name>.Resolution` (`SkwPOI.__init_subclass__`); l2/skw declares
  each Action Type with its own UUID in one table and the runtime registers
  them. StaleContext and StaleGeneration keep their `BlessableResolution`
  classes. Reading POIs get theirs too, although outside chains.
- **Identities change**: delete the affected action records (as in 925/926).

### Alternatives considered

- One Check per finding (literal Gitleaks): the Check would only re-raise
  what the analysis already decided. Per subject the Check runs the rule.
- Putting `ProductDrift` in the document chain: its situation holds hashes,
  which would make every document POI change identity with the product text.

### Known gap

The agents-file check raises chain POI Types (OutputChanged, ProductDrift…)
outside their chain; logged for the request that brings the Project in.

## Impl.Req.Wiki

Product project: tarav-py. Wiki: `notes/wiki/` (this repository). Relevant:
`notes/wiki/situation-chains.md`; daily `notes/wiki/daily/2026-10-19.md`.
Supporting turns: session alias 3537df0a, prefixes above. Capture: pending.

## Execution.Plan

Data shape (l2/skw/chains.py, new; chains are `SituationChain`s):

| Chain | Situation subject | POI Types |
|---|---|---|
| SkillMarker | skill | SkillMarkerMissing, SkillMarkerMismatch |
| SkillLoading | skill | InvalidLoadingModel |
| Source | skill, path=source | InvalidSource, SourceUncompiled, LoadingDeclarationStale, LoadingRenderError |
| Product | skill, path=product | DuplicateOutput, OutputNotDeployed, ProductUnavailable |
| ProductDrift | skill, path=product (+actual, expected) | ProductDrift |
| Block | skill, path=source, block | MissingContent, OutputChanged, InvalidAnnotation, InvalidProducedOutput, StaleProducedOutput |
| ConsumerFile | skill, path=file | MissingConsumerFile |
| ConsumerLink | skill, path=file, target=link | UnbundledLink, UndeclaredConsumerLink, MissingLinkTarget |
| Dependency | skill, path=dependency | MissingDependency |
| Publication | skill, path=publication | PublicationDisconnected |
| ContextResolution | (as today, +declaration) | ContextUnresolvable |
| GenerationFreshness / ContextFreshness | (as today) | StaleGeneration / StaleContext |

`SkwSkillSuite(CheckSuite)`: named by the skill folder, keyed by skill id;
`produce()` yields the package chains, one nested `CheckSuite` per source
(named by it) with its Source, Block, freshness and context-resolution
Checks, then the reading checks. `SkwAnalysisCheck`, `_analysis_pois`,
`collect` and `_check_without_reading` are removed; `evaluate()` runs the
suite.

1. **Refactor — per-subject analysis in l1.** Split `Document.lint` /
   `SkillDocument.lint` into per-subject parts; `lint()` composes them.
   Check: `tests/test_skw_poi.py`, `tests/test_skills.py` unchanged and green.
   Status: pending.
2. **Feature — the chains and the Suite.** Add `l2/skw/chains.py`, move the
   freshness and context-resolution checks into it as chains, replace the
   analysis check by `SkwSkillSuite`. Check: new tests (one atomic Check per
   subject, identities `fingerprint([type, situation])`, relative paths, two
   bad links are two POIs, a chain's Check raises only its POIs), existing
   SKW tests adapted, default suite green. Status: pending.
3. **Feature — Action Types for every SkwPOI.** Convention in l1, table in
   l2, runtime registration; a test asserts each `SkwPOI` subclass's action
   resolves. Delete the affected records; `tarav status --project tarav-md`
   twice: same open counts, second run "nothing". Status: pending.
4. **Docs.** AGENTS.md (source) / ARCHITECTURE.md / Wiki. Status: pending.

Deviation triggers: a per-subject split that changes `lint()` output; a
reading check needing the package loaded differently; check count or time on
tarav-md growing past ~2× (report it).

## Impl.Log

- Design: inspected `l2/skw/pois.py`, `l2/skw/skills.py`,
  `l2/skw/reading_checks.py`, `l1/skw/document.py`, `l1/skw/loading.py`,
  `l1/skw/skills.py`, `l1/skw/pois.py`, `l1/project/agents.py`, the tests and
  the tarav-md check summary.
