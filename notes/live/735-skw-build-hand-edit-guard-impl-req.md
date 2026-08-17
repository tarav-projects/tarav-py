# 735 — `skw build` hand-edit guard

## Impl.Abstract

**Scope.** `tarav skw build` currently overwrites every compiled target
unconditionally. When session work has been written into a compiled surface
instead of its `.skw.md` source, the build destroys it and reports `[built]` —
a line indistinguishable from an ordinary rebuild. Make the build refuse,
per file, to write over a target whose on-disk content differs from the
`output_sha256` the lock recorded for it, and give the caller one explicit,
per-target escape: `--discard-hand-edits <target>` (repeatable).

**Status.** Executed. All four slices landed; 2015 tests pass, project POI count
unchanged at 33, changes uncommitted for review.

**Source context.** Chat of 2026-08-17 while working on `g70203-pkg`. Two
compiled surfaces in that package (`references/ingest.md`,
`references/db-index-fields-spec.md`) carried content that lived only in the
compiled artifact. The second was destroyed by a build and recovered only
because its text happened to still be in agent context. The detection this
guard needs already exists — `check_skill` computes exactly this condition and
reports it as the `hand-edited` POI — but `build_skill` never consults it.

**Out of scope.**

- changing what `check` reports, or its POI kinds, severities, or hashes
- any bulk/global form of the escape flag (explicitly refused: the flag names
  one target so the caller types what is being destroyed)
- backing up or salvaging the discarded content
- the `.skw/AGENTS.md` stamp, which is engine-owned and overwritten by design
- project-scope (`check_project`) behavior; build is package-scoped

## Impl.Index

- [CT] the engine compares a content hash against the lock and knows nothing
  else, so the refusal states only that the output carries changes not present
  in the source — it must not assert that the changes are wanted, are session
  work, or should be backported
- [DC] the message names the target, its src file, and both hashes, and offers
  preserving-in-src or `--discard-hand-edits <target>` as *hints*, in the shape
  the user approved verbatim:
  ```
  error: references/db-index-fields-spec.md has changes not present in its source
         src/references/db-index-fields-spec.skw.md
         target hash 9f2a…  lock hash 41c7…
         hint: preserve them in src, or --discard-hand-edits <target> to rebuild from src
  ```
- [DC] the guard is per file: a refused target does not stop its siblings from
  building, and the run exits non-zero
- [DC] the escape is per target and repeatable; there is no bare bulk form,
  because a blanket flag becomes reflex and the guard stops protecting anything
- [CT] the guard fires only when the lock holds an `output_sha256` for the
  target. With no lock entry there is no baseline, and the first build after
  adoption legitimately writes over a pre-existing hand-owned file
- [CT] a refused file must carry its previous lock entry forward verbatim. The
  build rebuilds `lock.json` from scratch each run; dropping the skipped file's
  entry would leave the next build with no baseline and it would clobber
  silently — the exact failure this work exists to prevent
- [CT] a refused file is also skipped for src refresh. Refusing the target
  while mechanically rewriting its source would half-apply the build
- [CT] `.skw/AGENTS.md` is not a lock `files` entry, so it is outside the guard
  with no carve-out needed; `test_build_overwrites_hand_edited_agents_md` pins
  that it stays overwrite-always
- [PR] `--discard-hand-edits` naming a path that is not a managed target is an
  error (typo protection); naming a target that is not hand-edited is a silent
  no-op, so a script that always passes the flag does not become brittle
- [DF] "hand-edited" here is `check_skill`'s existing discrimination: on-disk
  differs from lock. On-disk *equal* to lock but differing from a fresh
  compile is `stale-build` — an out-of-date target, not a modified one, and it
  must keep building without complaint
- [PS] the guard's value depends on nothing else legitimately writing to a
  compiled surface after a build; a survey of the repo's own packages before
  landing is the check on that assumption

## Execution.Plan

### Slice 1 — refuse in the engine

`src/tarav/skillware/_build_operations.py`.

- add `BuildRefusal(target, src, target_sha256, lock_sha256)` and a
  `refusals: tuple[BuildRefusal, ...]` field on `BuildReport`
- `build_skill(skill_root, *, discard_hand_edits: tuple[str, ...] = ())`
- at the top of each `src_files()` iteration, before `expand_file`: resolve
  `target_rel = skillware.target_rel(src_rel)`; if the target exists, the old
  lock has an `output_sha256` for it, the on-disk sha differs from it, and the
  target is not named in `discard_hand_edits` → record a refusal, copy the old
  lock entry into the new lock verbatim, append a `BuildEntry(action="refused")`,
  and `continue`
- raise `SkillwareError` when a `--discard-hand-edits` value does not name a
  managed target, listing the managed targets

**Check.** `uv run pytest tests/test_skillware.py tests/test_skillware_project.py
tests/test_skillware_parser.py tests/test_skillware_context.py
tests/test_skw_unlock_tokens.py`

**RED first** (`tests/test_skillware.py`):

1. `test_build_refuses_to_overwrite_a_hand_edited_target` — build, append
   `rogue edit` to `references/mod.md`, build again: the rogue text survives,
   that entry's action is `refused`, the report carries one refusal with both
   hashes, and its sibling targets still report `built`/`unchanged`.
