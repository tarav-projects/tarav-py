# 755 — index-2208 migration

## Note.Abstract

- **Purpose:** record what the `index-2208` migration moved, what it deliberately did not
  decide, and the grounded prior decisions it reused, so the result can be audited without
  re-reading the scripts.
- **Session:** `9f41aa0e-d2cd-4873-b35d-0a3e1239c9e5`
- **Status:** corpus archived and extracted; workspace load in progress.
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

## 5. Open

- **`append_many` is O(n²).** It calls `append` per record, and each `append` calls
  `self.list()`, re-reading the whole depot. Loading 5,047 records degrades from ~150
  records/10s and keeps slowing. Fine for a one-off; a real defect for a kernel meant to take
  continuous capture.
- 642 says to reconcile "the 3,974-record Bloberia corpus"; this extraction produced 3,975
  lines. Close enough to be worth checking whether they are the same corpus.
- The hugentics wording migration is not started. Superseded terms still in `.skw/src`:
  `Chat.Index.HEAD` (7), `Chat.Index.Delta` (6), `Index.Native.Surface` (10),
  `Index.Depot` (14), `Demoted` (10), backpropagation language (16). 642 is explicit that
  HEAD/Tail, agent/user standing, Chat.Index backpropagation and HEAD-surface discovery
  "must not remain responsibilities of the reduced recording kernel".
- Nothing in the live tree has been rewritten. The old system is untouched and still runs.
