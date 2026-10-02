# 838 — SKW reference resolution checks

## Impl.Abstract

Knowledge.Surface: wiki
Alignment.Mode: Interactive
Status: ready for implementation; exact conversational Breadcrumb capture pending.

Add explicit SKW Checks that surface broken declared references as CheckPOIs.
Reference resolvability is independently assessable: it must not disappear when
freshness evaluation cannot construct its inputs or has no recorded baseline.
This request changes checking/reporting, not generation or retained content.

Non-goals: automatic repair, mandatory successful validation before mutation,
new check engines, broad arbitrary-object crawling, uv/environment changes,
or changes to blessing policy. This pass creates a request, not product code.

## Design narrative

### User direction and evidence

During the read-only review of request 836, the user requested a Check to
evaluate whether connections are resolvable and raise a POI for a broken
reference. The subsequent clarification was explicit: a broken reference
should produce the POI; successful resolution needs no success POI. The user
then requested this implementation request through Tarav Hugentics Design.

Visible voice excerpts, retained here for a self-contained handoff:

> deve esister un check per valutare que tutti la connessione sono ... resolvable

> deve lanciare un POI ... un broken riferimento

> Utiliza el tarah agentic implementation design for making an implementation request

These are conversation excerpts, not verified Chatlas Turn attachments. The
current session locator is `codex:01a0d86c-9538-7be1-af96-014cd4203d61`.
Do not fabricate Turn hashes or Breadcrumb identities to fill this gap.

### Deferred User-Turn lookup — user-authorized fallback

The user explicitly requested retaining enough evidence here to locate the
supporting User Turns later, without registering Breadcrumbs in this pass.
The following are verbatim `input` payloads visible in realtime delegations,
not normalized Chatlas records. Preserve transcription errors when searching;
the retained provider message may wrap these payloads in XML and include a
repeated `transcript_delta`. Resolve the actual user message, not an assistant
paraphrase or a later repeated transcript excerpt.

Lookup scope: the Codex session identified above; neutral identity recorded
earlier in this session:
`6734aba0b9204f614baf3987604865fa85146495877841244ad7fe1efce4104b`.
Recording date: 2026-10-02 (not an asserted source-turn timestamp).
Sequence: read-only 836 review → uv discussion → unresolved-reference concern
→ Check/POI clarification → request 838 → archive permissions → this fallback.

1. Requested reference-resolution Check:

   > Okay, no, questo deve essere ehm... risolto eh... con un check... se- de-debe esister un check per valutare que tutti la connessione sono, eh... diciamo... resolvable, eh... debe la- rais lanciare un poi

2. Clarified the failure condition, after incomplete “caso de” turns:

   > No no, in caso che- que... deve lanciare un POI in caso de que sia... diciamo... un probl- eh... un broken riferimento

3. Requested a design handoff, not implementation:

   > Mm-hmm. Okay, uh... tu puoi fare una... implementation request, uh... di questo... diciamo... risol

4. Selected the skill route:

   > , Utiliza el tarah agentic implementation design for making an implementation request

5. Authorized this temporary evidence representation after the permissions
   discussion:

   > Okay... Questo... Ok, va bene. Ehm... tsk... Registra en la implementation request ehm... non utilizzando il breadcrumbs ma sufficiente eh... diciamo... evidenze per trovare el user turn... dopo

Recovery: query this exact session through Chatlas, locate these phrases in
the indicated order, inspect adjacent turns, and attach the resolved user
turns beside the corresponding design passages. No exact timestamps, turn
hashes, or Breadcrumb IDs have been established for these messages yet.
This fallback preserves findability; it does not claim completed capture.

#### Emergency evidence map

The numbered inputs above are local lookup labels, not Tarav Breadcrumb IDs.
Their relationship to this request is explicit:

| Content in this request | Supporting user interaction |
| --- | --- |
| A Check evaluates reference resolvability and surfaces a POI | Input 1 |
| A broken reference is the condition for the requested POI | Input 2, clarifying input 1 |
| Produce an implementation request through Hugentics Design | Inputs 3–4 |
| Preserve evidence locally while canonical Breadcrumb registration is unavailable | Input 5 and the clarification quoted below |

The user further clarified the non-optional requirement to locate the relevant
interaction, allowing a purpose-built emergency note when Breadcrumbs are
unavailable. Verbatim realtime input, following input 5 and the discussion of
timestamps:

> Dico, lo che noi non possiamo eh... diciamo eh... lasciare fuori è che noi dobbiamo documentare dove è l’usuario ha fatto, diciamo, eh... de l’interagione rilevante per il contenuto che noi stiamo sviluppando, questo deve essere chiaro, si el breadcrumb non è available... tu lo puoi fare come una nota fatta apposta per questo emergenza, diciamo

Coverage boundaries: the baseline-independent integration, proposed enumeration
scope, snapshot reuse, and detailed test matrix below are agent-proposed
implementation consequences, not separately approved user interface decisions.
Current-code observations cite source paths rather than treating user intent
as proof of implementation behavior. Preserve these distinctions when replacing
this emergency evidence map with canonical attachments.

### Current implementation observations

Request [836](836-typed-annotated-skw-blocks-impl-req.md) moved SKW to neutral
blocks with typed annotations and a local objects index.

