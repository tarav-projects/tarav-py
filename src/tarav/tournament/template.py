# $kw: ^tournament-template --from Match.Template --from Match.Verbatim --from Match.Component.Registry --note [DF] a Match.Template is the complete parameterized description of one Match.Verbatim, structured so a renderer can rebuild that verbatim without the code that first produced it --supp ^c20260809-19u ^<anchor-on-landing>
"""The parameterized description of one match prompt, and its renderer.

A ``Match.Verbatim`` is derived, never stored. What is stored is a
``Match.Template``: a small JSON object naming its parts by content address, plus
the per-run values those parts need bound into them. Rendering is pure data work
here, so a verdict written by one engine version rebuilds under another.

Two template versions render here, and version 1 is not debt to retire: every
verdict recorded before frames existed names one, and a prompt that cannot be
rebuilt is a `verbatim_hash` that cannot be checked.

Version 1 — the fixed frame a definition got before it could compose one. Three
component kinds, all addressed the same way:

- ``Match.Brief`` — the definition's question and optional criteria, one component
  because they change together and only when the definition does.
- ``Player.Presentation`` — one per player, exactly what ``present_player`` returned.
  Identical presentations collapse to one address, which is where dedup pays.
- ``Match.Footnote.Template`` — the engine's trailing frame with its holes still
  open: the ranking instruction and the two submit commands.

Version 2 — the definition composed a ``Match.Frame``, so the brief is replaced
by that whole frame as a *single* component. One component and not one per node
because the frame is identical across every match of a run; the per-match
variation is the presentations, and that is already where dedup pays. The frame
carries a ``Players()`` placeholder, so it renders *around* the candidates rather
than before them, and any permutation it declared rides ``template_bindings``
under ``frame_operations`` — a template restating its own run's shuffle would be
unique per match and dedup nothing.

Position labels are generated here from arity. They are engine frame, but they
interleave the presentations rather than trailing them, so they belong to neither
the brief nor the footnote and are not a component.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

from tarav.tournament.components import ComponentRegistry
from tarav.tournament.contract import position_labels
from tarav.tournament.frame import Frame, render_frame
from tarav.tournament.frame import canonical as frame_canonical
from tarav.tournament.model import TournamentError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from tarav.tournament.model import Verdict
    from tarav.tournament.store import TournamentStore

TEMPLATE_VERSION = 2
LEGACY_TEMPLATE_VERSION = 1

KIND_BRIEF = "brief"
KIND_FRAME = "frame"
KIND_CANDIDATES = "candidates"
KIND_FOOTNOTE = "footnote"

ORIGIN_DEFINITION = "definition"
ORIGIN_ENGINE = "engine"




FOOTNOTE_TEMPLATE = (
    "Rank all {arity} candidates from best to worst, every label exactly "
    "once — no ties.\n"
    "\n"
    "Submit your answer by running this command. It validates your ranking "
    "and tells you what to fix if it is wrong:\n"
    "\n"
    "    tarav tournament submit{depot} --ticket {ticket_id} "
    "--ranking {ranking}\n"
    "\n"
    "Replace the ranking with your own order, best first. If the comparison "
    "cannot honestly be made, submit instead:\n"
    "\n"
    "    tarav tournament submit{depot} --ticket {ticket_id} "
    '--no-contest --refusal-reason "why"\n'
    "\n"
    "Nothing you print is read; only the submitted command counts."
)


RANKING_TEMPLATE = (
    "Rank all {arity} candidates from best to worst, every label exactly "
    "once — no ties."
)


class TemplateMissingError(TournamentError):
    """The verdict predates templates and carries no address to rebuild from."""


def build_template(
    *,
    question: str,
    criteria: str | None,
    presented_presentations: tuple[str, ...],
    ticket_id: str | None = None,
    depot_root: Path | str | None = None,
    frame: Frame | None = None,
    frame_operations: dict[str, object] | None = None,
) -> tuple[dict[str, object], dict[str, bytes], dict[str, object]]:
    """Describe one match prompt as data.

    Returns the template, the components it names keyed by address, and the
    bindings the renderer needs. The bindings stay out of the template: a template
    that restated its run's ticket would be unique per run and dedup nothing, and
    the values are already recorded beside it.

    Without a ``frame`` this emits a version 1 template — the fixed brief,
    candidates, and footnote a definition got before frames existed. With one it
    emits version 2, where the definition's whole composed frame is a single
    component. One component and not one per node because the frame is identical
    across every match of a run: the per-match variation is the presentations,
    and that is already where dedup pays.
    """
    components: dict[str, bytes] = {}

    presentation_addresses = tuple(
        _put(components, presentation) for presentation in presented_presentations
    )
    footnote = FOOTNOTE_TEMPLATE if ticket_id is not None else RANKING_TEMPLATE
    footnote_address = _put(components, footnote)

    candidates_section = {
        "kind": KIND_CANDIDATES,
        "origin": ORIGIN_ENGINE,
        "presentations": list(presentation_addresses),
    }
    footnote_section = {
        "kind": KIND_FOOTNOTE,
        "origin": ORIGIN_ENGINE,
        "component": footnote_address,
    }

    if frame is None:
        head: dict[str, object] = {
            "kind": KIND_BRIEF,
            "origin": ORIGIN_DEFINITION,
            "component": _put(components, _brief_text(question, criteria)),
        }
        version = LEGACY_TEMPLATE_VERSION
    else:
        head = {
            "kind": KIND_FRAME,
            "origin": ORIGIN_DEFINITION,
            "component": _put_bytes(components, frame_canonical(frame.to_dict())),
        }
        version = TEMPLATE_VERSION

    template: dict[str, object] = {
        "template_version": version,
        "sections": [head, candidates_section, footnote_section],
    }
    bindings: dict[str, object] = {
        "ticket_id": ticket_id,
        "depot_root": None if depot_root is None else str(depot_root),
    }
    if frame is not None:
        bindings["frame_operations"] = dict(frame_operations or {})
    return template, components, bindings


def render_template(
    template: dict[str, object],
    components: dict[str, bytes],
    bindings: dict[str, object],
) -> str:
    """Rebuild the exact text a judge was handed.

    Both template versions render here. Version 1 is not legacy debt to retire —
    every verdict recorded before frames existed names one, and a verdict whose
    prompt cannot be rebuilt is a verdict whose hash cannot be checked.
    """
    version = template.get("template_version")
    if version == LEGACY_TEMPLATE_VERSION:
        return _render_v1(template, components, bindings)
    if version == TEMPLATE_VERSION:
        return _render_v2(template, components, bindings)
    raise TournamentError(
        f"unknown match template version: {version!r} "
        f"(this engine renders versions {LEGACY_TEMPLATE_VERSION} "
        f"and {TEMPLATE_VERSION})"
    )


def _render_v1(
    template: dict[str, object],
    components: dict[str, bytes],
    bindings: dict[str, object],
) -> str:
    parts: list[str] = []
    for section in _sections(template):
        kind = section.get("kind")
        if kind == KIND_BRIEF:
            brief = _text(components, section["component"])
            parts.extend(part for part in brief.split("\n\n") if part)
        elif kind == KIND_CANDIDATES:
            parts.append(_candidates_block(section, components))
        elif kind == KIND_FOOTNOTE:
            parts.append(_footnote_part(section, template, components, bindings))
        else:
            raise TournamentError(f"unknown match template section: {kind!r}")
    return "\n\n".join(parts)


def _render_v2(
    template: dict[str, object],
    components: dict[str, bytes],
    bindings: dict[str, object],
) -> str:
    """The frame decides where the candidates land, so it renders around them."""
    sections = {str(section.get("kind")): section for section in _sections(template)}
    for kind in (KIND_FRAME, KIND_CANDIDATES, KIND_FOOTNOTE):
        if kind not in sections:
            raise TournamentError(f"a version 2 match template needs a {kind!r} section")

    candidates = _candidates_block(sections[KIND_CANDIDATES], components)
    frame_data = json.loads(
        _text(components, sections[KIND_FRAME]["component"])
    )
    body = render_frame(
        frame_data,
        players_block=candidates,
        operations=bindings.get("frame_operations") or {},
    )
    footnote = _footnote_part(
        sections[KIND_FOOTNOTE], template, components, bindings
    )
    return "\n\n".join([body, footnote])


def _candidates_block(
    section: dict[str, object], components: dict[str, bytes]
) -> str:
    addresses = tuple(section.get("presentations") or ())
    labels = position_labels(len(addresses))
    return "\n\n".join(
        f"{label}:\n{_text(components, address)}"
        for label, address in zip(labels, addresses)
    )


def _footnote_part(
    section: dict[str, object],
    template: dict[str, object],
    components: dict[str, bytes],
    bindings: dict[str, object],
) -> str:
    return _rendered_footnote(
        _text(components, section["component"]),
        arity=_arity(template),
        bindings=bindings,
    )


def register_template(
    registry: ComponentRegistry,
    template: dict[str, object],
    components: dict[str, bytes],
) -> str:
    """Write a template and every part it names, returning the template address.

    Each write is a no-op when the content is already present, so repeated matches
    over one player cost nothing after the first.
    """
    for data in components.values():
        registry.put(data)
    return registry.put(_canonical(template))


def reassemble(store: TournamentStore, verdict: Verdict) -> str:
    """Rebuild one verdict's prompt from the depot.

    It renders and returns; it does not verify. Comparing the result's hash to the
    recorded ``verbatim_hash`` is the caller's call, because a rebuild that
    silently repaired a mismatch would destroy the only evidence of one.
    """
    address = verdict.envelope.get("template")
    if not address:
        raise TemplateMissingError(
            f"verdict {verdict.record_id} carries no match template; it was "
            "recorded before templates existed and cannot be reassembled"
        )
    registry = ComponentRegistry(store.root)
    template = json.loads(registry.get(str(address)).decode("utf-8"))
    components = {
        address: registry.get(address) for address in _addresses(template)
    }
    bindings = verdict.envelope.get("template_bindings") or {}
    return render_template(template, components, dict(bindings))


def _sections(template: dict[str, object]) -> tuple[dict[str, object], ...]:
    sections = template.get("sections")
    if not isinstance(sections, list):
        raise TournamentError("a match template must carry a list of sections")
    return tuple(sections)


def _addresses(template: dict[str, object]) -> tuple[str, ...]:
    found: list[str] = []
    for section in _sections(template):
        component = section.get("component")
        if component:
            found.append(str(component))
        found.extend(str(item) for item in section.get("presentations") or ())
    return tuple(found)


def _arity(template: dict[str, object]) -> int:
    for section in _sections(template):
        if section.get("kind") == KIND_CANDIDATES:
            return len(section.get("presentations") or ())
    return 0


def _rendered_footnote(
    footnote: str, *, arity: int, bindings: dict[str, object]
) -> str:
    labels = position_labels(arity)
    ticket_id = bindings.get("ticket_id")
    depot_root = bindings.get("depot_root")
    return footnote.format(
        arity=arity,
        ticket_id=ticket_id,
        depot="" if depot_root is None else f" --depot {depot_root}",



        ranking=",".join(labels[1:] + labels[:1]),
    )


def _brief_text(question: str, criteria: str | None) -> str:
    parts = [question.strip()]
    if criteria and criteria.strip():
        parts.append(criteria.strip())
    return "\n\n".join(parts)


def _put(components: dict[str, bytes], text: str) -> str:
    return _put_bytes(components, text.encode("utf-8"))


def _put_bytes(components: dict[str, bytes], data: bytes) -> str:
    address = "sha256:" + hashlib.sha256(data).hexdigest()
    components[address] = data
    return address


def _text(components: dict[str, bytes], address: object) -> str:
    data = components.get(str(address))
    if data is None:
        raise TournamentError(f"match template names a missing component: {address}")
    return data.decode("utf-8")


def _canonical(template: dict[str, object]) -> bytes:
    """Serialize a template the one way, so equal templates share one address."""
    return json.dumps(
        template, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
