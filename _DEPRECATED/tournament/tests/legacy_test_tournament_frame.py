"""The typed node vocabulary a definition composes a match prompt from."""

from __future__ import annotations

import random

import pytest

from tarav.tournament.frame import (
    Cite,
    Frame,
    FrameError,
    Players,
    Raw,
    Section,
    Sequence,
    Shuffle,
    Table,
    Text,
    address_of,
    plan_operations,
    render_frame,
)

PLAYERS_BLOCK = "A:\nfirst\n\nB:\nsecond"


def _frame(*nodes, question: str = "Which is better?") -> Frame:
    return Frame(question=question, nodes=nodes)


def _render(frame: Frame, operations=None) -> str:
    return render_frame(
        frame.to_dict(), players_block=PLAYERS_BLOCK, operations=operations
    )


class TestAddressing:
    def test_equal_nodes_share_one_address(self):
        assert address_of(Text("hello").to_dict()) == address_of(Text("hello").to_dict())

    def test_different_content_addresses_differently(self):
        assert address_of(Text("a").to_dict()) != address_of(Text("b").to_dict())

    def test_the_version_is_inside_the_address(self):
        """A rendering change must not rebuild an old verdict into new text."""
        node = Text("hello").to_dict()
        bumped = {**node, "version": node["version"] + 1}
        assert address_of(node) != address_of(bumped)

    def test_table_entry_order_is_content(self):
        forward = Table("t", {"a": "1", "b": "2"}).to_dict()
        reverse = Table("t", {"b": "2", "a": "1"}).to_dict()
        assert address_of(forward) != address_of(reverse)

    def test_a_table_built_two_ways_shares_one_address(self):
        from_mapping = Table("t", {"a": "1", "b": "2"})
        from_pairs = Table("t", [("a", Text("1")), ("b", Text("2"))])
        assert address_of(from_mapping.to_dict()) == address_of(from_pairs.to_dict())


class TestValidation:
    def test_a_frame_needs_exactly_one_players_placeholder(self):
        with pytest.raises(FrameError, match="exactly one Players"):
            _frame(Text("no candidates here"))
        with pytest.raises(FrameError, match="exactly one Players"):
            _frame(Players(), Players())

    def test_a_frame_needs_a_question(self):
        with pytest.raises(FrameError, match="non-empty question"):
            _frame(Players(), question="   ")

    def test_an_unresolvable_cite_is_refused_at_build(self):
        with pytest.raises(FrameError, match="which this frame does not define"):
            _frame(Table("types", {"DC": "a decision"}), Cite("codes", "DC"), Players())

    def test_a_cite_to_an_undefined_key_is_refused_at_build(self):
        with pytest.raises(FrameError, match="does not define"):
            _frame(Table("types", {"DC": "a decision"}), Cite("types", "ZZ"), Players())

    def test_a_resolvable_cite_passes(self):
        frame = _frame(Table("types", {"DC": "a decision"}), Cite("types", "DC"), Players())
        assert "DC" in _render(frame)

    def test_a_duplicate_table_key_is_refused(self):
        with pytest.raises(FrameError, match="appears twice"):
            Table("types", [("DC", "one"), ("DC", "two")])

    def test_unstructured_material_must_be_wrapped(self):
        with pytest.raises(FrameError, match="wrap unstructured material in Raw"):
            _frame(Players(), 42)


class TestShuffleRefusals:
    def test_shuffle_refuses_a_sequence(self):
        with pytest.raises(FrameError, match="ordered by construction"):
            Shuffle(Sequence(["one", "two"]))

    def test_shuffle_refuses_an_ordered_table(self):
        with pytest.raises(FrameError, match="ordered=True"):
            Shuffle(Table("steps", {"1": "first"}, ordered=True))

    def test_shuffle_refuses_a_leaf(self):
        with pytest.raises(FrameError, match="nothing to permute"):
            Shuffle(Text("prose"))


class TestRendering:
    def test_the_question_leads(self):
        assert _render(_frame(Players())).startswith("Which is better?")

    def test_the_players_placeholder_becomes_the_candidates(self):
        assert PLAYERS_BLOCK in _render(_frame(Players()))

    def test_a_table_renders_its_name_then_its_rows(self):
        frame = _frame(Table("Line types", {"DC": "pins a choice"}), Players())
        assert "Line types\n\nDC: pins a choice" in _render(frame)

    def test_a_multiline_table_value_indents_its_continuation(self):
        frame = _frame(Table("t", {"k": "first\nsecond"}), Players())
        assert "k: first\n  second" in _render(frame)

    def test_a_sequence_renders_as_a_list(self):
        frame = _frame(Sequence(["one", "two"]), Players())
        assert "- one\n- two" in _render(frame)

    def test_a_section_renders_its_label_then_its_body(self):
        frame = _frame(Section("Notes", ["first", "second"]), Players())
        assert "Notes\n\nfirst\n\nsecond" in _render(frame)

    def test_raw_is_not_stripped(self):
        frame = _frame(Raw("  spaced  "), Players())
        assert "  spaced  " in _render(frame)

    def test_an_unknown_node_kind_is_refused(self):
        data = _frame(Players()).to_dict()
        data["nodes"] = [{"type": "invented", "version": 1}]
        with pytest.raises(FrameError, match="unknown match frame node"):
            render_frame(data, players_block=PLAYERS_BLOCK)

    def test_an_unknown_frame_version_is_refused(self):
        data = _frame(Players()).to_dict()
        data["frame_version"] = 99
        with pytest.raises(FrameError, match="unknown match frame version"):
            render_frame(data, players_block=PLAYERS_BLOCK)


class TestShuffleOperations:
    def _shuffled(self):
        return _frame(
            Shuffle(Table("types", {"A": "one", "B": "two", "C": "three"})),
            Players(),
        )

    def test_a_plan_is_drawn_for_each_shuffle_site(self):
        plan = plan_operations(self._shuffled(), random.Random(7))
        assert sorted(plan) == ["0"]
        assert sorted(plan["0"]) == [0, 1, 2]

    def test_the_plan_alone_reproduces_the_rendered_order(self):
        """Reassembly rebuilds from the bindings, not from the engine that ran."""
        frame = self._shuffled()
        plan = {"0": [2, 0, 1]}
        rendered = _render(frame, plan)
        assert rendered.index("C: three") < rendered.index("A: one")
        assert rendered.index("A: one") < rendered.index("B: two")
        assert _render(frame, plan) == rendered

    def test_the_same_seed_draws_the_same_plan(self):
        frame = self._shuffled()
        assert plan_operations(frame, random.Random(3)) == plan_operations(
            frame, random.Random(3)
        )

    def test_a_malformed_recorded_permutation_is_refused(self):
        with pytest.raises(FrameError, match="must be a permutation"):
            _render(self._shuffled(), {"0": [0, 0, 0]})

    def test_shuffle_sites_are_numbered_depth_first(self):
        frame = _frame(
            Shuffle(Section("outer", [Shuffle(Table("inner", {"a": "1", "b": "2"}))])),
            Players(),
        )
        plan = plan_operations(frame, random.Random(1))
        assert sorted(plan) == ["0", "1"]
        assert len(plan["0"]) == 1
        assert len(plan["1"]) == 2

    def test_an_unshuffled_frame_plans_nothing(self):
        assert plan_operations(_frame(Players()), random.Random(1)) == {}
