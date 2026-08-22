# 755 — index-2208 migration

## Note.Abstract

- **Purpose:** record what the `index-2208` migration moved, what it deliberately did not
  decide, and the grounded prior decisions it reused, so the result can be audited without
  re-reading the scripts.
- **Session:** `9f41aa0e-d2cd-4873-b35d-0a3e1239c9e5`
- **Status:** complete. Corpus archived, extracted, loaded into `index-2208`, folded, and linted.
- **Rule:** this is a **format** migration. Nothing here validates the corpus. Defects are
  carried into the new model intact so the new linter can report them.

## 1. Conservation first

The umbrella root `taravangian-project` **is not a Git repository**, and it holds
`.tarav/state/index-anchor-locators` — 2.8M of anchor occurrence data. `tarav-js` and
`tarav-pkg-testground` are also unversioned. Before anything else, everything was frozen into
`index-archive-2208/`, itself a Git repository:

| Group | Count | Note |
|---|---|---|
| `surfaces/` | 210 | every Markdown file with a typed line or an anchor |
| `code/` | 475 | every `$kw`-annotated source file |
| `state/` | 176 | every `.tarav` store, `_root` first |
| `external/` | 367 | the anchory depot, `~/Documents/chatlas/anchory` |

The anchory depot lives **outside the project tree** and was missed by the first pass. It
carries the `session` / `message_address` / `message_hash` triples every `Support.Set`
resolves through; archiving the citations without it would have kept the references and lost
their referents.

`MANIFEST.json` records a per-file sha256 and each source repo's commit SHA, so a restore can
prove byte-identity and the migration can be audited against a frozen source rather than
against whatever HEAD said at the time.

## 2. Decisions reused, not re-derived

`dev/live/643-anchory-to-line-records.py` already settled the hard questions for the previous
migration. They carry:

- **`Migration.Current.Only`** — one target schema. Every legacy family maps onto the new
  model rather than being preserved beside it.
- **Conservation governs** — "a record is never skipped for being incomplete". An ungrounded
  line migrates with an empty `Support.Set`; an unaddressable line falls back to its file and
  then to quarantine. Each is a loud finding, never a silent omission.
- **Coordinates are mapped, never invented** — an unresolved anchor produces an empty
  `Support.Set`, not a plausible-looking one.

`tarav-py/AGENTS.md` supplies one more, and it is why `$kw` notes are in scope at all:

> Native Index surfaces, SKW annotations, and other domain surfaces are one distributed Index
> under Natural.Placement. An Index line on code is still an ordinary Index line and must
> receive a LineRecord through the same mechanics.

## 3. Two decisions this migration had to make

**`Record.Context` is the migration pass, not the original chat.** 642 makes context and
support orthogonal: `Record.Context` bounds *derivation*, `Support.Set` bounds *authority*.
The derivation event for these records is this migration — they did not exist before it. The
original chat session is authority, so it goes to `Support.Set`. Writing the anchor's session
into `Record.Context` would claim these records were derived in a chat that never saw them.

**Repeated anchors become Isolines, not collisions.** 620 lines cite an anchor already used
elsewhere. `line.capture` requires a globally unique label, so the naive reading is a
conflict — but this is exactly what `Index.Isoline` exists for: one semantic line with several
projections. Occurrences share an `isoline_id` and take distinct `Line.Id`s. The repetition
survives as structure instead of being deduplicated away. Secondary projections take a
`~n`-suffixed label, which is migration-assigned and greppable.

## 4. What came across

3,975 index lines → 5,047 records (1,072 `block.create` + 3,975 `line.capture`).

| Measure | Count |
|---|---|
| markdown lines | 3,633 |
| `$kw` note lines | 342 |
| anchors resolved to support | 3,408 |
| anchors resolving to nothing | 262 |
| lines with no anchor at all | 696 |
| untyped lines | 626 |
| isoline projections | 620 |
| incomplete support members | 58 |

Coverage was verified line-for-line against the archive: markdown 3,633 expected / 3,633
captured, `$kw` 342 / 342. Exactly one `--note` was excluded — a bare `--note` with no body
inside a test fixture string demonstrating a malformed annotation. It is not an Index line.

The 262 unresolved anchors and 696 ungrounded lines are **migrated, not dropped**. They are
the backlog the new linter should report, which is the point of moving format first.

## 5. The load, and what the linter found

