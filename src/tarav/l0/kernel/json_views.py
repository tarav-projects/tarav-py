"""Declaration-only schema projections; no instance construction or descriptor access."""
# tarav.breadcrumb 6494535db5dc

import inspect


def _annotation(value):
    return {} if value is inspect.Signature.empty else {
        "x-python-annotation": value if isinstance(value, str) else inspect.formatannotation(value)}


def default_view_schemas(cls):
    record = cls.RecordInterface.model_json_schema(by_alias=True)
    # RecordInterface validates payload fields; Type dispatch is a separate boundary.
    record.setdefault("properties", {}).setdefault("type", {"description": "Tarav Type reference"})
    properties = {}
    for base in reversed(cls.__mro__):
        for name, annotation in inspect.get_annotations(base, eval_str=False).items():
            if not name.startswith("_"):
                properties[name] = _annotation(annotation)
    for name, parameter in inspect.signature(cls.__init__).parameters.items():
        if name not in {"self", "cls"} and parameter.kind not in {
                inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}:
            properties.setdefault(name, _annotation(parameter.annotation))
    for name in dir(cls):
        if name.startswith("_"):
            continue
        member = inspect.getattr_static(cls, name)
        if isinstance(member, property):
            result = inspect.signature(member.fget).return_annotation if member.fget else inspect.Signature.empty
            properties[name] = {**properties.get(name, {}), **_annotation(result),
                                "readOnly": member.fset is None}
    return {"record": record, "instance": {
        "type": "object", "properties": properties, "additionalProperties": True,
        "x-tarav-completeness": "partial",
        "description": "Declared attributes, properties and constructor parameters; override for exact instance semantics.",
    }}
