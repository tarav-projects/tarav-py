# POIs and blessings

`POI` is the neutral point-of-interest base. Producing workflows define their
own concrete subtypes; POI does not prescribe checking, persistence, severity,
or response mechanics.

`IdentifiedPOI` adds stable concern and evidence-state identities. Its identity
groups the concrete POI Type and subject. Its state also includes the current
evidence. `POICollector` retains emitted POIs and provides filtered reports.

`NotificationPOI` is non-blocking. `emit_notification()` makes it visible as a
`POINotificationWarning` by default. `collect_notifications()` captures that
same emission without also warning.

Checks and blessings are separate workflows:

```python
class StaleOutput(CheckPOI, BlessablePOI):
    ...
```

`CheckPOI` binds an occurrence to the `Check` that explains it.
`BlessablePOI` marks, by inheritance, an identified evidence edition that may
receive an attributed blessing. A POI is not blessable unless its concrete
type inherits that capability. `BlessingStore` retains acceptance and
assessment Records without suppressing the POI.
