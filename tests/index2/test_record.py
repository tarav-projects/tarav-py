from __future__ import annotations

import json

import pytest

from tarav.index2.gates import GateRef
from tarav.index2.record import (
    IndexStore,
    LineRecord,
    RecordStoreError,
    SupportRef,
    Tier,
    split_statement,
)
from tarav.index2.standing import ReviewSide, standings

BLOCK = "tarav-pkg/design#Index.Line.Record"
ANNOTATION = "@src/tarav/index2/linter.py/Finding"


def _support(message_id="addr-1", session="s1"):
    return SupportRef(archive="chat", session_id=session, message_id=message_id)


def _entry(body="the record is complete", scope=BLOCK, support=None, **kw):
    return LineRecord.create(
        scope, "CT", body, support=support if support is not None else (_support(),), **kw
    )


class TestCompleteRecord:
    def test_the_entry_carries_its_own_assertion(self):
        record = _entry()
        assert record.line.type == "CT"
        assert record.line.body == "the record is complete"
        assert record.scope.address == BLOCK

    def test_the_entry_carries_its_own_indexing(self):
        record = _entry().relabel("^d20260818-1u")
        assert record.line.label == "^d20260818-1u"
        assert record.support
        assert record.grounded

    def test_nothing_is_derived_from_a_surface(self, geo):
        """A round-trip through storage preserves the whole entry, surfaces absent."""
        store = IndexStore(geo)
        original = _entry().relabel("^d20260818-1u")
        store.put(original)
        loaded = store.get(original.id)
        assert loaded.line == original.line
        assert loaded.scope.address == original.scope.address
        assert loaded.support == original.support

    def test_an_entry_can_be_scoped_to_an_annotation_point(self, geo):
        store = IndexStore(geo)
        record = store.put(_entry(scope=ANNOTATION))
        assert store.get(record.id).scope.address == ANNOTATION


class TestAssertionHalf:
    def test_type_and_body_parse_off_a_kernel_line(self):
        assert split_statement("- [CT] the model wins ^d20260818-3u") == (
            "CT",
            "the model wins",
        )

    def test_storage_layout_does_not_change_the_entry(self, geo):
        """Reformat the bytes; the model is unchanged, so no drift is manufactured."""
        store = IndexStore(geo)
        record = store.put(_entry())
        path = store.root().record_path(record.id)
        path.write_text(json.dumps(json.loads(path.read_text("utf-8")), indent=7))
        assert store.get(record.id) == record

    def test_the_record_carries_no_content_hash(self):
        """Identity survives rewording, so a hash over content decides nothing."""
        record = _entry()
        assert not hasattr(record, "hash")
        assert "hash" not in record.to_json()["line"]

    def test_an_absent_edition_time_is_never_manufactured(self):
        """A missing time stays missing; reading a record does not invent one."""
        record = LineRecord.from_json(_entry().to_json())
        assert record.line.at is None


class TestLabelAndIdentity:
    def test_the_label_is_the_public_id_and_lives_under_line(self):
        record = _entry().relabel("d20260818-1u")
        assert record.line.label == "^d20260818-1u"
        assert record.to_json()["line"]["label"] == "^d20260818-1u"

    def test_relabelling_does_not_move_the_internal_id(self):
        record = _entry().relabel("^d20260818-1u")
        assert record.relabel("^d20260819-4u").id == record.id

    def test_the_rendered_line_is_type_body_label(self):
        record = _entry("the record is complete").relabel("^d20260818-1u")
        assert record.line.render() == "- [CT] the record is complete ^d20260818-1u"

    def test_amend_fixes_in_place_and_keeps_the_label(self):
        record = _entry("bad").relabel("^d20260818-1u")
        amended = record.amend("CT", "fixed")
        assert amended.id == record.id
        assert amended.line.label == "^d20260818-1u"

    def test_a_successor_is_a_new_line_in_the_same_trace(self):
        first = _entry("v1").relabel("^d20260818-1u")
        second = first.successor("CT", "v2")
        assert second.id != first.id
        assert second.trace == first.trace
        assert second.line.label is None, "a new version gets its own label"


