# 903 — A Skillware finding names its POI Type — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Develop.
Status: implemented, with point 6 open.

A Skillware POI has two names: its Type, such as
`Tarav.SKW.POI.UnreachableBlock`, and a lowercase string, such as
`unreachable-block`. The string is what the analysis in layer 1 writes,
because it cannot name a Type that lives in layer 2; a table then
translates. This request removes the string.

1. The Skillware POI Types move to `tarav.l1.skw`, beside the analysis that
   detects them. The checks that run the analysis stay in layer 2.
2. The analysis reports with the Type itself. A finding holds the class.
3. The table `CLASSES` and the kind strings are deleted. Code that compared
   a string compares the Type.
4. The message of each Type is a literal sentence; none starts with a kind.
5. The JSON of the Skillware commands shows the Type name where it showed
   the kind.
6. The Agents file check loses its own table in the same way.

Non-goals: what each Skillware Type keeps in its situation (the package
snapshot stays, except for product drift); raising POIs directly from the
analysis with no finding in between.

## Design narrative

### User decisions

The user saw both names on one status row and asked what the lowercase one
is.
<!-- tarav.breadcrumb 4f80c0450291887bf1bf429f978bae6f837044418792258f54692944541a3be9 -->

The agent explained the table and offered two levels of cleanup: the surface
only, or the root. The user answered that this is stupid and to eliminate
it.
<!-- tarav.breadcrumb 6793a754d44d1b4794a4f14de7e8524a842d88c5b3868f7cacab9aacd8b101d0 -->

The agent proposed the six points above and asked for approval. The user
invoked the Develop route with those six points as its input.
<!-- tarav.breadcrumb 5696878ccaa0595a4b02ff41cfd1aabb7b0003069b9b9c79c0c72abea8cdad11 -->

Earlier the same day the user had fixed two rules that this request has to
keep: a Tarav object becomes data only through the Record system, and no
code decides anything from the details of a POI.
<!-- tarav.breadcrumb b5b7f07f31d3c3fdf76981af949f7cce3dbf00c943bc6a2da47a2a29b502ee23 -->
<!-- tarav.breadcrumb c6b6c5b0f988281163fd8c2a83817efac3ff318b37d10e1409549da07992782b -->

### Current behavior (inspected)

- `Document.lint()`, the produced blocks and the loading model
  (`l1/skw/document.py`, `skills.py`, `loading.py`) append dictionaries
  with a `kind`, and the reading graph appends dictionaries with a `code`.
- `l2/skw/skills.py` adds package findings the same way and filters by
  comparing strings.
- `l2/skw/pois.py` holds 39 POI Types, the checks, and `CLASSES`, which
  maps each string to a Type. `l2/skw/reading_checks.py` selects
  diagnostics by sets of strings.
- A Skillware message is built from the finding and starts with the kind.
  28 of the Types have a placeholder as their description.
- `SkwSkill.check()` reads `poi.details["finding"]` back out of POIs: code
  that depends on details.
- Three strings have no Type and would raise if they occurred:
  `missing-content`, `invalid-produced-output` and `stale-produced-output`
  in a package, and `model-publication-disconnected`. The Agents file check
  has Types of its own for the first two.
- `ModelPublication.render()` reads `result.findings` of a Diagram render
  result, which has no such attribute: that path cannot run today.
- The Agents file check (`l1/project/agents.py`) has twelve Types of its
  own, one per lint kind, chosen through a second table.

### Proposals of the agent

**Finding.** `tarav.l1.skw.pois.Finding(poi, **data)`: the POI Type that
states what was found, and the place and observations as plain data. It is
not a Tarav object and not a POI: a POI of a check needs the check that
raises it, and the analysis also runs outside checks. `finding.poi` is the
class; `finding.data` is read by key. `to_json()` gives the Type name and
the data, for command output.

**Types.** `SkwPOI` and the atomic Types move to `tarav.l1.skw.pois`. Each
Type states a literal `statement`; the message is the statement, the place
and the detail when there is one. A placeholder description is replaced by
the statement. The three strings without a Type get one, since a finding
can no longer be made without it.

**Checks.** They stay in `tarav.l2.skw.pois`, which no longer defines a POI
Type. The reading checks select diagnostics by Type. `FRESHNESS_KINDS`
becomes a tuple of two Types.

**Details.** A POI's details hold `finding.to_json()` as before, for the
reader. `SkwSkill.check()` returns the POIs of the evaluation and reads no
details.

**Commands.** `tarav skw document lint|compile` and the loading context
print `type` where they printed `kind` or `code`.

**Open point, for the user.** Point 6 can mean two things. (a) The Agents
file check raises the Skillware Types themselves, and its twelve duplicate
Types are deleted. (b) It keeps its Types and chooses one from the
Skillware Type. Until the user decides, the check keeps its Types and its
table is keyed by Type; no string remains in it.

## Impl.Req.Wiki

Product project: `tarav-py`. Wiki owner: `tarav-md`, root
`tarav-md/notes/wiki/`. Relevant notes: `poi-system.md`,
`daily/2026-10-13.md`. Supporting chat: session `abd0372d` above.
Capture status: done (`poi-system.md`, section "A Skillware finding names
its POI Type"; daily 2026-10-13).

## Execution.Plan

1. `l1/skw/pois.py`: `Finding`, `SkwPOI`, the Types with their statements.
2. Layer 1 analysis reports Types: `document.py`, `skills.py`, `loading.py`,
   `presentation.py`.
3. Layer 2: `pois.py` keeps the checks; `skills.py`, `reading_checks.py`,
   `publication.py` use Types; importers of the Types follow.
4. Agents file check: the table is keyed by Type.
5. Tests, the whole `tests/` folder, Ruff, and a real status run. The
   stored actions change message only; no identity changes.
6. Extension and skill documents: search for kinds and update.
7. Wiki capture.

## Impl.Log

- Design written from the discussion of 2026-10-13.
- Implemented points 1 to 5 as designed. `tarav.l1.skw.pois` holds `SkwPOI`,
  `Finding` and 41 atomic Types; `tarav.l2.skw.pois` holds only checks.
- Three Types that nothing ever reported were deleted with the table:
  `InvalidPublication`, `MissingOutput`, `InvalidInput`. Four Types were
  added for strings that had none: `PublicationDisconnected`,
  `MissingContent`, `InvalidProducedOutput`, `StaleProducedOutput`.
- `ModelPublication.render()` read an attribute that does not exist; it now
  reads the POIs of the render result. That path is still not run by any
  test or package.
- Point 6 is half done. The Agents file check has no string: its lint
  findings name Skillware Types, and its table is keyed by those Types. The
  table and the twelve Types of that check remain, awaiting the user's
  choice between (a) and (b) above.
- Checks: Ruff clean; the default run passes; the whole `tests/` folder
  passes except `test_scoped_lines`, which fails in another agent's area.
- Real runs: `tarav status --project .` shows the new sentences on the 20
  open Skillware actions and keeps every identity; `tarav skw document
  lint`, `tarav skw skills check` and `tarav skw skills context` print Type
  names.
- Data: the 58 stored Skillware actions whose details still held a kind were
  rewritten to the new wording and committed in the records registry.
- Documents: `ARCHITECTURE.md`; one sentence of
  `tarav-md/skills/tarav-hugentics/AGENTS.md`.
- Noticed, not changed: the Breadcrumb audit maps string concerns to POI
  Types through a table of the same kind.
