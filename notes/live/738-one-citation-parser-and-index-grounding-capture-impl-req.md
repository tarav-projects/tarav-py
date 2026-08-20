# 738 — One citation parser, and grounding capture in the index

## Impl.Abstract

**Scope.** Three slices, in order:

1. One parser for the citation grammar. Six ad-hoc regexes across five packages collapse into
   one module — which turns out to own **two** grammars, not one.
2. Support references that know what they address. `archive` already distinguishes a
   message-addressed ref from a turn-addressed one, and nothing dispatches on it.
3. Grounding capture in the index: verified support resolution, equivalent-line detection, and
   batch landing — the functionality `chatlas2 anchory preview|register|batch` provides today,
   rebuilt on `LineRecord` rather than on the dossier.

**Out of scope, by explicit decision.** Making `tarav index resolve --label` work from a
directory without `.tarav`. Keep as is; discussed later.

**Also out of scope.** Deleting `src/tarav/anchory/` or `chatlas/anchory.py`. Slice 3 gives the
capture path a replacement, which is the precondition for retiring them — but the retirement
itself rides with the v1 chatlas model in its own `Impl.Req`. Nothing is deleted here.

**Status.** Slices 1–3 not started.

**Source context.** Follows 737, which closed the provider boundary and made the Index CLI a
selector surface. Continues the 641 migration.

## Impl.Index

The index is frozen (638 Invariant 1), so these lines carry no anchors.

- [CT] a citation and a locator name are two address kinds sharing one sigil; one grammar for
  both would conflate them, so the consolidation is one module owning two named grammars
- [DC] `Citation` is `^<sigil><YYYYMMDD>-<seq><tag>` and points at an index record;
  `Locator.Name` is `^<kebab-name>` and names a region of a surface
- [CT] `SupportRef.archive` names the coordinate space its `message_id` lives in; a consumer
  that ignores it resolves a turn address against messages and reports drift that is not there
- [DC] a support reference carries a content hash so drift is detectable; without one,
  verification can only prove the coordinate still exists, not that it still says the same thing
- [CT] verification, equivalence detection, and batching are index write-path concerns, not
  anchor-dictionary concerns — they moved to Anchory only because Anchory owned the store
- [EX] the citation grammar has six implementations: `anchory/core.py:24`,
  `chatlas/anchory.py:62`, `index_model/parser.py:55`, `index/record/store.py:44`,
  `poi/renderer.py:19`, `skillware/model.py:99`

### Hard.Evidence

Measured during design, across `tarav-py`, `tarav-md`, `tarav-chatlas-md` and `_DEPRECATED/tarav2`:

| fact | number | how |
|---|---|---|
| trailing `^` tokens in the corpus | 2,869 | scan of `.md` and `.py` |
| …matching the strict citation grammar | 2,776 | same scan |
| …**not** matching it — locator names like `^package-driver-router` | **93**, 17 distinct | same scan |
| support refs addressing a **turn** (`archive="chat-turn"`) | **5,755** | depot scan |
| support refs addressing a **message** (`archive="chat"`) | 4,013 | depot scan |
| `Index.Linter/Support.Mismatch` findings in the corpus | **5,676** | full corpus lint |
| total corpus findings | 14,964 | full corpus lint |
| support refs with a hash still recoverable from the Anchory depot | **3,928** | join over `~/Documents/chatlas/anchory` |

The middle three rows are the load-bearing ones. `_check_support_resolves` calls
`session.message(ref.message_id)` for every ref regardless of `archive`, so all 5,755
turn-addressed refs fail to resolve. **5,676 of the corpus's 14,964 findings — 38% — are one
unhandled archive kind**, not evidence of anything wrong with the data.

### Dependency evidence for the parser's home

| package | already depends on `index_model`? |
|---|---|
| `index` | yes |
| `chatlas` | yes |
| `poi` | yes |
| `skillware` | yes |
| `anchory` | **no** (`_core`, `poi`, `wayfinder`) |

`index_model` itself depends only on `_core` and `surfaces`. Putting the grammar there adds
**zero** edges for five of six consumers, and one for `anchory`, which is being retired. Putting
it in `index` instead would make `poi` and `skillware` depend on `index`, which they do not
today — a new edge into a much heavier package, for a regex.

## Execution.Plan

### Slice 1 — one citation parser

**Do.** Create `src/tarav/index_model/label.py` owning both grammars and the classifier that
tells them apart. Replace all six regexes with calls into it.

The two are not variants of one pattern and must not be merged: `^c20260820-0u` resolves to a
record, `^package-driver-router` names a block in a `.skw` source. A single permissive regex
would let a locator name be handed to `IndexStore.by_label` and a citation be treated as a
region name. Both grammars, both named, one module.

Consumers keep their own *use*, not their own *grammar*:

| site | today | becomes |
|---|---|---|
| `index_model/parser.py:55` | `ANCHOR_RE` | find citations in a line |
| `index/record/store.py:44` | `LABEL_RE` | parse a citation into its parts |
| `chatlas/anchory.py:62` | `_ANCHOR_KEY_RE` | validate an unprefixed key |
| `anchory/core.py:24` | `_TAGGED_KEY_RE` | split tag from base |
| `poi/renderer.py:19` | loose strip | strip a trailing address of *either* kind |
| `skillware/model.py:99` | loose extract | extract a trailing address of *either* kind |

