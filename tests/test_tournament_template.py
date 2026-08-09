# $kw: ^test-tournament-template --from Match.Template --from Match.Verbatim --note [CT] the rendered bytes are the invariant: a template that does not reproduce the current frame exactly cannot be checked against verbatim_hash ^<anchor-on-landing>
from __future__ import annotations

import pytest

from agentos.tournament.runner import compose_verbatim
from agentos.tournament.template import build_template, render_template

CRITERIA = "Prefer the one that survives a hostile reading."


def _frame(
    *,
    arity: int,
    criteria: str | None,
    ticket_id: str | None,
) -> tuple[str, str | None, tuple[str, ...], str | None, str | None]:
    presentations = tuple(f"candidate number {index}" for index in range(arity))
    depot = "/tmp/depot" if ticket_id else None
    return ("Which is better?", criteria, presentations, ticket_id, depot)


MATRIX = [
    (arity, criteria, ticket)
    for arity in (2, 4, 26)
    for criteria in (None, CRITERIA)
    for ticket in (None, "tk-0001")
]


@pytest.mark.parametrize("arity,criteria,ticket_id", MATRIX)
def test_the_template_renders_the_frame_byte_for_byte(
    arity: int, criteria: str | None, ticket_id: str | None
) -> None:
    """The whole change is a refactor with a hash for its witness."""
    question, criteria, presentations, ticket_id, depot = _frame(
        arity=arity, criteria=criteria, ticket_id=ticket_id
    )
    expected = _legacy_verbatim(
        question=question,
        criteria=criteria,
        presented_presentations=presentations,
        ticket_id=ticket_id,
        depot_root=depot,
    )

    template, components, bindings = build_template(
        question=question,
        criteria=criteria,
        presented_presentations=presentations,
        ticket_id=ticket_id,
        depot_root=depot,
    )

    assert render_template(template, components, bindings) == expected


def test_the_live_composer_and_the_template_agree() -> None:
    """compose_verbatim is the production path; it must not drift from the renderer."""
    question, criteria, presentations, ticket_id, depot = _frame(
        arity=3, criteria=CRITERIA, ticket_id="tk-9"
    )
    template, components, bindings = build_template(
        question=question,
        criteria=criteria,
        presented_presentations=presentations,
        ticket_id=ticket_id,
        depot_root=depot,
    )
    assert render_template(template, components, bindings) == compose_verbatim(
        question=question,
        criteria=criteria,
        presented_presentations=presentations,
        ticket_id=ticket_id,
        depot_root=depot,
    )


def test_a_template_names_its_parts_by_content_address() -> None:
    template, components, _bindings = build_template(
        question="q",
        criteria=None,
        presented_presentations=("a", "b"),
        ticket_id=None,
        depot_root=None,
    )
    addresses = {
        section.get("component")
        for section in template["sections"]
        if "component" in section
    }
    for section in template["sections"]:
        addresses.update(section.get("presentations", ()))

    assert addresses <= set(components)
    assert all(address.startswith("sha256:") for address in addresses)


def test_identical_presentations_share_one_address() -> None:
    """Dedup is the point: one player's presentation is written once."""
    _template, components, _bindings = build_template(
        question="q",
        criteria=None,
        presented_presentations=("same", "same", "other"),
        ticket_id=None,
        depot_root=None,
    )
    presentation_bodies = [value for value in components.values()]
    assert presentation_bodies.count(b"same") == 1


def test_sections_declare_which_side_supplied_them() -> None:
    template, _components, _bindings = build_template(
        question="q",
        criteria=None,
        presented_presentations=("a", "b"),
        ticket_id="tk-1",
        depot_root="/d",
    )
    origins = {section["kind"]: section["origin"] for section in template["sections"]}
    assert origins == {
        "brief": "definition",
        "candidates": "engine",
        "footnote": "engine",
    }


def test_the_template_declares_its_shape_version() -> None:
    template, _components, _bindings = build_template(
        question="q",
        criteria=None,
        presented_presentations=("a", "b"),
        ticket_id=None,
        depot_root=None,
    )
    assert isinstance(template["template_version"], int)


def test_per_run_values_stay_out_of_the_template() -> None:
    """The ticket and depot are bindings; the template must not restate them."""
    import json

    template, _components, bindings = build_template(
        question="q",
        criteria=None,
        presented_presentations=("a", "b"),
        ticket_id="tk-secret",
        depot_root="/depot/here",
    )
    serialized = json.dumps(template)
    assert "tk-secret" not in serialized
    assert "/depot/here" not in serialized
    assert bindings["ticket_id"] == "tk-secret"
    assert bindings["depot_root"] == "/depot/here"


def _legacy_verbatim(
    *,
    question: str,
    criteria: str | None,
    presented_presentations: tuple[str, ...],
    ticket_id: str | None,
    depot_root: str | None,
) -> str:
    """The frame exactly as it stood before templates, pinned here as the oracle."""
    from agentos.tournament.contract import position_labels

    labels = position_labels(len(presented_presentations))
    parts = [question.strip()]
    if criteria and criteria.strip():
        parts.append(criteria.strip())
    for label, presentation in zip(labels, presented_presentations):
        parts.append(f"{label}:\n{presentation}")
    parts.append(
        f"Rank all {len(labels)} candidates from best to worst, every label exactly "
        "once — no ties."
    )
    if ticket_id is not None:
        ranked = ",".join(labels[1:] + labels[:1])
        depot = f" --depot {depot_root}" if depot_root is not None else ""
        parts.append(
            "Submit your answer by running this command. It validates your ranking "
            "and tells you what to fix if it is wrong:\n\n"
            f"    agentos tournament submit{depot} --ticket {ticket_id} "
            f"--ranking {ranked}\n\n"
            "Replace the ranking with your own order, best first. If the comparison "
            "cannot honestly be made, submit instead:\n\n"
            f"    agentos tournament submit{depot} --ticket {ticket_id} "
            '--no-contest --refusal-reason "why"\n\n'
            "Nothing you print is read; only the submitted command counts."
        )
    return "\n\n".join(parts)