All 5,047 records loaded and fold into a coherent projection: **1,072 blocks holding 3,975
lines**, `cargo_defects: 0` — every record round-trips through the model.

`tarav indexlab lint` over the full corpus, 32.5s, 7 checks:

| status | check |
|---|---|
| passed | `records-loadable`, `support-roles`, + 1 |
| failed | `support-present`, `support-resolves` |
| blocked | `context-resolves`, `support-visible` |

| POI class | total | failed | blocked |
|---|---|---|---|
| `IndexLab.Linter/Context.Unresolved` | 5,047 | 0 | **5,047** |
| `IndexLab.Linter/Support.Empty` | 2,001 | 2,001 | 0 |
| `IndexLab.Linter/Support.Amended` | 1 | 1 | 0 |

Three things worth reading carefully:

**`Context.Unresolved` is blocked, not failed — for every record.** The migration's
`Record.Context` names this session honestly, but its horizon `Turn.Ref` (`index-2208:corpus`)
is minted by the migration and is not a real Chatlas turn. So the check cannot resolve it and
reports *nothing known* rather than *something wrong*. That is the correct verdict and the
exact distinction 752 argues for: blocked is expected, failed is a defect.

**`support-visible` is blocked by `context-resolves`.** The dependency short-circuit works:
one unresolvable precondition suppresses the check that depends on it without pretending the
run was clean. `verified: false`, `clean: false`, `short_circuited: false`.

**`Support.Empty` decomposes exactly**: 2,001 = 1,072 `block.create` (empty by construction)
+ 929 lines with no resolvable support. Verified against the manifest, not inferred.
**3,046 of 3,975 lines — 77% — carry real resolved support.**

The 929 ungrounded lines are the honest backlog. They were migrated, not dropped, and the
linter can now see every one of them. That is what moving format first buys.

## 6. Open

- **`append_many` is O(n²).** It calls `append` per record, and each `append` calls
  `self.list()`, re-reading the whole depot. Loading 5,047 records took ~25 minutes, degrading
  from ~150 records/10s. Fine for a one-off; a real defect for a kernel meant to take
  continuous capture.
- **The migration horizon is unresolvable by construction.** Every record blocks
  `context-resolves`. Either the kernel needs a first-class way to say "this context is a
  migration, not a chat turn", or migrated records need a real turn to hang from. Right now
  the honest answer produces 5,047 blocked checks, which is correct but not useful.
- 642 says to reconcile "the 3,974-record Bloberia corpus"; this extraction produced 3,975
  lines. Close enough to be worth checking whether they are the same corpus.
- Nothing in the live tree has been rewritten. The old system is untouched and still runs.

## 7. Hugentics wording

The always-loaded `What The Index Is` block now describes the recording kernel:
context-attached `Index.Record`s in an `Index.Workspace`, `Record.Context` and `Support.Set`
as orthogonal bounds, the record sequence as the sole `Index.Primary.Surface`,
Isoline/Isoblock replacing trace and equivalence, and `Skw.Annotation` as
`Project.Index.Grounding` rather than a distributed Index materialization.

Dropped, because 642 says they must not remain: `Chat.Index.HEAD`/`Delta` backpropagation,
`Demoted.Index.Line` standing, and the Chatlas2 dossier as a privileged link.

**The `Index.Skillware` chapter and depot literacy was kept alongside it.** The first edit
removed it and that was wrong: the corpus in hand is still written as chapters, and capture
does not yet run on records, so a skill without that literacy would describe a system that
cannot perform its own workflows.

`tarav skw check`: 0 POIs, 0 diagnostics.

### What blocks the rest

The `--from` list declares `Kernel.Block::Index` dependencies, so a term can only be declared
once it is a real block. Of the thirteen new-model terms, **three exist and ten do not**:

| Declared today | Not declared anywhere |
|---|---|
| `Evidence.Neighborhood`, `Index.Block`, `Support.Set` | `Index.Record`, `Record.Context`, `Index.Isoline`, `Index.Isoblock`, `Index.Primary.Surface`, `Index.Secondary.Surface`, `Index.Workspace`, `Index.Library`, `Project.Index.Grounding`, `Index.Record.Operation` |

Declaring the ten now would produce dangling references. **Landing the 642 model into the
index is the prerequisite for finishing the wording migration**, and for the operational
layer too: the workflow prose still routes through `tarav index capture` (18 references),
which IndexLab has no equivalent for.
