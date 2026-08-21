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

**Status.** Slice 1 **done**. Slice 2 **done** — see the remainder result below. Slice 3 delivered by 739 slice 4.

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

### Slice 1 — one citation parser — **done**

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

### Slice 2 — support references that know what they address — **premise was wrong**

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

### Slice 1 result

**Nine copies, not six.** The architecture rule went RED naming three the design pass had
missed, and widening its detector from `\d{8}` to `[0-9]{8}` as well found three more:

```
anchory/core.py:24                     chatlas/anchory.py:62
chatlas/event_query.py:706             chatlas/lossless/anchory.py:44
chatlas/lossless/chat_index.py:38      chatlas/lossless/chat_index_plan.py:16, :19
index/record/store.py:44               index_model/parser.py:55
poi/renderer.py:19                     skillware/model.py:99
```

All now route through `index_model/label.py`. `anchory/core.py:24` stays: it splits a trailing
tag off *any* `*-N` key for sharding and never parses the citation grammar — a different job
that happens to look similar.

**What the consolidation had to preserve.** `ANCHOR_RE` requires the caret and
`_ANCHOR_KEY_RE` forbids it, and both are right for their callers: scanning running text must
not strip a bare `20260820-1`, while a stored Anchory key never carries one. So `label` exposes
`CITATION_BODY` as a pattern string and composes both spellings from it — one grammar, two
compositions, rather than one regex forced to serve both.

`is_label` also kept its stricter contract. A label is a *complete* citation, sigil and tag
present, because the store never mints a partial one; parsing still accepts partials, because
the corpus holds them. That distinction now has a name — `Citation.is_complete` — instead of
living in the difference between two regexes nobody compared.

**Verified.** 2,127 tests pass. Classifying the whole corpus through the new module yields
2,783 citations and 93 locator names with **nothing unclassified**, and `split_trailing_address`
agrees with an independent scan on every one of the 2,876 lines. (2,783 rather than the design
pass's 2,776: parallel agents landed seven more lines during the slice.)

### Slice 2 result — the plan was wrong and the measurement said so

**The premise.** "Dispatch on `archive` and the 5,755 turn-addressed refs resolve." They do
not. Sampling 40 of them against the current archive: **0 resolve**, 39 miss, 1 session
unreachable.

**Why.** Their coordinates predate Chatlas2 entirely:

| kind | count | example |
|---|---|---|
| Chatlas1 ordinal turn ids | 3,641 | `turn-r1326` |
| provider-native uuids | 2,114 | `c5cd4ad4-476e-4baf-a657-b7c2621a3574` |

Chatlas2 addresses turns by 64-hex digest. Neither shape is one. A further sample of 25 uuid
refs found **0** appearing anywhere in the current Normal Model — expected, since Chatlas2
excludes provider-native payloads by default. They survive only in the raw archive.

So the 5,676 `Support.Mismatch` findings were honest that the refs do not resolve, and wrong
about why: they asserted the evidence had **changed** when it has never been **read**.

**What landed instead.** `Index.Linter/Support.LegacyCoordinate`, `BLOCKED` rather than
`FAILED`, for the same reason `Support.Unreachable` is blocked — a check that could not run is
not a check that failed. Measured on the live corpus:

| | before | after |
|---|---|---|
| findings (failed) | 14,964 | **9,288** |
| blocked | 79 | **5,755** |
| `Support.Mismatch` | 5,676 | 0 |
| `Support.LegacyCoordinate` | 0 | 5,755 |

5,676 + 79 = 5,755 exactly: every previously-unreachable ref was a turn ref too. The `chat`
path is untouched, and a test asserts a `chat` ref naming an absent message is still a
`Support.Mismatch` — the new state must not swallow the old one.

**Not done, and now correctly scoped.** The hash backfill (3,928 refs recoverable from
`~/Documents/chatlas/anchory`) is still valid and independent. Mapping the 5,755 legacy
coordinates onto Chatlas2 addresses is a raw-archive recovery job of the same kind as 642–645,
not a linter change — it needs its own measurement pass before anyone writes to 59% of the
corpus's support references.

**Owed to the index, not written.** `Index.Linter/Support.LegacyCoordinate` needs a block in
`tarav-pkg/poi/101-poi.md`. The index is frozen and that surface is gated, so this is a
`Capture.Offer`, not a landing.

### Slice 3 — not started

Unchanged from the plan above. It depends on nothing slice 2 did or did not do.

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


### Slice 2 remainder — the hash backfill and the coordinate migration — **done**

Governing constraint, from the invocation: *only migrate the turns that are clear — pollution
is worse than drift.*

**`SupportRef.message_hash`, schema `v5`.** Optional, and written absent rather than null: a
reference that never had a hash and one recorded as having none are the same state. `v4`
records read unchanged. The address says where to look; the hash proves what was found is what
was meant.

**The clarity criterion.** A legacy coordinate is *clear* when its Anchory dossier records a
timestamp and that timestamp matches **exactly one user-side message** in the session, to the
millisecond. Measured over all 927 distinct coordinates, not a sample:

| | |
|---|---:|
| clear | **862** (93.0%) |
| ambiguous — several user messages at that instant | 27 |
| unreadable — session will not normalize | 37 |
| absent | 1 |

**Two independent corroborations, both run before writing.**

- *One coordinate, one timestamp.* Across every dossier in the depot, 927 coordinates, **0**
  disagreements about when a turn happened.
- *Ordinal order matches chronology.* For the 409 clear `turn-rNNNN` coordinates, the turn
  ordinal and the mapped message's timestamp agree in every session: **0 inversions**. (A first
  pass reported 120; it was extracting trailing digits from uuid coordinates and ordering by
  them. The check is meaningful only where an ordinal exists.)