- `src/tarav/l2/skw/skills.py`: `_check_without_reading()` invokes
  `document.lint(freshness=False)`; `evaluate()` and `check()` construct checks
  with `skip_unresolved_freshness=True`.
- `src/tarav/l2/skw/pois.py`: `freshness_checks()` catches resolution errors
  and skips checks in that mode. Context freshness iterates recorded context
  baselines, not every current declaration.
- The comment in `evaluate()` says preliminary document analysis already
  retains resolution failures. That assumption must be revalidated against
  the new structural-only lint path.
- A `ContextUnresolvable` POI already exists; inspect its contract before
  adding another overlapping type.

These observations establish a missing reporting path to investigate; this
Design pass has not independently reproduced the end-to-end defect. The prior
review ran the configured suite successfully (150 tests), which does not
establish coverage of missing-reference cases.

### Proposed bounded contract

Provide an independently runnable SKW-owned Check through the existing Checks
workflow and expose it through the existing iterable `SkwSkill.checks`.
Reuse CheckResult and CheckPOI mechanics. Consumers emit resulting POIs through
the existing collector; do not add a parallel finding model or confuse POI
emission with raising a Python exception.

Enumerate declared reference occurrences using the actual typed SKW contracts:
generation-context references, local ObjectIndexReference targets, and existing
typed loading/reading targets. Reuse existing checks where they already cover
a category. Document exact coverage; do not interpret arbitrary strings or
Markdown links as new typed graph edges, nor recursively crawl arbitrary
referenced content.

For each supported occurrence, successful resolution produces no failure POI.
A resolution failure produces a POI identifying the owning document/block,
annotation or index coordinate, declared target, and available failure reason.
An unavailable or permission-denied target should be reported accurately as
unresolvable in this environment, not asserted to be permanently deleted.
Use the existing explicit situation/identity conventions, not hidden hashing
heuristics or unstable timestamps.

Reference checking does not require a generation baseline. A failure must not
abort evaluation of unrelated valid references or suppress unrelated Checks.
If a prerequisite cannot resolve, dependent freshness is not verified; never
report it as fresh merely because its Check was skipped. Keep independently
resolvable generation/context freshness checks working. Do not introduce a
new universal status framework solely for this integration.

Prefer one resolution observation per evaluation that can feed both the
resolution result and dependent freshness snapshots. If SituationCheck is
used, collect observations before execution and preserve its snapshot-only
contract. This is an implementation proposal, not a requirement for all Checks
to become SituationChecks.

Keep package evaluation, existing CLI reporting, and standalone targeted checks
consistent. Avoid duplicate POIs for the same occurrence from overlapping
structural and resolution paths. Broken inputs must remain visible even when
another malformed input prevents full loading-model construction; retain
existing structural diagnostics rather than assuming all objects can load.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`.
Relevant existing context:

- `tarav-md/notes/wiki/checks-workflow.md`: Check, result POI provider,
  targeted execution, and SituationCheck contracts.
- `tarav-md/notes/wiki/poi-system.md`: POI semantics and identity.
- `tarav-md/notes/wiki/reader-context-path.md`: declared reading relationships.

Capture status: pending. Canonical Chatlas refresh/Breadcrumb retention was
blocked earlier in this session by permissions outside the writable workspace.
Do not redirect canonical evidence into an unofficial depot. Complete exact
Turn grounding, the bounded Wiki daily capture, and evidence-backed closure
when that route is writable. No new Wiki capture or commit is claimed here.

## Execution.Plan

1. Reproduce missing external context through public package evaluation;
   compare standalone document lint. Include a block without any baseline.
2. Inventory existing typed reference resolvers and Checks. Select the smallest
   missing resolution Check/POI integration, reusing existing coverage.
3. Implement independent resolution reporting and integrate `.checks`,
   `evaluate()`, `check()`, and current CLI reporting without silent skips.
4. Verify deterministic tests: all references resolve; missing external file;
   missing local index target; resolver failure; no baseline; mixed valid and
   broken references; relevant loading/reading targets; no duplicate reports.
5. Verify unrelated freshness still runs; unresolved freshness is not presented
   as verified; repaired references stop producing broken-reference POIs.
   Use fake resolvers for permission/remote failures, not live services.
6. Run focused SKW/Checks tests, then configured suite and lint. Confirm no
   check repairs sources, refreshes baselines, or changes generated content.
7. Capture supported Product.Surface Breadcrumbs and Wiki updates and complete
   scoped workflow closure; preserve unrelated worktree edits.

Acceptance: a broken supported reference is visible as an inspectable CheckPOI
through normal package reporting and a targeted Check, independently of
freshness baseline presence. Successful resolution produces no failure POI.

## Impl.Log

- User explicitly authorized deferred Breadcrumb registration with verbatim
  voice inputs and session/sequence locators retained in this request. Added
  the lookup section above; no canonical evidence-store writes attempted.

- 2026-10-02: Created this Design handoff from the user's clarification during
  review of 836. Inspected package check composition and freshness construction.
- No implementation changes or new execution tests performed in this pass.
- Exact Turn/Breadcrumb capture, Wiki daily integration, and evidence commit
  remain pending due to the session's canonical evidence-store permission gap.
