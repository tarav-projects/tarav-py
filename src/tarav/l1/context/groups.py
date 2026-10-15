"""The objects that belong together, opened from any of them.

An object does not list its relations itself. Each workflow registers, for
the Types it owns, a function naming the links of one object: pairs of
members, upstream first. The `ObjectGroup` view follows those links from the
subject until no new member appears, so every member opens the same group,
in the same order.

A member is what is known of an object: its role, its Type, its id or key,
or its value when it has no Type. A member with a live object attached is
followed further; one without (a check known only by its Type) is not.
Building a group reads what is there; it never runs anything.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from tarav.l0.kernel.identity import TypeShip
from tarav.l0.kernel.records import TaravClass, TaravObject, entity

from . import CONTEXT_WORKFLOW_SHIP, ContextFolder, ContextViewEntry


# tarav.breadcrumb a2790b232f6f2badcfb8e0d1a6978a2137b26a8123bc81d57cea48e60e543981
class Member(TaravObject):
    """One member of an object group: its role, and what is known of it."""

    class RecordInterface(TaravObject.RecordInterface):
        role: str
        member_type: str | None = None
        id: str | None = None
        key: str | None = None
        value: object = None

    def __init__(self, role: str, *, member_type: str | None = None, id: str | None = None,
                 key: str | None = None, value: object = None,
                 obj: TaravObject | None = None) -> None:
        super().__init__()
        if not isinstance(role, str) or not role:
            raise ValueError("A member has a role")
        self.role, self.member_type, self.id, self.key, self.value = role, member_type, id, key, value
        self.obj = obj  # the live object, followed for more links; never recorded

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("5b0c7e2a-9d41-4f8e-a6b3-1c2d8e7f4a90"),
                          name="Tarav.Context.Group.Member", workflow=CONTEXT_WORKFLOW_SHIP)

    @classmethod
    def _from_record(cls, data):
        return cls(data.role, member_type=data.member_type, id=data.id, key=data.key, value=data.value)

    def _to_record(self):
        fields = {"role": self.role, "member_type": self.member_type, "id": self.id, "key": self.key,
                  "value": self.value}
        return {**super()._to_record(),
                **{name: value for name, value in fields.items() if value is not None}}

    def identity(self) -> tuple:
        """Two members are the same when these are; a member without Type, id or key
        is told by its value."""
        if self.member_type is None and self.id is None and self.key is None:
            return (self.role, json.dumps(self.value, sort_keys=True, default=str))
        return (self.role, self.member_type or "", self.id or "", self.key or "")

    class Records(TaravObject.Records):
        def record_example(self) -> dict[str, object]:
            return {"type": entity(self._owner).name, "role": "poi",
                    "member_type": "Tarav.POI", "id": "0" * 64}


@dataclass(frozen=True)
class Link:
    """`upstream` comes before `downstream` in the group."""

    upstream: Member
    downstream: Member


LinksFunction = Callable[[TaravObject], Iterable[Link]]
_LINKS: dict[type, list[LinksFunction]] = {}


def register_links(subject_type: type, links: LinksFunction) -> None:
    """Name the links of every object of this Type and its subclasses. Explicit:
    the runtime registers each workflow's functions."""
    if not isinstance(subject_type, type) or not issubclass(subject_type, TaravObject):
        raise TypeError("Links are registered for a TaravObject Type")
    registered = _LINKS.setdefault(subject_type, [])
    if links not in registered:
        registered.append(links)


def _functions(subject: object) -> list[LinksFunction]:
    return [function for cls in type(subject).__mro__ for function in _LINKS.get(cls, ())]


def members(subject: TaravObject) -> tuple[Member, ...]:
    """The group of the subject: every member reached through links, upstream first.

    Ties are broken by role, Type, id and key, never by where the walk began.
    """
    found: dict[tuple, Member] = {}
    edges: set[tuple[tuple, tuple]] = set()
    followed, pending = [subject], [subject]
    while pending:
        current = pending.pop(0)
        for function in _functions(current):
            for link in function(current):
                ends = []
                for member in (link.upstream, link.downstream):
                    key = member.identity()
                    known = found.setdefault(key, member)
                    if known.obj is None and member.obj is not None:
                        known.obj = member.obj
                    if known.obj is not None and not any(known.obj is seen for seen in followed):
                        followed.append(known.obj)
                        pending.append(known.obj)
                    ends.append(key)
                edges.add((ends[0], ends[1]))
    return tuple(found[key] for key in _ordered(found, edges))


def _ordered(found: dict[tuple, Member], edges: set[tuple[tuple, tuple]]) -> list[tuple]:
    incoming = {key: {up for up, down in edges if down == key and up != key} for key in found}
    placed: list[tuple] = []
    while len(placed) < len(found):
        ready = sorted(key for key in found if key not in placed and not incoming[key] - set(placed))
        # a cycle has no ready member: place the rest by their identity
        placed.append(ready[0] if ready else sorted(set(found) - set(placed))[0])
    return placed


# tarav.breadcrumb c495fca19b50a25f36ee90e2d7f906c4796455a980139b8f8e2133fccf65a364
# tarav.breadcrumb 13d3aca58a26c58304d80fc28c9f752c0140e7d2ff8e032e798c7ce6f381e380
class ObjectGroup(ContextFolder):
    """The objects that belong together with the subject, one entry per member.

    Entries are named by role, upstream first; a role held by several members
    is numbered in that order (`suite-1`, `suite-2`). Each opens its Member.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("d7e3a1f4-62b8-4c09-9e5d-3a7b0c4f1e26"),
                          name="Tarav.Context.ObjectGroup", workflow=CONTEXT_WORKFLOW_SHIP)

    @classmethod
    def accepts(cls, scope):
        # tarav.context 473c89a0:926997d41da95b26
        return not scope.views and isinstance(scope.subject, TaravObject) and bool(_functions(scope.subject))

    @classmethod
    def for_context(cls, current):
        subject = current.subject
        group = members(subject)

        def populate(builder) -> None:
            for name, member in _names(group):
                builder.add(name, opener=lambda member=member: member,
                            description=member.member_type or "")

        return cls(subject, populate)

    @property
    def members(self) -> tuple[Member, ...]:
        return tuple(entry.open() for entry in self.ls() if not isinstance(entry, ContextViewEntry))


def _names(group: tuple[Member, ...]) -> list[tuple[str, Member]]:
    counts: dict[str, int] = {}
    for member in group:
        counts[member.role] = counts.get(member.role, 0) + 1
    seen: dict[str, int] = {}
    named = []
    for member in group:
        if counts[member.role] == 1:
            named.append((member.role, member))
            continue
        seen[member.role] = seen.get(member.role, 0) + 1
        named.append((f"{member.role}-{seen[member.role]}", member))
    return named


GROUP_RECORD_TYPES = (Member, ObjectGroup)

__all__ = ["GROUP_RECORD_TYPES", "Link", "LinksFunction", "Member", "ObjectGroup",
           "members", "register_links"]
