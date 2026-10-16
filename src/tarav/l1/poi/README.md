# POIs and blessings

`POI` is the neutral point-of-interest base: the statement that an event
happened, with a Type and an elementary message, as an error has. There are
no instruction fields.
<!-- tarav.breadcrumb e8473b22fc3ee0a455cbc39e008f48b457d5b1486ae3b6b608120a10e8ebbd1f -->

Producing workflows define their
own concrete subtypes; POI does not prescribe checking, persistence, severity,
or response mechanics.

`SituationPOI` adds a situation: an object that describes what was found, as
a `LiteRecord`. What goes into it is for each line of POIs to decide; no
structure is common to all of them. The same Type with the same situation is
the same POI, and that is its identity. The base holds nothing else. A
specialization adds what it needs as fields of its own Type, named for what
they hold: a `CheckPOI` adds its `check`, `details` and `failure`. Such
fields are never part of the identity. `POICollector` retains every emission and addresses
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
`BlessablePOI` marks, by inheritance, a POI whose action may be closed by a
blessing: closed although the situation still exists, with a reason. A POI
is not blessable unless its concrete type inherits that capability. The
`Blessing` is the closing record of the action; the POI is still raised.

A POI is a flag between detecting and working. It is momentary and owns
nothing: whether it is blessed, and how its action stands, is asked of the
Project that registered the action (`project.actions`), never of a POI
listing. `POICollector.report()` shows all emissions and says nothing about
actions.
<!-- tarav.breadcrumb 919ad0356a7b415abc1cb46bd0a15ef2478b17c468675dc3e5ed2c6440496cb1 -->
