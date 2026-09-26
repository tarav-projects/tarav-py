# Application-owned POIs

Import `POI`, `POICollector`, and `BlessingStore` from `tarav.poi`. Define
subclasses beside the application's checks, with a unique `type_name` and
`type_ship`, a useful docstring, and optional `blessable = True`. The default
is non-blessable. `help()` resolves the class's own source path and line;
classes may extend it with documentation references. No central catalog edit
is needed to emit an application class. Register it explicitly with a Tarav
TypeRegistry when retained Record loading is needed.

```python
from tarav.kernel import TypeShip
from tarav.poi import POI, POICollector, BlessingStore

class DependencyReview(POI):
    """The dependency fingerprint differs from the reviewed baseline."""
    type_name = "Example.DependencyReview"
    type_ship = TypeShip("61722eae-56c5-4d07-8369-5f7a3259cd21")
    blessable = True

collector = POICollector()
finding = collector.emit(DependencyReview.finding(
    {"path": "src/module.py"},
    evidence={"observed_sha256": observed_hash, "current_sha256": current_hash},
))
store = BlessingStore(project / ".tarav" / "blessings")
report = collector.report(store=store, limit=20)
```

Emission returns a finding and continues. The application owns workflow
gating. `subject` identifies the occurrence; `evidence` contains the compared
state. Identity hashes class identity plus subject; state hashes that identity,
`check_version`, and evidence. Bump the class's `check_version` when its
evaluation contract changes. Callers must include every acceptance-relevant
state component in evidence. Inputs are copied as canonical JSON snapshots.

## Blessings and assessments

`store.bless(finding, actor=typed_reference, rationale=text, support=[...])`
records an explicit attributed acceptance of that exact state. A non-blessable
class is refused before writing. The store path is always caller-selected;
SKW selects `.skw/blessings/`. No source, baseline, or detector result changes.

Records are created as new UUID JSON files with exclusive creation. The store
never overwrites a previous action. Actor and support are typed references;
the generic store validates their shape, not their semantic truth or external
resolution. Applications can resolve those references using their registries.
No User approval or actual context loading is inferred from their presence.

`store.assess(blessing_id, actor=..., assertion="acceptance-justified",
score=0.8, rationale=..., support=[...])` appends a separate assessment Record.
It is an attributed score, not a verified truth flag or an automatic scorer.
All assessments remain visible; conflicting scores are not silently combined.
Missing `acceptance-justified` assessments produce `blessing-unassessed`;
scores below 0.5 produce `blessing-low-score`. These signals never erase the
blessing or convert the underlying check into a pass. Store corruption and
orphan assessments are surfaced without hiding detector findings.

Applicability is computed separately: `unblessed`, `blessed` for matching
state, `stale` when only previous states were accepted, or `disallowed` if the
current class no longer permits blessing. Each acceptance's original finding,
evidence, actor, rationale, support, timestamp, and scores remain inspectable.

## Navigation and presentation

The collector retains every emitted finding. `report()` defaults to all
classes and blessing standings, showing 20 compact rows with complete counts,
filter counts, and `next_offset`. Filters never change detection. Evidence is
omitted from compact rows; `collector.get(id).as_dict(detail=True)` expands it.
Rows expose class help for native file navigation. Blessing assessment counts
remain visible even when the corresponding instance is outside the page.

## SKW integration

`SkwSkill.evaluate()` returns the collector; `.report()` supplies its
blessing store. Domain classes live at `tarav.skw.pois`, separate from the
workflow-neutral primitives. Annotation omissions, stale maintenance context,
and stale generation currently allow explicit acceptance; structural and
loading-contract violations require correcting the analyzed surface.

SKW fingerprints its declared source/product/lock state, and includes resolved
generation context/input fingerprints for semantic freshness findings. This is
conservative: unrelated package edits can make an acceptance stale. Blessing
does not advance any source, generation, or context baseline.

```sh
tarav skw skills check --project /path/to/skill --limit 10 --offset 0
tarav skw skills check --project /path/to/skill --blessing-status blessed
tarav skw skills poi --project /path/to/skill --id FINDING_ID
tarav skw skills bless --project /path/to/skill --id FINDING_ID \
  --actor-file actor-reference.json --rationale-file rationale.txt
tarav skw skills assess-blessing --project /path/to/skill \
  --blessing-id BLESSING_UUID --actor-file evaluator-reference.json \
  --assertion acceptance-justified --score 0.8 --rationale-file assessment.txt
```

Both action commands optionally accept `--support-file` containing an array of
typed evidence references. They never invent actor identity, rationale, or
assessment. The `poi` command expands current evidence and retained blessing
records. Check/build/deploy CLI reports support `--class-name`,
`--blessing-status`, `--offset`, and `--limit`. Findings, including blessed
ones, retain exit status 1; consumers decide which to act on. Compilation and
deployment are not gated by ordinary findings. Mechanical impossibility still
prevents an operation from completing. Older unrelated POI workflows remain
separate consumers; this slice adds no legacy adapters.
