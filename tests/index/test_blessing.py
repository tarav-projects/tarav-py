# $kw: ^test-index-blessing --from Agentos.Index --note [DF] coverage for the grounded Blessing.Record and its depot
"""The `Blessing.Record`: an agent's claim that a POI is acceptable, and its evidence."""

from __future__ import annotations

import json

from tarav.index.linter import POI_TEST_MARKER
from tarav.index.record import IndexStore, LineRecord, SupportRef
from tarav.index.record.blessing import BlessingRecord, BlessingStore


def _support():
    return (SupportRef("chat", "s1", "m1"),)


class TestBlessingRecord:
    def test_create_mints_an_id_and_keeps_the_claim(self):
        record = BlessingRecord.create(
            "deadbeef", "DC", "legacy coordinates are migration debt", support=_support()
        )
        assert record.id.startswith("bl_")
        assert record.poi == "deadbeef"
        assert record.line.body == "legacy coordinates are migration debt"
        assert record.line.type == "DC"
        assert record.support == _support()

    def test_it_round_trips_through_json(self):
        record = BlessingRecord.create("deadbeef", "DC", "a claim", support=_support())
        assert BlessingRecord.from_json(record.to_json()) == record

    def test_the_line_carries_no_scope(self):
        """A blessing's explanation is a free Index.Line: it is hosted by no surface.

        Freeness is a property of the host, not a flag on the line -- which is why there is
        no scope field to leave empty and no `ScopeKind` naming a POI.
        """

        record = BlessingRecord.create("deadbeef", "DC", "a claim")
        assert not hasattr(record, "scope")


class TestBlessingStore:
    def test_a_blessing_round_trips_through_its_depot(self, geo):
        store = BlessingStore(geo)
        record = BlessingRecord.create("deadbeef", "DC", "a claim", support=_support())
        store.put(record)
        assert store.get(record.id) == record
        assert [r.id for r in store.all()] == [record.id]

    def test_blessings_and_index_records_do_not_share_a_depot(self, geo):
        """Different subjects, so different hosts -- which is what keeps the record checks
        from being offered a blessing and needing a filter to refuse it."""

        BlessingStore(geo).put(BlessingRecord.create("deadbeef", "DC", "a claim"))
        IndexStore(geo).put(LineRecord.create("d/design#Concept", "CT", "a line"))

        assert BlessingStore(geo).directory != IndexStore(geo).directory
        assert len(BlessingStore(geo).all()) == 1
        assert len(IndexStore(geo).all()) == 1

    def test_by_poi_finds_every_blessing_of_one_poi(self, geo):
        store = BlessingStore(geo)
        store.put(BlessingRecord.create("deadbeef", "DC", "first claim"))
        store.put(BlessingRecord.create("deadbeef", "DC", "second claim"))
        store.put(BlessingRecord.create("cafef00d", "DC", "other poi"))
        assert len(store.by_poi("deadbeef")) == 2

    def test_a_rewritten_blessing_replaces_rather_than_duplicates(self, geo):
        store = BlessingStore(geo)
        record = BlessingRecord.create("deadbeef", "DC", "a claim")
        store.put(record)
        store.put(record.amend("DC", "a corrected claim"))
        assert [r.line.body for r in store.all()] == ["a corrected claim"]


CHAPTER = """****

## Blessing.Probe

{lines}

****
"""


def _probe_project(root, *lines: str):
    marker = root / ".tarav" / "project.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps(
            {
                "class": "agentos.project",
                "schema_version": 1,
                "project_id": "11111111-1111-4111-8111-111111111111",
            }
        ),
        encoding="utf-8",
    )
    depot = root / "skills" / "tarav-pkg"
    depot.mkdir(parents=True, exist_ok=True)
    (depot / "000-INDEX.md").write_text("# test Index\n", encoding="utf-8")
    path = depot / "design" / "100-design.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(CHAPTER.format(lines="\n".join(lines)), encoding="utf-8")
    return path


class TestBlessCommandLine:
    """The whole loop, through the CLI, driven by the probe the linter exists to summon."""

    def _lint(self, project_root, capsys):
        from tarav.cli.cli import main

        assert main(["index", "--json", "linter", "--project", str(project_root),
                     "--limit", "1000"]) in (0, 1)
        return json.loads(capsys.readouterr().out)

    def _probes(self, document):
        return {
            item["subject"]: item
            for item in document["poi_instances"]["items"]
            if item["class_address"] == "Index.Linter/POI.Test"
        }

    def test_blessing_a_probe_silences_it_and_leaves_its_sibling(
        self, project_root, capsys, chat, monkeypatch
    ):
        from tarav.cli.cli import main

        chat("s1", [("m1", "user", "a probe is not a defect")])
        _probe_project(
            project_root,
            f"- [CT] first probe {POI_TEST_MARKER}#alpha",
            f"- [CT] second probe {POI_TEST_MARKER}#beta",
        )
        surface = "skills/tarav-pkg/design/100-design.md"

        before = self._probes(self._lint(project_root, capsys))
        assert {s.split("#")[-1] for s in before} == {"alpha", "beta"}
        alpha = before[f"{surface}#alpha"]["instance_id"]

        assert main([
            "index", "bless", "--poi-id", alpha, "--type", "DC",
            "--body", "a probe is placed deliberately and is not a defect",
            "--session", "s1", "--support", "m1",
        ]) == 0
        assert "grounded" in capsys.readouterr().out

        after = self._probes(self._lint(project_root, capsys))
        assert after[f"{surface}#alpha"]["status"] == "blessed"
        assert after[f"{surface}#beta"]["status"] == "failed"

    def test_an_ungrounded_blessing_from_the_cli_reports_its_own_standing(
        self, project_root, capsys, chat
    ):
        from tarav.cli.cli import main

        chat("s1", [("m1", "user", "anything")])
        _probe_project(project_root, f"- [CT] a probe {POI_TEST_MARKER}#alpha")
        alpha = next(iter(self._probes(self._lint(project_root, capsys)).values()))

        assert main([
            "index", "bless", "--poi-id", alpha["instance_id"],
            "--type", "DC", "--body", "trust me",
        ]) == 0
        assert "ungrounded" in capsys.readouterr().out

        classes = {
            item["class_address"]
            for item in self._lint(project_root, capsys)["poi_instances"]["items"]
        }
        assert "Index.Linter/Blessing.Ungrounded" in classes

    def test_the_listing_shows_each_blessing_with_its_derived_standing(
        self, project_root, capsys, chat
    ):
        from tarav.cli.cli import main

        chat("s1", [("m1", "user", "a probe is not a defect")])
        assert main([
            "index", "bless", "--poi-id", "deadbeef", "--type", "DC",
            "--body", "a claim", "--session", "s1", "--support", "m1",
        ]) == 0
        capsys.readouterr()

        assert main(["index", "blessings"]) == 0
        rendered = capsys.readouterr().out
        assert "deadbeef" in rendered
        assert "grounded" in rendered
