# 740 — The grounded Blessing.Record

## Impl.Abstract

Replace the gate-based, project-local blessing with a **grounded `Blessing.Record`**: a free
`Index.Line` carrying an agent's one-line explanation plus a `User.Touched` support set, naming
the `POI.Instance` it accepts, stored in its own Bloberia depot beside the `LineRecord`s.

A blessing stops being *the user approved this* and becomes *the agent claims this, and here is
the touched evidence it rests on*. Nothing stores whether a blessing is valid; that is derived
from whether its support resolves and qualifies, exactly as `LineRecord` standing is derived.

This requirement also adds `POI.Test`: a summonable finding that makes the linter's own
behaviour — selection, targeting, reporting, and now blessing — exercisable against a real
corpus. It is a general linter-development facility, not a fixture for one test.

Scope excludes: record-level project ownership (parked by 739), blessing concentration
reporting, and any migration path — **zero blessings exist today**, verified across the whole
worktree, so the old format is deleted rather than carried.

## Impl.Index

- [DC] a blessing is an `Agent.Claim`, not a user review: the record carries the agent's own
  one-line explanation of why it blessed, plus a `User.Touched` `Support.Set`
- [CT] the `Blessing.Record` must carry everything the linter needs both to *read* the blessing
  and to *run checks on the blessing itself*
- [DC] the record stores no validity flag; whether a blessing silences its POI is derived from
  its support, the same rule that makes `LineRecord` carry no `head` or `reviewed` field
- [CT] a grounded blessing carries `Touched.Authority` and silences its POI; an ungrounded one
  is an `Index.Presumption`, silences nothing, and is itself a finding
- [DC] the explanation is a **free** `Index.Line` — it has no scope, and freeness is a property
  of the host rather than a field on the line
- [RJ] no `ScopeKind` for POI instances: a scope kind would make freeness a blessing-shaped
  special case instead of a general capability
- [CT] `Record.Unplaced` and every other surface check binds to its host, so a check that asks
  "is this line placed?" is simply never offered the blessing depot
- [DC] blessings live in their own Bloberia depot beside the record depot, carrying no project
  data: the POI identity is already global because its subject is a depot-global record id
- [CT] a `Support.Set` is never mechanically checked for *relevance* — that is the
  `Semantic.Assertion` the record exists to make auditable later, and it is true of every
  support set, not only a blessing's
- [PR] a finding about a blessing is not itself blessable, or the grounding requirement is
  answered by another ungrounded blessing and becomes decorative
- [DC] `POI.Test` is a general mechanism for working on and testing the linter, so it is a
  documented durable check with named probes rather than a fixture

### Presumptions

- [PR] the blessing depot is separate from the record depot rather than sharing it under a
  discriminator, because a shared depot would put blessings in front of every check that
  iterates records and make host-bound applicability a filter rather than a structure
- [PR] `bless` does not verify at write time that its POI occurs: the orphan is a derived
  condition like every other, and write-time verification would cost a full corpus lint

## Execution.Plan

### Slice 1 — `POI.Test`, the summonable finding

The instrument comes first: every later slice is verified with it.

- Add a marker constant and a `poi-test` check that scans the raw text of every discovered
  surface file for the marker, with an optional `#<tag>` suffix naming the probe.
- Subject is `<surface>#<tag>` — deliberately not `<scope>:<lineno>` like the other surface
  checks, because this POI must stay blessed while the file is edited around it.
- Assemble the marker from parts in its own module so the defining file never matches itself.
- Register it with `why` and `resolutions` like every other check.

**Check:** a fixture surface containing the marker yields exactly one finding; two distinct
tags yield two independent findings; the identity is unchanged after an unrelated edit to the
same file that moves the marker's line number.

### Slice 2 — `BlessingRecord` and its depot

- `record/blessing.py`: `BlessingRecord(id, poi, line, support)` on schema
  `tarav.index-blessing-record.v1`, reusing the existing `Line` and `SupportRef` primitives.