class TestUnifiedStore:
    def test_a_label_resolves_to_its_entry_without_a_second_store(self, geo):
        store = IndexStore(geo)
        store.put(_entry().relabel("^d20260818-5u"))
        assert store.by_label("d20260818-5u") is not None

    def test_a_trace_gathers_its_members(self, geo):
        store = IndexStore(geo)
        first = store.put(_entry("v1"))
        store.put(first.successor("CT", "v2"))
        assert len(store.by_trace(first.trace)) == 2

    def test_minting_allocates_the_next_sequence(self, geo):
        store = IndexStore(geo)
        first = store.mint_label(store.put(_entry("a")))
        second = store.mint_label(store.put(_entry("b")))
        assert first.line.label != second.line.label

    def test_minting_is_idempotent(self, geo):
        store = IndexStore(geo)
        record = store.mint_label(store.put(_entry()))
        assert store.mint_label(record).line.label == record.line.label

    def test_missing_entry_is_an_error(self, geo):
        with pytest.raises(RecordStoreError, match="no index entry"):
            IndexStore(geo).get("ln_absent")

    def test_an_ungrounded_entry_may_simply_be_removed(self, geo):
        """It indexes nothing yet, so nothing is lost."""
        store = IndexStore(geo)
        record = store.put(_entry(support=()))
        store.remove(record.id)
        assert store.find(record.id) is None

    def test_a_grounded_entry_removes_without_ceremony(self, geo):
        """The index issues no verdict; git records the deletion and the linter reports it."""
        store = IndexStore(geo)
        record = store.put(_entry())
        store.remove(record.id)
        assert store.find(record.id) is None

    def test_no_removal_ledger_is_written(self, geo):
        store = IndexStore(geo)
        store.remove(store.put(_entry()).id)
        assert not list(geo.project_tier.glob("removals*"))

    def test_lookup_by_scope_and_session(self, geo):
        store = IndexStore(geo)
        store.put(_entry(support=(_support("addr-9", "sess-9"),)))
        assert store.by_scope(BLOCK)
        assert store.by_session("sess-9")

    def test_the_record_names_no_surface(self):
        """Where a line is, is the filesystem's answer — not a cache an agent writes."""
        assert "occurrences" not in _entry().to_json()["links"]


class TestReviewSplit:
    """The agent/user split is derived, so it is a computation and not a folder."""

    def test_the_store_keeps_one_folder_per_tier(self, geo):
        store = IndexStore(geo)
        record = store.put(_entry())
        assert store.root().record_path(record.id).exists()
        assert not (geo.project_tier / "index" / "agent").exists()

    def test_review_evidence_puts_a_trace_on_the_user_side(self, geo):
        store = IndexStore(geo)
        gate = GateRef("chat", "s1", "tok", "u", "a")
        agent = store.put(_entry("agent side"))
        user = store.put(_entry("user side").with_review(gate))
        derived = standings(store.all())
        assert derived[agent.id].side is ReviewSide.AGENT
        assert derived[user.id].side is ReviewSide.USER

    def test_nothing_writes_the_side(self, geo):
        store = IndexStore(geo)
        record = store.put(_entry())
        assert not hasattr(record, "review_index")
        assert not hasattr(store, "promote")


class TestGeography:
    def test_a_user_tier_entry_stays_out_of_the_project(self, geo):
        store = IndexStore(geo)
        record = store.put(_entry("local only"), tier=Tier.USER)
        assert store.root(Tier.USER).record_path(record.id).exists()
        assert not store.root(Tier.PROJECT).record_path(record.id).exists()

    def test_reads_span_both_tiers_as_one_index(self, geo):
        store = IndexStore(geo)
        store.put(_entry("ships"), tier=Tier.PROJECT)
        store.put(_entry("stays local"), tier=Tier.USER)
        assert len(store.all()) == 2

    def test_a_tier_can_be_read_alone(self, geo):
        store = IndexStore(geo)
        store.put(_entry("ships"), tier=Tier.PROJECT)
        store.put(_entry("stays local"), tier=Tier.USER)
        assert len(store.all(tier=Tier.USER)) == 1


class TestGroundingBoundary:
    def test_support_stores_refs_and_never_grounding_content(self, geo):
        store = IndexStore(geo)
        record = store.put(_entry())
        raw = store.root().record_path(record.id).read_text("utf-8")
        payload = json.loads(raw)["links"]["grounding"][0]
        assert set(payload) == {"archive", "session_id", "message_id"}

    def test_an_ungrounded_entry_is_legitimate(self):
        assert not _entry(support=()).grounded