**The strongest evidence arrived as a problem.** Applying the plan would have given 1,590
records a duplicate support reference. Every one had the same cause: the record *already*
carried a `chat` reference to the exact message the timestamp join independently arrived at.
Zero collapses of several turns onto one message. So the join agrees with ground truth already
in the corpus **2,061 times**, and those 2,061 references are redundant rather than migratable.

**What was written.**

| action | refs |
|---|---:|
| migrated onto a current-model address | 2,108 |
| …carrying a hash recorded at reference time | 1,302 |
| dropped as redundant with a reference already present | 2,061 |
| hashes backfilled onto existing `chat` references | 3,987 |
| left exactly as they were, not clear | **1,586** |

**No hash is computed from today's archive.** Only hashes Anchory recorded at reference time
are written. Recomputing would manufacture the validation and destroy the drift it exists to
detect — the pollution the constraint names.

**The deviation trigger fired, and was read.** Of 824 recorded hashes checked against the live
archive, 823 agree and **1 disagrees**. Read before proceeding: the address resolves, the
message is user-side and coherent, only its content hash moved. That is real drift, not a bad
join, and writing the recorded hash is what makes it reportable.

**Corpus effect.**

| | before naming fix | after naming fix | after migration |
|---|---:|---:|---:|
| `Support.LegacyCoordinate` | 3,666 blocked | — | — |
| `Support.Unresolved` | — | 3,632 | **749** |
| POI instances | 16,624 | 16,661 | **13,808** |

**Coverage.** The drop raised `Coverage.Shrank` 862 times. Checked rather than assumed: all
862 are the same messages addressed by the current model — **zero** messages lost coverage.
The check's declared resolution is to read the commit, so the depot carries one explaining the
migration; the finding cleared at the new baseline, which is the loop working.

**Concurrency.** Another agent landed records throughout. The apply asserted the record count
had not moved and tripped on it — the corpus had grown by one. Verified directly instead:
4,054 records, 0 without support, 1,586 `chat-turn` refs remaining, which is exactly the
not-clear set.
