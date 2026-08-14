# $kw: ^test-tournament-template --from Match.Template --from Match.Verbatim --note [CT] the rendered bytes are the invariant: a template that does not reproduce the current frame exactly cannot be checked against verbatim_hash ^<anchor-on-landing>
from __future__ import annotations

import pytest

from tarav.tournament.frame import Frame, Players, Shuffle, Table, Text
from tarav.tournament.model import TournamentError
from tarav.tournament.runner import compose_verbatim
from tarav.tournament.template import build_template, render_template

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
    from tarav.tournament.contract import position_labels

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
            f"    tarav tournament submit{depot} --ticket {ticket_id} "
            f"--ranking {ranked}\n\n"
            "Replace the ranking with your own order, best first. If the comparison "
            "cannot honestly be made, submit instead:\n\n"
            f"    tarav tournament submit{depot} --ticket {ticket_id} "
            '--no-contest --refusal-reason "why"\n\n'
            "Nothing you print is read; only the submitted command counts."
        )
    return "\n\n".join(parts)


# --------------------------------------------------------------------------
# Version 2: a definition-composed Match.Frame
# --------------------------------------------------------------------------


def _typed_frame() -> Frame:
    """The shape the index Line.Type tournament needs: shared material, cited."""
    return Frame(
        question="Which line is most accurately typed?",
        nodes=(
            Text("Rank by fit between the line and its own type."),
            Shuffle(Table("Line types", {"DC": "pins a choice", "CT": "bounds one"})),
            Players(),
        ),
    )


def _v2(frame: Frame, *, operations=None, ticket_id=None, depot=None):
    template, components, bindings = build_template(
        question="ignored when a frame is supplied",
        criteria=None,
        presented_presentations=("first card", "second card"),
        ticket_id=ticket_id,
        depot_root=depot,
        frame=frame,
        frame_operations=operations,
    )
    return template, components, bindings


def test_a_frame_selects_the_version_2_template() -> None:
    template, _components, _bindings = _v2(_typed_frame())
    assert template["template_version"] == 2
    assert [section["kind"] for section in template["sections"]] == [
        "frame",
        "candidates",
        "footnote",
    ]


def test_no_frame_still_selects_version_1() -> None:
    """Every definition written before frames must render the bytes it always did."""
    template, _components, _bindings = build_template(
        question="q", criteria=None, presented_presentations=("a", "b")
    )
    assert template["template_version"] == 1


def test_the_frame_decides_where_the_candidates_land() -> None:
    template, components, bindings = _v2(_typed_frame(), operations={"0": [0, 1]})
    rendered = render_template(template, components, bindings)
    assert rendered.index("Line types") < rendered.index("A:\nfirst card")
    assert rendered.startswith("Which line is most accurately typed?")


def test_the_frame_question_wins_over_the_module_attribute() -> None:
    template, components, bindings = _v2(_typed_frame(), operations={"0": [0, 1]})
    rendered = render_template(template, components, bindings)
    assert "ignored when a frame is supplied" not in rendered


def test_shared_material_is_rendered_once() -> None:
    """The point of a frame: five cards, one copy of what they all cite."""
    template, components, bindings = _v2(_typed_frame(), operations={"0": [0, 1]})
    rendered = render_template(template, components, bindings)
    assert rendered.count("pins a choice") == 1


def test_the_permutation_is_a_binding_not_template_content() -> None:
    """A template restating its run's shuffle would be unique per match."""
    import json

    forward, _components, forward_bindings = _v2(_typed_frame(), operations={"0": [0, 1]})
    reverse, _components2, reverse_bindings = _v2(_typed_frame(), operations={"0": [1, 0]})
    assert json.dumps(forward) == json.dumps(reverse)
    assert forward_bindings["frame_operations"] == {"0": [0, 1]}
    assert reverse_bindings["frame_operations"] == {"0": [1, 0]}


def test_the_recorded_permutation_alone_rebuilds_the_order() -> None:
    template, components, _bindings = _v2(_typed_frame())
    forward = render_template(
        template, components, {"ticket_id": None, "frame_operations": {"0": [0, 1]}}
    )
    reverse = render_template(
        template, components, {"ticket_id": None, "frame_operations": {"0": [1, 0]}}
    )
    assert forward.index("DC:") < forward.index("CT:")
    assert reverse.index("CT:") < reverse.index("DC:")


def test_a_version_2_template_still_carries_the_submit_instruction() -> None:
    template, components, bindings = _v2(
        _typed_frame(), operations={"0": [0, 1]}, ticket_id="tk-9", depot="/d"
    )
    rendered = render_template(template, components, bindings)
    assert "tarav tournament submit --depot /d --ticket tk-9" in rendered


def test_an_unknown_template_version_names_both_renderable_ones() -> None:
    template, components, bindings = _v2(_typed_frame(), operations={"0": [0, 1]})
    template["template_version"] = 99
    with pytest.raises(TournamentError, match="renders versions 1 and 2"):
        render_template(template, components, bindings)
