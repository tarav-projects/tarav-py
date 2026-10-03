# POIs and blessings

`POI` is the neutral point-of-interest base. Producing workflows define their
own concrete subtypes; POI does not prescribe checking, persistence, severity,
or response mechanics.

`IdentifiedPOI` adds a stable identity derived from its concrete Type and an
explicit producer-supplied situation. Evidence and presentation do not create a
second identity axis. `POICollector` retains every emission and addresses
repeated observations through a collector-local emission index.

`NotificationPOI` is non-blocking. `emit_notification()` makes it visible as a
`POINotificationWarning` by default. `collect_notifications()` captures that
same emission without also warning.

Checks and blessings are separate workflows:

```python
class StaleOutput(CheckPOI, BlessablePOI):
    ...
```

`CheckPOI` binds an occurrence to the `Check` that explains it.
`BlessablePOI` marks, by inheritance, an identified situation that may
receive an attributed blessing. A POI is not blessable unless its concrete
type inherits that capability. `BlessingStore` retains acceptance and
assessment Records without suppressing the POI.

`tarav.l2.blessings.attention_report` is a separate, pageable view of a
`POICollector` evaluation. It selects currently due POIs for an agent while
`POICollector.report()` continues to show all emissions. A missing POI has no
attention schedule, and `show_all` or `force_review` can expose deferred POIs.
<!-- tarav.breadcrumb 919ad0356a7b415abc1cb46bd0a15ef2478b17c468675dc3e5ed2c6440496cb1 -->
