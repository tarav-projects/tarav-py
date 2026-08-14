# $kw: ^tournament-frame --from Match.Frame --from Match.Template --from Match.Component.Registry --note [DF] a Match.Frame is the definition's typed composable description of one match prompt, built from a closed set of content nodes and a closed set of engine-applied operations --supp ^<anchor-on-landing>
"""The typed material a definition composes into one match prompt.

A definition used to hand the engine strings: a ``question``, an optional
``criteria``, and one opaque presentation per player. Strings are renderable and
nothing else — there is nowhere to put material shared by the whole match, no way
to validate what a definition built, and no way for the engine to apply a generic
operation to it.

A ``Match.Frame`` is the replacement: an ordered composition of typed nodes.

**Content is open, operations are closed.** New material composes out of the node
types below without touching the engine. Operations cannot, because every one of
them needs engine machinery — seeding, recording, reproducibility. An operation
the engine cannot record is a hole in the instrument, so ``shuffle`` is the whole
set until something earns a second entry.

**The node types are structural, not domain-named.** There is no ``Question``
type carrying "questionness" and no ``Glossary`` type — there is a ``Table``, and
what it means is its label. Naming instances as types is exactly what made the
three-section template inextensible.

**The engine owns the roster; the definition owns the card.** ``Players`` is a
placeholder, never a list a definition fills. Control substitution, sampling, and
position labelling stay engine work.

Every node addresses under the hash of ``(type, version, payload)``. The version
is inside the hash because a node type whose rendering changes must not rebuild an
old verdict into text its judge never saw.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Mapping, Sequence as SequenceABC
from dataclasses import dataclass, field
from typing import Union

from tarav.tournament.model import TournamentError

FRAME_VERSION = 1


class FrameError(TournamentError):
    """A frame is not something the engine can render or record."""


# --------------------------------------------------------------------------
# Nodes
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Node:
    """Base of the closed node vocabulary. Subclasses declare TYPE and VERSION."""

    TYPE = "node"
    VERSION = 1

    def payload(self) -> dict[str, object]:  # pragma: no cover - abstract
        raise NotImplementedError

    def to_dict(self) -> dict[str, object]:
        return {"type": self.TYPE, "version": self.VERSION, **self.payload()}


@dataclass(frozen=True)
class Text(Node):
    """A block of prose. The default shape of anything a definition writes."""

    TYPE = "text"

    body: str

    def payload(self) -> dict[str, object]:
        return {"body": self.body}


@dataclass(frozen=True)
class Raw(Node):
    """Material the vocabulary cannot express, rendered exactly as supplied.

    The escape hatch is named so that leaving the language is *visible*. Without
    one, the material that does not fit gets smuggled into a ``Text`` and reads
    as structured when it is not.
    """

    TYPE = "raw"

    body: str

    def payload(self) -> dict[str, object]:
        return {"body": self.body}


@dataclass(frozen=True)
class Table(Node):
    """A named lookup: keys to material, cited by key from elsewhere in the frame.

    Order is presentational by default, which is what makes a table shufflable —
    listing order in a lookup carries no meaning and removing it closes an
    inference channel. A table whose order *is* meaning declares ``ordered=True``
    and the engine refuses to shuffle it rather than silently destroying it.
    """

    TYPE = "table"

    name: str
    entries: tuple[tuple[str, "FrameNode"], ...] = ()
    ordered: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", _normalized_entries(self.entries))

    def keys(self) -> tuple[str, ...]:
        return tuple(key for key, _ in self.entries)

    def payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "ordered": self.ordered,
            "entries": [[key, node.to_dict()] for key, node in self.entries],
        }


@dataclass(frozen=True)
class Sequence(Node):
    """An ordered list. Ordered by construction, so it is never shufflable."""

    TYPE = "sequence"

    items: tuple["FrameNode", ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "items", tuple(_as_node(item) for item in self.items))

    def payload(self) -> dict[str, object]:
        return {"items": [item.to_dict() for item in self.items]}


@dataclass(frozen=True)
class Section(Node):
    """A labeled group. The label is what a reader calls the material inside it."""

    TYPE = "section"

    label: str
    body: tuple["FrameNode", ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "body", tuple(_as_node(item) for item in self.body))

    def payload(self) -> dict[str, object]:
        return {"label": self.label, "body": [item.to_dict() for item in self.body]}


@dataclass(frozen=True)
class Cite(Node):
    """A reference into a named ``Table`` by key.

    It renders as the bare key. The material lives in the table, once per match,
    instead of being copied into every card that mentions it. An unresolvable
    cite is refused when the frame is validated — before a spawn is paid for.
    """

    TYPE = "cite"

    table: str
    key: str

    def payload(self) -> dict[str, object]:
        return {"table": self.table, "key": self.key}


@dataclass(frozen=True)
class Players(Node):
    """Where the match's candidates go. A placeholder, never a list.

    A definition that could supply this list could substitute away a control or
    relabel a position, so it does not get to. It declares the card; the engine
    decides who fills it.
    """

    TYPE = "players"

    def payload(self) -> dict[str, object]:
        return {}


@dataclass(frozen=True)
class Shuffle(Node):
    """Permute the wrapped node's children, seeded and recorded by the engine.

    A definition that shuffled with ``random`` would produce a match nobody can
    reproduce and an order recorded nowhere. Declaring the operation is what lets
    the engine seed it from the match, write the realized permutation beside the
    verdict, and rebuild the exact prompt later.
    """

    TYPE = "shuffle"

    node: "FrameNode" = field(default_factory=lambda: Text(""))

    def __post_init__(self) -> None:
        object.__setattr__(self, "node", _as_node(self.node))
        if isinstance(self.node, Sequence):
            raise FrameError(
                "shuffle refuses a sequence: a sequence is ordered by "
                "construction, so permuting it destroys its content"
            )
        if isinstance(self.node, Table) and self.node.ordered:
            raise FrameError(
                f"shuffle refuses table {self.node.name!r}: it declares "
                "ordered=True, so its order is meaning rather than presentation"
            )
        if not isinstance(self.node, (Table, Section)):
            raise FrameError(
                f"shuffle expects a table or a section, got {self.node.TYPE!r}; "
                "there is nothing to permute in a leaf node"
            )

    def payload(self) -> dict[str, object]:
        return {"node": self.node.to_dict()}


FrameNode = Union[Text, Raw, Table, Sequence, Section, Cite, Players, Shuffle]

_LEAF_TYPES = (Text, Raw, Cite, Players)


# --------------------------------------------------------------------------
# The frame
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Frame:
    """One match prompt described as data.

    Two requirements are structural rather than conventional. ``question`` is the
    judge's task and every match has exactly one. ``Players`` must appear exactly
    once, because a frame with none renders a prompt with no candidates and a
    frame with two would ask the engine which position labelling is real.
    """

    question: str
    nodes: tuple[FrameNode, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", tuple(_as_node(node) for node in self.nodes))
        validate_frame(self)

    def to_dict(self) -> dict[str, object]:
        return {
            "frame_version": FRAME_VERSION,
            "question": self.question,
            "nodes": [node.to_dict() for node in self.nodes],
        }


def validate_frame(frame: Frame) -> None:
    """Refuse a frame the engine cannot render, before any judge is spawned."""
    if not isinstance(frame.question, str) or not frame.question.strip():
        raise FrameError("a match frame must carry a non-empty question")

    players = [node for node in _walk(frame.nodes) if isinstance(node, Players)]
    if len(players) != 1:
        raise FrameError(
            "a match frame must carry exactly one Players() placeholder "
            f"(found {len(players)}); the engine owns the roster and needs "
            "one place to put it"
        )

    _resolve_cites(frame.nodes, tables_of(frame))


def tables_of(frame: Frame) -> dict[str, Table]:
    """Every named lookup a cite may resolve against."""
    return {node.name: node for node in _walk(frame.nodes) if isinstance(node, Table)}


def validate_cards(frame: Frame, cards: SequenceABC[FrameNode]) -> None:
    """Check the player cards against the frame they will be composed into.

    A card is built by ``present_player`` and so is not inside the frame, but a
    cite in a card resolves against the frame's tables exactly like any other.
    Checking here is what keeps an unresolvable reference from costing a spawn.
    """
    tables = tables_of(frame)
    for card in cards:
        for node in _walk([card]):
            if isinstance(node, Players):
                raise FrameError(
                    "a player card may not contain Players(); the engine places "
                    "the candidates, and a card inside the roster is a loop"
                )
            if isinstance(node, Shuffle):
                raise FrameError(
                    "a player card may not declare a shuffle; presentation order "
                    "is already engine-owned and a second permutation would be "
                    "recorded nowhere"
                )
        _resolve_cites([card], tables)


def _resolve_cites(nodes: SequenceABC[FrameNode], tables: dict[str, Table]) -> None:
    for node in _walk(nodes):
        if not isinstance(node, Cite):
            continue
        table = tables.get(node.table)
        if table is None:
            known = ", ".join(sorted(tables)) or "none"
            raise FrameError(
                f"cite names table {node.table!r}, which this frame does not "
                f"define (defined: {known})"
            )
        if node.key not in table.keys():
            raise FrameError(
                f"cite names key {node.key!r}, which table {node.table!r} does "
                f"not define (defined: {', '.join(table.keys()) or 'none'})"
            )


# --------------------------------------------------------------------------
# Operations
# --------------------------------------------------------------------------


def plan_operations(frame: Frame, rng: random.Random) -> dict[str, list[int]]:
    """Draw the permutation for every declared shuffle, in traversal order.

    The permutations ride the verdict's bindings rather than the template. A
    template holding its run's permutation would be unique per match and dedup
    nothing, and the material inside a shuffled table is exactly the material a
    hundred other matches share.
    """
    plan: dict[str, list[int]] = {}
    for index, node in enumerate(_shuffle_sites(frame.nodes)):
        count = _child_count(node.node)
        order = list(range(count))
        rng.shuffle(order)
        plan[str(index)] = order
    return plan


def _shuffle_sites(nodes: SequenceABC[FrameNode]) -> list[Shuffle]:
    return [node for node in _walk(nodes) if isinstance(node, Shuffle)]


def _child_count(node: FrameNode) -> int:
    if isinstance(node, Table):
        return len(node.entries)
    if isinstance(node, Section):
        return len(node.body)
    return 0


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def render_frame(
    frame_data: Mapping[str, object],
    *,
    players_block: str,
    operations: Mapping[str, object] | None = None,
) -> str:
    """Render a frame's stored dictionary form back to the judge's text.

    Takes the dictionary rather than the dataclass because reassembly starts from
    what the depot holds, not from the definition that produced it — that is the
    whole reason a template exists.
    """
    version = frame_data.get("frame_version")
    if version != FRAME_VERSION:
        raise FrameError(
            f"unknown match frame version: {version!r} "
            f"(this engine renders version {FRAME_VERSION})"
        )
    state = _RenderState(
        operations=dict(operations or {}),
        players_block=players_block,
    )
    parts = [str(frame_data.get("question", "")).strip()]
    for node in _node_dicts(frame_data.get("nodes")):
        rendered = state.render(node)
        if rendered:
            parts.append(rendered)
    return "\n\n".join(part for part in parts if part)


def render_node(node: FrameNode) -> str:
    """Render one standalone node — a player card, not a whole frame.

    A card carries no ``Players`` and no ``Shuffle``, so it needs neither a
    candidates block nor an operation plan and renders from itself alone.
    """
    return _RenderState(operations={}, players_block="").render(_as_node(node).to_dict())


@dataclass
class _RenderState:
    """Carries the shuffle plan and consumes it in the same order it was drawn."""

    operations: dict[str, object]
    players_block: str
    shuffle_index: int = 0

    def render(self, node: Mapping[str, object]) -> str:
        kind = node.get("type")
        if kind == Text.TYPE:
            return str(node.get("body", "")).strip()
        if kind == Raw.TYPE:
            return str(node.get("body", ""))
        if kind == Cite.TYPE:
            return str(node.get("key", ""))
        if kind == Players.TYPE:
            return self.players_block
        if kind == Table.TYPE:
            return self._table(node)
        if kind == Sequence.TYPE:
            items = [self.render(item) for item in _node_dicts(node.get("items"))]
            return "\n".join(f"- {item}" for item in items if item)
        if kind == Section.TYPE:
            return self._section(node)
        if kind == Shuffle.TYPE:
            return self._shuffle(node)
        raise FrameError(f"unknown match frame node: {kind!r}")

    def _table(
        self, node: Mapping[str, object], order: list[int] | None = None
    ) -> str:
        entries = _entry_pairs(node.get("entries"))
        entries = _permuted(entries, order)
        lines = [str(node.get("name", "")).strip()]
        for key, value in entries:
            lines.append("")
            lines.append(_labeled(key, self.render(value)))
        return "\n".join(line for line in lines if line is not None).strip()

    def _section(
        self, node: Mapping[str, object], order: list[int] | None = None
    ) -> str:
        body = list(_node_dicts(node.get("body")))
        body = _permuted(body, order)
        parts = [str(node.get("label", "")).strip()]
        parts.extend(self.render(item) for item in body)
        return "\n\n".join(part for part in parts if part)

    def _shuffle(self, node: Mapping[str, object]) -> str:
        order = self.operations.get(str(self.shuffle_index))
        self.shuffle_index += 1
        inner = node.get("node")
        if not isinstance(inner, Mapping):
            raise FrameError("a shuffle node must wrap another node")
        permutation = None if order is None else [int(item) for item in order]
        if inner.get("type") == Table.TYPE:
            return self._table(inner, permutation)
        if inner.get("type") == Section.TYPE:
            return self._section(inner, permutation)
        raise FrameError(
            f"a shuffle node may only wrap a table or a section, "
            f"got {inner.get('type')!r}"
        )


def _labeled(key: str, value: str) -> str:
    """One table row. A multi-line value indents so the key stays readable."""
    lines = value.split("\n")
    head = f"{key}: {lines[0]}" if lines else f"{key}:"
    rest = [f"  {line}" if line else line for line in lines[1:]]
    return "\n".join([head, *rest])


def _permuted(items: list, order: list[int] | None) -> list:
    if order is None:
        return items
    if sorted(order) != list(range(len(items))):
        raise FrameError(
            f"a recorded shuffle must be a permutation of {len(items)} positions; "
            f"got {order!r}"
        )
    return [items[index] for index in order]


# --------------------------------------------------------------------------
# Addressing
# --------------------------------------------------------------------------


def canonical(data: Mapping[str, object]) -> bytes:
    """Serialize the one way, so equal material shares one address."""
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def address_of(data: Mapping[str, object]) -> str:
    return "sha256:" + hashlib.sha256(canonical(data)).hexdigest()


# --------------------------------------------------------------------------
# Internals
# --------------------------------------------------------------------------


def _as_node(value: object) -> FrameNode:
    """Accept a bare string as prose so ordinary material stays ordinary."""
    if isinstance(value, str):
        return Text(value)
    if isinstance(value, Node):
        return value  # type: ignore[return-value]
    raise FrameError(
        f"a match frame holds nodes or strings, got {type(value).__name__}; "
        "wrap unstructured material in Raw() so leaving the vocabulary is visible"
    )


def _normalized_entries(value: object) -> tuple[tuple[str, FrameNode], ...]:
    if isinstance(value, Mapping):
        pairs = list(value.items())
    elif isinstance(value, SequenceABC) and not isinstance(value, str):
        pairs = [tuple(item) for item in value]  # type: ignore[misc]
    else:
        raise FrameError(
            f"table entries must be a mapping or a sequence of pairs, "
            f"got {type(value).__name__}"
        )
    normalized: list[tuple[str, FrameNode]] = []
    seen: set[str] = set()
    for pair in pairs:
        if len(pair) != 2:
            raise FrameError(f"a table entry must be a (key, value) pair: {pair!r}")
        key, item = pair
        if not isinstance(key, str) or not key.strip():
            raise FrameError(f"a table key must be a non-empty string: {key!r}")
        if key in seen:
            raise FrameError(
                f"table key {key!r} appears twice; a cite could not resolve it"
            )
        seen.add(key)
        normalized.append((key, _as_node(item)))
    return tuple(normalized)


def _walk(nodes: SequenceABC[FrameNode]):
    """Depth-first over every node, parents before children.

    Shuffle sites are numbered by this order, so it is part of the recorded
    contract rather than an implementation detail.
    """
    for node in nodes:
        yield node
        if isinstance(node, Table):
            yield from _walk([item for _key, item in node.entries])
        elif isinstance(node, Sequence):
            yield from _walk(node.items)
        elif isinstance(node, Section):
            yield from _walk(node.body)
        elif isinstance(node, Shuffle):
            yield from _walk([node.node])


def _node_dicts(value: object) -> list[Mapping[str, object]]:
    if value is None:
        return []
    if not isinstance(value, SequenceABC) or isinstance(value, str):
        raise FrameError(f"expected a list of nodes, got {type(value).__name__}")
    for item in value:
        if not isinstance(item, Mapping):
            raise FrameError(f"expected a node object, got {type(item).__name__}")
    return list(value)  # type: ignore[arg-type]


def _entry_pairs(value: object) -> list[tuple[str, Mapping[str, object]]]:
    if value is None:
        return []
    if not isinstance(value, SequenceABC) or isinstance(value, str):
        raise FrameError(f"expected table entries, got {type(value).__name__}")
    pairs: list[tuple[str, Mapping[str, object]]] = []
    for item in value:
        if not isinstance(item, SequenceABC) or len(item) != 2:
            raise FrameError(f"expected a (key, node) entry, got {item!r}")
        key, node = item
        if not isinstance(node, Mapping):
            raise FrameError(f"expected a node object for key {key!r}")
        pairs.append((str(key), node))
    return pairs
