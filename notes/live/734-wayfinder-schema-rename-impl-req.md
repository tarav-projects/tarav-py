# Wayfinder schema rename - agentos.* to tarav.* - impl record

## Impl.Abstract

First of the deferred serialized-id renames (note 532, carried-forward item 3). Wayfinder was chosen
because it is the one subsystem where the rename costs almost nothing, and the caller's instinct to
start there was right.

## Why wayfinder was cheap

Serialized ids are normally expensive because they are written into data already on disk and the
readers compare them by exact equality - `agentos.project` sits in 55 project markers,
`agentos.agent.usage-record` in 238,818 usage records. Renaming the constant does not rename the
data; it invalidates it.

Wayfinder does not have that problem:

- `REGISTRY_SCHEMA` - one file, five entries.
- `REFERENCE_SCHEMA` - **not persisted at all**. References are constructed at runtime. The only
  on-disk occurrences were the source, one hook context sample, and chatlas transcripts, none of
  which are read back as references.

## Decided before acting

- **Straight prefix swap, keep `.v1`.** `tarav.wayfinder.registry.v1`. The shape did not change, only
  the vendor; bumping to `.v2` would advertise a schema change that did not happen. This sets the
  convention for the remaining 25 ids.
- **Archive, do not migrate in place.** The old registry is copied to
  `~/.tarav/wayfinder/archive/registry-agentos-schema-20260814.json` (SHA-256 verified identical),
  then the live registry starts empty and is repopulated by registration.

## Verified before committing to the approach

An empty registry was tested through `TARAV_WAYFINDER_REGISTRY` before anything was changed:

- `wayfinder check` -> `status: ok`, 0 diagnostics
- `index linter` runs unchanged
- an unregistered root fails *informatively* - `situation: "no Wayfinder registration for root..."`,
  `evidence.kind: "missing"`, `trace: [{stage: registry.lookup, status: missing}]`

So the failure mode names the root it wanted, which is what makes "register as they come up" viable.

## Execution

1. Archived the registry (byte-identical copy).
2. Renamed both constants.
3. Deleted the live registry; confirmed `check` still `ok` with nothing registered.
4. Re-registered all five roots with `tarav wayfinder register`, correcting the relocation hints,
   which still said "in the agentos-project repository".

| root | path |
|---|---|
| `tarav-pkg` | `tarav-md/skills/tarav-pkg` |
| `tarav-hugentics` | `tarav-md/skills/tarav-hugentics` |
| `tarav-chatlas-pkg` | `tarav-chatlas-md/skills/tarav-chatlas-pkg` |
| `tarav-canvas-pkg` | `tarav-canvas-md/skills/tarav-canvas-pkg` |
| `md-library-pkg` | `Documents/md-library/skills/md-library-pkg` |

## Acceptance

- registry `schema: tarav.wayfinder.registry.v1`, 5 entries, all paths resolving
- `wayfinder check` -> ok, 0 diagnostics, 0 POIs
- `wayfinder resolve index://tarav-pkg/Index.Linter` returns a reference carrying
  `schema: tarav.wayfinder.reference.v1`
- `index linter --depot skills/tarav-pkg` runs; warning count identical with the registry empty and
  full, confirming the rename does not move it
- suite **1900 passed**

## The archive is a keepsake, not a rollback

Demonstrated rather than assumed: pointing `TARAV_WAYFINDER_REGISTRY` at the archived file now raises
`CorruptWayfinderRegistry: invalid Wayfinder registry schema`. The readers compare schema by exact
equality, so the retired id cannot be loaded by the new code. The archive's value is that five
entries can be re-registered from it by hand, not that it can be restored.

The test suite states this deliberately: `test_wayfinder.py` keeps `agentos.wayfinder.reference.v1`
as a **rejection** case, so the retired schema failing to parse is an asserted property rather than
an accident.

## Left for later

The other 25 serialized ids (`agentos.project`, `agentos.global.config`, `agentos.daemon-event`,
`agentos.index-line-*`, `agentos.agent.usage-record`, ...). None of them are as cheap as this one -
each is written into live data that readers validate by exact equality, so each needs either a
migration pass or a dual-accept transition. `agentos.skills.routing-state` left the list on its own
when the routing registry was deleted.