**Check.** The suite stays green, and a scan of all four repos classifies the same 2,776
citations and 93 locator names as before — no token changes category.

**Test (RED first).** A test that no module outside `index_model` compiles a regex containing
the citation shape, so the seventh implementation fails here. Plus a table test over real
tokens from the corpus scan — including `^package-driver-router` and `^c20260820-0u` — asserting
each classifies as exactly one kind.

**Risk.** `skillware/model.py` extracts the trailing anchor into `SkwNote.anchor`. If the strict
grammar were applied there alone, 93 locator-name anchors would stop parsing and silently
become part of the note text. That is why the classifier accepts both kinds rather than the
consolidation narrowing to citations.

### Slice 2 — support references that know what they address

**Do.**

1. **Dispatch on `archive`.** `_check_support_resolves` and every other consumer resolves a
   `chat` ref against messages and a `chat-turn` ref against turns. This is the fix for 5,676
   findings; nothing about the data changes.
2. **`SupportRef` gains an optional `message_hash`** (schema `v5`). Optional, not required: the
   5,755 turn-addressed refs never had one, and making it mandatory would render them
   unstorable — the same mistake `v3`'s single review gate made, which `v4` had to widen.
3. **Backfill 3,928 hashes** from `~/Documents/chatlas/anchory`, which still holds them. This is
   recovery of evidence the 643 migration dropped, not new data.
4. The support check compares the hash when present and reports drift distinctly from absence.

**Check.** After the dispatch fix, a full corpus lint reports roughly 9,288 findings rather than
14,964, and the difference is entirely `Support.Mismatch` on turn-addressed refs. Every
remaining `Support.Mismatch` names a ref that genuinely does not resolve. Record count
unchanged at 3,993; support-ref count unchanged at 9,768.

**Test (RED first).** A `chat-turn` ref whose turn exists must resolve clean — that fails today.
And a `chat` ref whose stored hash disagrees with the archive must report drift, distinctly from
one whose coordinate is missing: absence and disagreement are different states and a check that
collapses them cannot be acted on.

**Risk.** This is the slice that touches live records. It writes only an added field, never
removes one, and the backfill source is read-only. Verify the record count and the per-record
support-ref count before and after; any change is a failure, not a rounding.

**Deviation trigger.** If a backfilled hash disagrees with the archive for a ref the migration
carried, stop. That is either a real drift finding or a bad join, and both need reading before
9,768 references are rewritten.

### Slice 3 — grounding capture in the index

**Do.** Create `src/tarav/index/capture.py` with the three capabilities `chatlas2 anchory`
provides, rebuilt on `LineRecord`:

- **verify** — `resolve_support(geo, refs)` resolves each `<session>:<address>:<hash>` against
  the archive, requiring the message to exist, its hash to match, and its side to be `user`.
  Today `index write --support` takes ids on trust (`cli.py:324`); this is the gap.
- **detect equivalence** — find an existing record with the same support set and body, and
  return it for reuse rather than minting a second label for the same line. The dossier did
  this with a `triplet_hash`; the record model needs no such field, because body and support
  are already stored and comparing them directly is both equivalent and cheaper to check.
- **batch** — resolve and land a whole set in one pass under one lock, returning the
  line-to-label mapping the Hugentics capture loop applies to a surface in a single patch.

**CLI.** `tarav index capture preview` (resolve and report, write nothing) and
`tarav index capture land`. Named options only, per 737.

**Check.** For a landing the old path handled, the new path produces the same label reuse
decision and the same support set. Preview writes nothing — asserted by comparing the depot's
git status before and after.

**Test (RED first).** `index write --support` accepting a message id that does not exist is the
current behavior; the new path must refuse it. A second landing of the same body and support
must reuse the first label rather than minting a second.

**Risk.** Preview must be provably read-only. The index depot is git-tracked, so the test can
assert a clean status after a preview rather than trusting the implementation.

**Deviation trigger.** If equivalence detection over 3,993 records is too slow for an
interactive capture loop, narrow with a bloberia query on the support coordinates before
comparing bodies — do not weaken the comparison.

## Impl.Log

**Presumption (`Index.Presumption`).** That the 5,676 `Support.Mismatch` findings are entirely
the turn-addressed refs is inference from two counts that nearly coincide (5,755 refs, 5,676
findings), not from a per-finding join. Slice 2's check confirms or refutes it; if the residue
is not ~79, the difference is real and gets read before anything is called fixed.

**Correction carried in.** My earlier suggestion framed this as "six implementations of one
grammar." The scan says otherwise: two grammars, 2,776 tokens of one and 93 of the other. A
consolidation that had merged them would have been a regression dressed as cleanup.

**Awareness.** Other agents are working this tree concurrently. Slice 2 writes to the shared
live depot; do the record-count check immediately before and after the backfill rather than
trusting an earlier reading, and prefer narrow edits over file rewrites throughout.