- `BlessingStore` over a Bloberia shards depot keyed by `id`, with `Geography.blessing_depot`
  following the same public-path-unless-overridden rule as `index_depot`.

**Check:** round-trips through the depot; a blessing written under a test `TARAV_INDEX_HOME`
never appears in the index record depot, and vice versa.

### Slice 3 — derived standing, and the checks on the blessing itself

- `blessing_standing()`: resolves each support ref and reports grounded / ungrounded /
  unresolved / untouched. No stored flag anywhere.
- `lint()` consults the blessing store instead of `blessed.json`; a grounded blessing moves its
  finding to the `blessed` lane, anything else leaves the finding standing and emits its own.
- New POI classes: `Blessing.Ungrounded`, `Blessing.Support.Unresolved`,
  `Blessing.Support.Untouched`, `Blessing.Orphaned`.
- Delete `_blessings_path`, `read_blessings`, `_blessing_holds`, the `GateRef` parameter on
  `bless`, and `Index.Linter/Blessing.Unevidenced`.
- Exclude every `Blessing.*` class from blessing application.

**Check (RED then GREEN per condition):** a blessing with resolving user-side support silences
its POI and no other; one with no support does not silence and reports `Blessing.Ungrounded`;
one whose ref does not resolve reports `Blessing.Support.Unresolved`; one grounded on an agent
turn reports `Blessing.Support.Untouched`; one naming an absent POI reports `Blessing.Orphaned`;
and a `Blessing.*` finding cannot itself be blessed.

### Slice 4 — the CLI

- `tarav index bless --poi-id --body [--type] --session --support ...` writes the record and
  immediately prints its derived standing, following `gate`'s report-don't-refuse shape.
- `bless` leaves `PROJECT_COMMANDS`: it writes to the depot, so the coupling 739's contract was
  removing is gone rather than satisfied.
- `tarav index blessings [--poi-id]` lists blessings with their derived standing.

**Check:** end-to-end through `POI.Test` on a fixture project — summon two probes, bless one,
confirm it is reported `blessed` while the other stays `failed`, and confirm the blessing
survives a re-run.

### Slice 5 — close the visited surfaces

- Update `AGENTS.md`, the architecture notes, and the CLI contract section.
- Run the focused Index/CLI suites, then the full suite and ruff.
- Audit changed product surfaces, mint the line-dossier batch for this artifact's `Impl.Index`,
  and backpropagate.

## Impl.Log

- [TS] Execution of Impl.Req 740 is authorized by the tarav-hugentics `--impl --dev --AUTO`
  invocation.
- [OBS] Verified before designing: no `blessed.json` exists anywhere in the worktree and the
  current corpus lint reports 0 blessed instances of 16,600. The old format has no data.
- [OBS] The worktree already contains concurrent Index work from 739 (report model, capture,
  linter resolution) plus this session's `--project` conversion. All of it is shared state and
  must be preserved.
- [OBS] `Finding.identity` is `sha256(poi_class, subject, surface)` and deliberately excludes
  `operands`, so a blessing already survives the accepted value drifting. Slice 1's subject
  choice extends that same intent to the marker's line number.
- [PR] The support-message addresses selected as grounding for `Impl.Index`, to be minted at
  slice close, all in session `9f41aa0e-d2cd-4873-b35d-0a3e1239c9e5`:
  `f3822a678124f3a4` (bloberia, Stable Surface, Chat.Surface context, no project data),
  `270f6e0ef6222c6e` (agent claim, support set, like an Index Line, checks on the blessing),
  `5ed6bf744b083ebb` (free Index.Line, explanation indexes the explanation, later audit),
  `12809a93bbc1c381` (blessings can be free lines, other surfaces do not allow them),
  `8289ebbfa6696847` (create a POI that is a test),
  `57719fe142be2895` (a general mechanism for working and testing the linter).