2. `test_a_refused_target_keeps_its_lock_entry` — after the refused build, the
   lock still holds the previous `output_sha256` for that target, and a third
   build refuses again rather than clobbering.
3. `test_discard_hand_edits_rebuilds_the_named_target` — same setup, build with
   `discard_hand_edits=("references/mod.md",)`: the rogue text is gone, the
   file equals `MOD_COMPILED`, and no refusal is reported.
4. `test_discard_hand_edits_is_per_target` — two targets hand-edited, discard
   one: that one rebuilds, the other is still refused.
5. `test_discard_hand_edits_rejects_an_unknown_target` — `SkillwareError`.
6. `test_a_stale_build_is_not_refused` — edit src only; the target still
   matches the lock, so it rebuilds normally.

### Slice 2 — CLI surface

`src/tarav/skillware/commands.py`.

- `build` subparser gains
  `--discard-hand-edits` (`action="append"`, `default=[]`, metavar `TARGET`)
- `_cmd_skillware_build` reads it with `getattr(args, "discard_hand_edits", [])`
  — existing tests construct `argparse.Namespace` by hand
- text output prints the approved multi-line `error:` block per refusal
- JSON payload gains a `refusals` array with `target`, `src`, `target_sha256`,
  `lock_sha256`
- exit code becomes `1 if report.findings or report.refusals else 0`

**Check.** a CLI test in `tests/test_skillware_project.py` asserting exit 1, the
JSON `refusals` shape, and that the text form contains the target, the src path,
and the `--discard-hand-edits` hint.

### Slice 3 — surfaces

- `AGENTS_MD_TEXT` in `_build_operations.py`: one line stating that build
  refuses a target whose content differs from the lock and naming the flag.
  (This is the compiled `.skw/AGENTS.md` an agent reads at the build surface.)
- `tarav-py/AGENTS.md`, the `agentos skw` bullet: one sentence on the guard.
  Required by that file's own first rule.
- `POI_LEGEND["hand-edited"]` prescription: mention that build now refuses it.

**Check.** `uv run pytest tests/` for the whole suite, plus `ruff check src tests`.

### Slice 4 — survey the assumption

Run `tarav skw check` over the packages registered on this machine and count
`hand-edited` targets. If the condition is common in normal operation the guard
becomes noise; report the count rather than adjusting the design silently.

**Result.** 21 packages under `~/projects`, 96 managed targets: **2**
hand-edited, **0** stale-build, both in `tarav-md/skills/tarav-pkg`
(`references/index-retrofit.md`, `references/index-retrofit-worker.md`).
Nothing routinely writes to a compiled surface after a build, so the guard is
safe to make strict — and the survey immediately found two more instances of
the failure class it exists to prevent.

### Slice 5 — backport `tarav-pkg` (added during execution)

Both surfaces carried a coherent revision that existed nowhere else: the
amendment-versus-successor distinction for support edges, `Index.Line.Anchor`
terminology replacing "trailing support reference", the v2 dossier model, and
`ambiguous` anchor-occurrence standing holding a packet. 12 hunks, applied to
src by aligning each against the fresh compile and requiring a unique match.

Both targets then rebuilt **byte-identical** — `[unchanged]`, which is the
proof the backport was exact rather than approximate. One consequence
surfaced: the recovered text mentions `Index.Line.Anchor`, which resolves in
the depot but was undeclared, so `--from Index.Line.Anchor` joined the
dependency block. `tarav skw check --skill .` is now 0 POIs across all three
files.

## Impl.Log

- [PS] the escape flag is deliberately not implemented as a bare bulk form even
  though every other repeated flag in this CLI (`--unlock`) allows a bare
  accumulate. The user asked for the conservative shape explicitly; if a bulk
  form is ever missed, that is evidence to add later, not now.
- [DC] **the first predicate was wrong and the backport exposed it.** Refusing
  on `on-disk != lock` alone flagged `tarav-pkg/SKILL.md`, a file identical to
  what src compiles to whose lock hash predates an engine change. Stale
  bookkeeping is not lost content, and a guard that fires on it is the noise
  that teaches a caller to reach past it — the exact objection raised against
  the design before it was built. The predicate is now `check_skill`'s
  `hand-edited` exactly: differs from the fresh compile **and** from the lock.
  This also reordered `build_skill`'s loop, since the guard now needs the
  expansion before it can decide.
- [CT] the guard therefore runs after `expand_file` but before the src refresh
  and the target write, so a refused file still has nothing written on its
  behalf.
- [DC] the four inline `#` comments the first pass wrote into
  `_build_operations.py` each raised a `non-skw-annotation` POI — this project's
  strict code policy admits no bare comments. Both facts were maintenance
  relevant, so they moved into the enclosing docstrings rather than being
  deleted; project POI count returned to its 33 baseline.
- [CT] the target hash is computed as `read_text(encoding="utf-8").encode(...)`,
  matching `check_skill` exactly rather than hashing raw bytes. Raw bytes would
  be stricter — text mode folds CRLF to LF, so a line-ending-only change slips
  past both — but a build refusing what `check` calls clean would be a
  condition with no diagnostic anywhere.
- [PS] refusing when the target exists with no lock entry was considered and
  rejected: it would break the adopt path, whose first build necessarily writes
  over a hand-owned file. That leaves one uncovered case — a target deleted from
  the lock but not from disk — which `check` still reports as `never-built`.
