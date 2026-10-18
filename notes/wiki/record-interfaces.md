# Record interfaces

<!-- tarav.sessions
1f561f5d = codex:01a0b984-4664-7871-934a-89cf92595b64 @1f561f5d8db849a3a445b83a91a5e94acbb80927f9c332d45322ac70f8705a74
-->

## Object boundary

Meaningful Tarav data with an independent semantic type and standalone representation should derive from `TaravObject`. Structural records that exist only as parts of another object do not need artificial type identities, registration, or dispatch.
<!-- tarav.breadcrumb 93af33f9958b -->
<!-- tarav.breadcrumb e73fd0ea7554 -->

## Interface root

`TaravObject.RecordInterface` is the root of all Tarav record interfaces, including reusable interfaces for embedded records. There is no additional top-level `RecordInterface` above it.
<!-- tarav.breadcrumb ede7da11680f -->
<!-- tarav.breadcrumb 929380c4c75f -->

An embedded record interface therefore has this form:

```python
class SupportMemberInterface(TaravObject.RecordInterface):
    kind: str
    identity: str
```

The inheritance says that `SupportMemberInterface` participates in Tarav's structural record contract. It does not make the interface a `TaravObject`: it has no `type_ship`, registry entry, semantic dispatch, or object behavior.
<!-- tarav.breadcrumb c55638bd2758 -->
<!-- tarav.breadcrumb 68e0d8a81b69 -->

Complete object records remain nested on their semantic classes and inherit through the object hierarchy:

```python
class LineSupportAnnotation(TypedAnnotation):
    class RecordInterface(TypedAnnotation.RecordInterface):
        support: tuple[SupportMemberInterface, ...]
```

Reusable embedded interfaces live at module scope. Plain Pydantic `BaseModel` remains appropriate for validation models that do not describe any part of a retained Tarav record.
<!-- tarav.breadcrumb e2eebc86adda -->
<!-- tarav.breadcrumb c7e78ca51d73 -->

## Loading a Record — 921

<!-- tarav.sessions
3537df0a = claude-code:2bff854f-66a0-4e8c-8f96-9078af34c479 @3537df0a6015d884a94e9594478f971cb92e38df63776b87b5eea38741740d8a
-->

The record data is not the runtime source of truth. Instances can exist
without ever producing a record; the record is only for loading and creating
an instance. Types are full classes: their state does not live on a record
because that is how they are loaded or stored. `_record` is gone; the
`.records` namespace and the builder, record provider and record example
provider hooks stay.
<!-- tarav.breadcrumb 75ece1d801cf -->
<!-- tarav.breadcrumb b18ffdd4015c -->

Loading is a parsing step, from the raw JSON dict to typed data, not only
validation. It is a standard pipeline up to the Type's constructor, the
official road from a record but not the only way to an instance. The pipeline
fills a `RecordLoadingContext` step by step and carries the configuration the
steps react to; the builder receives a `LoadedRecord`, the pydantic model
itself plus loading metadata (by default `source`) that the loading system
chooses to give. An internal path returns the context of a failed load; the
public path raises.
<!-- tarav.breadcrumb e5f66d6694a4 -->
<!-- tarav.breadcrumb 95b120896a23 -->
<!-- tarav.breadcrumb 55d074a51e00 -->

Only pydantic stays at runtime, used as an accept/reject gate on the original
dict. The earlier "RecordInterface must not transform or discard supplied
data" comparison had no User grounding: on 2026-09-19 the User had asked for a
round-trip test per registered class, not a runtime check. Check levels
(none, lite, default, full) are Type-defined, configured on the loading
machinery, and never pass the loading phase; a separate check guards writing.
<!-- tarav.breadcrumb cbb211e47640 -->
<!-- tarav.breadcrumb 18698a7e8f7f -->
<!-- tarav.breadcrumb 01e71c68fd20 -->
