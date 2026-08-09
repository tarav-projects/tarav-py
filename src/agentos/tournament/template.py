# $kw: ^tournament-template --from Match.Template --from Match.Verbatim --from Match.Component.Registry --note [DF] a Match.Template is the complete parameterized description of one Match.Verbatim, structured so a renderer can rebuild that verbatim without the code that first produced it --supp ^c20260809-19u ^<anchor-on-landing>
"""The parameterized description of one match prompt, and its renderer.

A ``Match.Verbatim`` is derived, never stored. What is stored is a
``Match.Template``: a small JSON object naming its parts by content address, plus
the per-run values those parts need bound into them. Rendering is pure data work
here, so a verdict written by one engine version rebuilds under another.

Three component kinds, all addressed the same way:

- ``Match.Brief`` — the definition's question and optional criteria, one component
  because they change together and only when the definition does.
- ``Player.Presentation`` — one per player, exactly what ``present_player`` returned.
  Identical presentations collapse to one address, which is where dedup pays.
- ``Match.Footnote.Template`` — the engine's trailing frame with its holes still
  open: the ranking instruction and the two submit commands.

Position labels are generated here from arity. They are engine frame, but they
interleave the presentations rather than trailing them, so they belong to neither
the brief nor the footnote and are not a component.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

from agentos.tournament.components import ComponentRegistry
from agentos.tournament.contract import position_labels
from agentos.tournament.model import TournamentError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from agentos.tournament.model import Verdict
    from agentos.tournament.store import TournamentStore

TEMPLATE_VERSION = 1

KIND_BRIEF = "brief"
KIND_CANDIDATES = "candidates"
KIND_FOOTNOTE = "footnote"

ORIGIN_DEFINITION = "definition"
ORIGIN_ENGINE = "engine"

# The footnote before its per-run values are bound. Kept as one literal rather
# than assembled from pieces: it is registered by content, so the text itself is
# the version.
FOOTNOTE_TEMPLATE = (
    "Rank all {arity} candidates from best to worst, every label exactly "
    "once — no ties.\n"
    "\n"
    "Submit your answer by running this command. It validates your ranking "
    "and tells you what to fix if it is wrong:\n"
    "\n"
    "    agentos tournament submit{depot} --ticket {ticket_id} "
    "--ranking {ranking}\n"
    "\n"
    "Replace the ranking with your own order, best first. If the comparison "
    "cannot honestly be made, submit instead:\n"
    "\n"
    "    agentos tournament submit{depot} --ticket {ticket_id} "
    '--no-contest --refusal-reason "why"\n'
    "\n"
    "Nothing you print is read; only the submitted command counts."
)

# The ranking instruction alone, for a frame that has no ticket to submit against.
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
) -> tuple[dict[str, object], dict[str, bytes], dict[str, object]]:
    """Describe one match prompt as data.

    Returns the template, the components it names keyed by address, and the
    bindings the renderer needs. The bindings stay out of the template: a template
    that restated its run's ticket would be unique per run and dedup nothing, and
    the values are already recorded beside it.
    """
    components: dict[str, bytes] = {}

    brief = _brief_text(question, criteria)
    brief_address = _put(components, brief)

    presentation_addresses = tuple(
        _put(components, presentation) for presentation in presented_presentations
    )

    footnote = FOOTNOTE_TEMPLATE if ticket_id is not None else RANKING_TEMPLATE
    footnote_address = _put(components, footnote)

    template: dict[str, object] = {
        "template_version": TEMPLATE_VERSION,
        "sections": [
            {
                "kind": KIND_BRIEF,
                "origin": ORIGIN_DEFINITION,
                "component": brief_address,
            },
            {
                "kind": KIND_CANDIDATES,
                "origin": ORIGIN_ENGINE,
                "presentations": list(presentation_addresses),
            },
            {
                "kind": KIND_FOOTNOTE,
                "origin": ORIGIN_ENGINE,
                "component": footnote_address,
            },
        ],
    }
    bindings: dict[str, object] = {
        "ticket_id": ticket_id,
        # Recorded because it is rendered into the judge's prompt and lives
        # nowhere else: a depot that moved would otherwise fail every reassembly
        # for a reason no record explains.
        "depot_root": None if depot_root is None else str(depot_root),
    }
    return template, components, bindings


def render_template(
    template: dict[str, object],
    components: dict[str, bytes],
    bindings: dict[str, object],
) -> str:
    """Rebuild the exact text a judge was handed."""
    version = template.get("template_version")
    if version != TEMPLATE_VERSION:
        raise TournamentError(
            f"unknown match template version: {version!r} "
            f"(this engine renders version {TEMPLATE_VERSION})"
        )

    parts: list[str] = []
    for section in _sections(template):
        kind = section.get("kind")
        if kind == KIND_BRIEF:
            brief = _text(components, section["component"])
            parts.extend(part for part in brief.split("\n\n") if part)
        elif kind == KIND_CANDIDATES:
            addresses = tuple(section.get("presentations") or ())
            labels = position_labels(len(addresses))
            for label, address in zip(labels, addresses):
                parts.append(f"{label}:\n{_text(components, address)}")
        elif kind == KIND_FOOTNOTE:
            parts.append(
                _rendered_footnote(
                    _text(components, section["component"]),
                    arity=_arity(template),
                    bindings=bindings,
                )
            )
        else:
            raise TournamentError(f"unknown match template section: {kind!r}")
    return "\n\n".join(parts)


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
        # Rotated, never the identity order: a judge copying the example and a
        # judge genuinely finding the candidates already ranked would otherwise be
        # indistinguishable in the records.
        ranking=",".join(labels[1:] + labels[:1]),
    )


def _brief_text(question: str, criteria: str | None) -> str:
    parts = [question.strip()]
    if criteria and criteria.strip():
        parts.append(criteria.strip())
    return "\n\n".join(parts)


def _put(components: dict[str, bytes], text: str) -> str:
    data = text.encode("utf-8")
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
