# 757 — IndexLab RecordStore corpus rescan

## Impl.Abstract

- **Goal:** stop `RecordStore.append` and `append_many` from re-reading and re-validating the
  entire record corpus once per appended record, and remove the duplicated cargo-reading
  logic between `list` and `load`.
- **Status:** ready for execution.
- **Scope:** `src/tarav/indexlab/workspace.py` (`RecordStore` read/write paths) and focused
  tests in `tests/indexlab/test_workspace.py`.
- **Out of scope:** the Bloberia depot layout, the `Index.Record` model, projection, the
  linter, the CLI surface, and any change to `list`'s fail-closed contract.
- **Origin:** measured during the `index-2208` migration (`755`). Loading 5,047 records took
  roughly 25 minutes, degrading from ~150 records per 10s as the corpus grew.

## Impl.Index

### Problem

`append` computes the next ordinal with `self.list()`, which iterates the whole depot and
constructs an `IndexRecord` for **every stored record** — full model validation included —
then sorts them, in order to take one `max(ordinal)`. It also calls `self.get(record.id)`,
a separate depot query.

`append_many` calls `self.get` for every record up front, then calls `append` per record,
which repeats both the `get` and the full `list`.

For a batch of *n* records into a depot of *m*, that is `O(n·(n+m))` record constructions.
The 5,047-record migration paid roughly 12.7M record constructions to insert 5,047 rows.

### Decisions

- **One pass, not one pass per record.** Collect the existing id set and the maximum ordinal
  once per call, then assign ordinals incrementally from that seed. This reproduces the
  current numbering exactly, including the way records inserted earlier in a batch raise the
  ordinal for later ones.
- **Reading an ordinal must not require validating the corpus.** The ordinal seed reads raw
  cargo and never constructs an `IndexRecord`. Requiring the entire stored corpus to be
  model-valid before a single record can be appended is coupling with no justification, and
  it is the specific reason the migration was slow.
- **This is a deliberate behavior change and must be declared.** Today a single unloadable
  cargo makes `append` raise, because `list` fails closed. After this change `append`
  succeeds. Corruption detection belongs to `load` and the linter, which already report it
  properly as `CargoDefect`. A focused test declares the new constraint.
- **`list` keeps failing closed.** `test_load_reports_unloadable_cargo_instead_of_raising`
  pins that contract and it is not in scope here.
- **`list` and `load` share one reader.** `list` is `load` without defect tolerance; express
  both over a single private cargo-reading helper rather than two near-identical loops.
- **Rollback and batch semantics are unchanged.** Duplicate ids inside a batch, a non-zero
  incoming ordinal, an id already stored, and the delete-on-failure rollback all keep their
  current behavior and error text.

### Slices

1. **Shared reader.** Add a private helper that iterates depot cargo and yields
   `(record, defect)` outcomes. Re-express `list` (raise on first defect) and `load`
   (collect defects) over it. No public behavior change.
2. **Single-pass ordinal seed.** Add a private helper returning the stored id set and the
   maximum ordinal from raw cargo in one iteration, without constructing records.
3. **Rewrite `append` and `append_many`** over that seed, preserving numbering, validation
   order, error messages, and rollback.
4. **Tests.** Keep existing coverage green and add: appending into a depot that holds one
   unloadable cargo succeeds; a batch assigns consecutive ordinals continuing from stored
   records; batch rollback still removes partial inserts.

### Verification

- `uv run pytest tests/indexlab -q`
- `uv run pytest -q` (full suite; baseline 2272 passed)
- `uv run ruff check src tests`
- Re-load a slice of the `index-2208` manifest into a scratch workspace and confirm the
  per-record cost no longer grows with corpus size.
