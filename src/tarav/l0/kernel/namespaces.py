"""Bound object namespaces and explicit multiple-inheritance composition."""

from __future__ import annotations

from typing import Generic, TypeVar


ObjectT = TypeVar("ObjectT")


class NamespaceBase(Generic[ObjectT]):
    """A stateless view over an object, selected by the object's class."""
    # tarav.breadcrumb 3cc628c57d71d6c0514781e1c43d1e08803bdce35839ba6febca60bdba0c9d4c

    def __init__(self, obj: ObjectT) -> None:
        self.obj = obj


def check_namespace_composition(cls: type) -> None:
    """Reject a selected namespace that drops a direct base's contribution.

    Python selects the first matching class attribute in the host MRO. When
    independent bases contribute the same namespace, the host must select a
    namespace subclassing both contributions explicitly.
    """
    # tarav.breadcrumb 14f5a85ca8f89e7351ec63e3b8d4d77298fff6b0151e5111ebc539c487192509

    contributions: dict[str, set[type[NamespaceBase]]] = {}
    for base in cls.__bases__:
        for ancestor in base.__mro__:
            for name, value in vars(ancestor).items():
                if isinstance(value, type) and issubclass(value, NamespaceBase):
                    contributions.setdefault(name, set()).add(value)

    for name, parents in contributions.items():
        selected = getattr(cls, name, None)
        if not isinstance(selected, type) or not issubclass(selected, NamespaceBase):
            raise TypeError(f"{cls.__name__}.{name} must select a NamespaceBase")
        missing = [parent for parent in parents if not issubclass(selected, parent)]
        if missing:
            names = ", ".join(sorted(parent.__qualname__ for parent in missing))
            raise TypeError(
                f"{cls.__name__}.{name} drops namespace contribution(s): {names}"
            )
