# POI workflow

Consumers subclass `POICheck` (or the existing `POI` declaration) and define
their class entity. They own detection; this package supplies no check runner.

```python
finding = MyCheck.finding({"path": "notes/a.md", "line": 12}, evidence={"text": "..."})
runtime.pois.emit(finding)  # Non-throwing, no persistence.
runtime.context(finding).open("check")
runtime.context(finding).open("coordinate")
runtime.context(finding).open("evidence")
# finding.error() explicitly raises POIError carrying finding as .poi.
```

`POIFinding` is a `POIInstance`, an identified Tarav Entity. The existing
`identity` hash groups a check and its subject/coordinate. Its deterministic
UUID Ship is `.id`. Evidence and check version determine `.state`, not identity.
Repeated emissions remain in the collector; these are not separate event IDs.
Report `id` retains the grouping hash; `entity_id` exposes the Ship.

Records retain the check's class entity, coordinates, evidence, version, and
source/help snapshot. Loading never imports a retained Python path. Use
`finding.resolve_check(runtime.records)` to resolve the live check through
trusted registration by Type Ship. A loaded finding's blessing policy is the
retained policy, not a fresh check execution; evaluate again for current policy.

`runtime.blessings` addresses `<archive-root>/<POIWorkflow Ship>/blessings`.
Reads create nothing. `BlessingStore(path)` still supports consumer-owned
locations; `BlessingStore.from_archive(archive_root_object)` addresses the
shared partition. Existing blessing JSON and finding hashes remain valid.

Blessings and assessments are extensible identified FileRecords. Register
subtypes with the runtime or `BlessingStore(..., record_types=(MyBlessing,))`.
Override Record validation for subtype constraints and
`BlessingRecord.assessment_findings(assessments)` for assessment obligations.
`bless`/`assess` accept `record_type`; `add(object)` supports additional subtype
fields. `load(id)` returns the typed object. Unknown records are reported, not
imported, repaired, or hidden. Blessing never suppresses detection.
