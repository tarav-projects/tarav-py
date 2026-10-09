# POIs and blessings

`POI` is the neutral point-of-interest base: the statement that an event
happened, with a Type and an elementary message, as an error has. A Type may
add descriptive `context_notes`; they appear in the POI's context and are not
part of its record. There are no instruction fields.
<!-- tarav.breadcrumb e8473b22fc3ee0a455cbc39e008f48b457d5b1486ae3b6b608120a10e8ebbd1f -->

Producing workflows define their
own concrete subtypes; POI does not prescribe checking, persistence, severity,
or response mechanics.

`IdentifiedPOI` adds a stable identity derived from its concrete Type and an
explicit producer-supplied situation. Evidence and presentation do not create a
second identity axis. `POICollector` retains every emission and addresses
repeated observations through a collector-local emission index.

`NotificationPOI` is non-blocking. `emit_notification()` makes it visible as a
`POINotificationWarning` by default. `collect_notifications()` captures that
same emission without also warning.

No POI interrupts by itself. A caller that wants to stop calls `poi.throw()`,
available on every POI: it raises `POIError`, which carries the whole POI as
`.poi`, so whoever catches it still has the situation and its context.
<!-- tarav.breadcrumb 3fdc50f3f56f19e353058957f9ecde9403136681d3dd9b2a339e0c6792138402 -->
<!-- tarav.breadcrumb 9f6ed19f840ab6f7802c233860e111339115d0de49ff0a2030c6217de933cfa3 -->

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
