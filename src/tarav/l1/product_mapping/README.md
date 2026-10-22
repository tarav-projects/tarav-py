# Product Mapping

Product Mapping maintains product-agnostic coordinates in committed Git states.
It does not parse classes or document structure and does not record user reviews.
A chunk ID persists only through explicit maintainer continuity decisions.
<!-- tarav.breadcrumb 609e7c987cac -->

## Data and boundaries

Each confirmed ProductMap records a repository identity, exact commit and tree,
previous map, actor, reason, confirmation time, chunks and continuity decisions.
A chunk version records a UUID, file path, blob OID, half-open byte range and
SHA-256 fingerprint. A fingerprint identifies content state, never continuity.
All selected regular files, including binary and empty files, are covered once.
Symlinks and submodules are listed as skipped; their targets are never read.
The stream's include/exclude globs are fixed at explicit creation.

Initial chunks have a target byte size and optional forward boundary flexibility
that prefers whitespace. This is a heuristic, not a word/UTF-8/syntax boundary
guarantee. Maintained chunks can grow or shrink; they are not periodically
repartitioned. Consumers retrieve exact bytes from the retained Git blob.
<!-- tarav.breadcrumb 08083a49af42 -->

## Agent maintenance loop

1. Open an explicitly identified repository. Create its mapping track once.
   Reads, checks and proposals never initialize storage implicitly.
2. Select a target commit. The map can jump across many intermediate commits.
3. Produce a proposal. Exact blobs carry candidates forward. Endpoint line
   alignment and Git rename evidence propose coordinates for edited/moved files.
   Large surfaces use bounded block alignment. Edited spans use proportional
   candidate boundaries. None of this certifies semantic continuity.
4. Inspect `changes`, endpoint diffs and any intermediate history useful to the
   decision. Edit the proposal's chunks if needed. Do not accept ambiguous
   identity based only on an algorithm's suggestion.
5. Write explicit decisions and confirm as the actual actor (`agent:...` or
   `user:...`). Agent confirmation never claims user review or approval.
6. Audit exact file inventory, byte coverage, blob OIDs and fingerprints. Old
   confirmed maps remain addressable; map IDs and retired chunk IDs are not reused.
<!-- tarav.breadcrumb 0edfd046cad2 -->

Each decision contains `source_ids`, `target_ids` and `reason`. Keeping an ID
relates that old ID to itself. Empty source creates new IDs; empty target retires
old IDs. One-to-many with fresh IDs records a split; many-to-one with a fresh
ID records a merge. Replacement can relate an old ID to a new ID. Every changed
source and target must occur in exactly one decision; unchanged chunks need
no separate decision. A stream that advanced rejects an old proposal. Confirmation
validates the complete proposed state before writing an immutable map Record,
then advances the tracker. Interrupted writes can leave an unreferenced map
Record; they never make an incomplete map current. Retain it for investigation.

## Library and CLI

`ProductMapper(repository, repository_id, root=None)` uses the standard Record
Registry partition of ProductMappingWorkflow unless a partition is selected.
`create`, `propose`, `changes`, `confirm`, `latest`, `load`, `history` and `audit`
are the Python interface. `mapper.product.checkpoints(target, every=10)` selects
the first commit, every tenth subsequent first-parent commit and the final
target. `after=commit` resumes after a mapped checkpoint.

The CLI mirrors those operations under `tarav product-map`. Each leaf takes
`--repo PATH --repository-id ID` and an optional `--store PARTITION`.

```text
tarav product-map init ... --target-bytes 4096 --boundary-bytes 256
tarav product-map checkpoints ... --commit HEAD --every 10
tarav product-map propose ... --commit COMMIT --output /tmp/proposal.json
tarav product-map changes ... --proposal /tmp/proposal.json
tarav product-map confirm ... --proposal /tmp/proposal.json \
  --decisions /tmp/decisions.json --actor agent:SESSION --reason 'Inspected transition'
tarav product-map show ... --json
tarav product-map history ...
tarav product-map audit ... --all
```

The ellipsis stands for the common explicit repository/identity/store arguments.
Proposals and decision files are ordinary editable JSON; their Type is validated.
`show --json` returns the full Record; ordinary `show` returns a compact summary.

## Project maintenance policy

Featured Projects select a Mapping manager (`project.mapping`). Its `open()`
uses the existing Git repository identity binding and its `suite()` contributes
the independent ProductMappingSuite. Extend `Project.Mapping` to change that
integration. Minimal TaravProject does not depend on the mapping workflow.

Opt in through `.tarav/config.json` with
`"product_mapping": {"enabled": true, "max_age_days": 5}`.
The freshness age is elapsed time since the latest map's confirmation, not its
target commit's authored date. A missing map is due immediately. An existing
map becomes due only when committed HEAD differs and that confirmation is old
enough. Working-directory edits are ignored. Normal Project status opens one
workflow-owned update action; a current map closes it and later due work reopens
the same action. Disabled/unavailable scans cannot establish disappearance.
On-demand mapping has no freshness restriction.
<!-- tarav.breadcrumb 77bdc4d8861d -->

## Historical exercise

`tooling/map_product_history.py` is an explicit operational Agent policy, separate
from the workflow's default mechanics. Without `--apply` it lists checkpoints.
Application requires an `agent:` actor and a report path. Exact content carries
forward except ambiguous cross-file matches. Edited candidates retain IDs only
with at least 80% matching-byte evidence; weaker candidates receive fresh IDs,
and oversized edited ranges can split. This is a declared Agent inference,
not a claim of semantic equivalence or User review. Every decision is retained
on its confirmed map. The report records alignment evidence and independent
exact coverage audits, and the driver resumes from the latest mapped checkpoint.
<!-- tarav.breadcrumb 43ec1726a3f8 -->
