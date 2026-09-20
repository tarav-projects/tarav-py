# Record interfaces

<!-- tarav.sessions
1f561f5d = codex:01a0b984-4664-7871-934a-89cf92595b64 @1f561f5d8db849a3a445b83a91a5e94acbb80927f9c332d45322ac70f8705a74
-->

## Object boundary

Meaningful Tarav data with an independent semantic type and standalone representation should derive from `TaravObject`. Structural records that exist only as parts of another object do not need artificial type identities, registration, or dispatch.
<!-- tarav.context 1f561f5d:6f31163c2575c733 -->
<!-- tarav.context 1f561f5d:ddbd1eb05d89f06d -->

## Interface root

`TaravObject.RecordInterface` is the root of all Tarav record interfaces, including reusable interfaces for embedded records. There is no additional top-level `RecordInterface` above it.
<!-- tarav.context 1f561f5d:980668db41183f07 -->
<!-- tarav.context 1f561f5d:3e139040afacf22e -->

An embedded record interface therefore has this form:

```python
class SupportMemberInterface(TaravObject.RecordInterface):
    kind: str
    identity: str
```

The inheritance says that `SupportMemberInterface` participates in Tarav's structural record contract. It does not make the interface a `TaravObject`: it has no `type_ship`, registry entry, semantic dispatch, or object behavior.
<!-- tarav.context 1f561f5d:e2aa5b6a7d9dab1c -->
<!-- tarav.context 1f561f5d:3e139040afacf22e -->

Complete object records remain nested on their semantic classes and inherit through the object hierarchy:

```python
class LineSupportAnnotation(TypedAnnotation):
    class RecordInterface(TypedAnnotation.RecordInterface):
        support: tuple[SupportMemberInterface, ...]
```

Reusable embedded interfaces live at module scope. Plain Pydantic `BaseModel` remains appropriate for validation models that do not describe any part of a retained Tarav record.
<!-- tarav.context 1f561f5d:e2aa5b6a7d9dab1c -->
<!-- tarav.context 1f561f5d:3e139040afacf22e -->
