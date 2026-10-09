"""POI tracking: check results are data points on durable, multi-axis records."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from tarav.l0.kernel import TaravClass, TypeShip, WorkflowShip, entity
from tarav.l1.blessings import BlessablePOI
from tarav.l1.checks import Check, CheckPOI, CheckResult, CheckRun, CheckSuite, SituationCheck
from tarav.l1.context.query import ContextQueryService, IdentityContextQuery
from tarav.l1.poi.rendering import renderer
from tarav.l1.poi.reporting import ReportedPOIContext, ReportedPOIResolver, ReportedPOIStore
from tarav.l1.poi_tracking import (
    ACTIVE, NOT_EVALUATED, PASSED, TRACKED_POI_VIEW, CheckObservation, POITracker, TrackAxis,
    TrackablePOI, TrackingError, TrackRecordStore, status_vector,
)
from tarav.l1.poi_tracking.views import (
    TRACKING_POI_RENDERER, TrackRecordResolver, TrackedPOIContext, tracking_selection,
)
from tarav.l1.settings import SettingsError
from tarav.l2.blessings.tracking import BlessingAxis
from tarav.l2.project import Project
from tarav.l3.runtime import create_runtime

CLOCK = datetime(2026, 10, 9, tzinfo=timezone.utc)


class FilePOI(CheckPOI, BlessablePOI):
    """A file needs attention."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("f5b57dbe-ad71-41e8-b928-7cff9c76c983"),
                          name="Tarav.Test.Tracking.FilePOI")


class SwitchablePOI(CheckPOI):
    """A POI Type whose instances may switch tracking off."""

    settings_include = (TrackablePOI,)

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("2ee18d17-5738-4c33-aff9-dc686eaf6e9f"),
                          name="Tarav.Test.Tracking.SwitchablePOI")


class FileCheck(SituationCheck):
    """Raises one POI per listed file; the situation says which folder it is."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("5c0b7b0e-58f5-4f5e-8a6f-3d6f6f5f4a01"),
                          name="Tarav.Test.Tracking.FileCheck")

    def __init__(self, folder, *, bad=(), status="completed", poi_type=FilePOI, untracked=()):
        super().__init__(situation={"folder": folder})
        self.bad, self.status, self.poi_type, self.untracked = bad, status, poi_type, untracked

    def _run(self):
        pois = []
        for name in self.bad:
            poi = self.poi_type(self, f"{name} needs attention",
                                situation={"folder": self.situation["folder"]},
                                details={"file": name})
            if name in self.untracked:
                poi.settings.set("tracked", value=False)
            pois.append(poi)
        return CheckResult(self, status=self.status, pois=pois)


class AnonymousCheck(Check):
    """A check that cannot say which check it is across runs."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("5c0b7b0e-58f5-4f5e-8a6f-3d6f6f5f4a02"),
                          name="Tarav.Test.Tracking.AnonymousCheck")

    def __init__(self, raise_poi=True):
        super().__init__()
        self.raise_poi = raise_poi

    def _run(self):
        pois = [FilePOI(self, "anonymous", situation={"anonymous": 1})] if self.raise_poi else []
        return CheckResult(self, status="completed", pois=pois)


class ReviewAxis(TrackAxis):
    """An axis another workflow contributes; the tracker does not know what it means."""

    key = "review"
    values = ("open", "closed")

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("5c0b7b0e-58f5-4f5e-8a6f-3d6f6f5f4a03"),
                          name="Tarav.Test.Tracking.ReviewAxis",
                          workflow=WorkflowShip("5c0b7b0e-58f5-4f5e-8a6f-3d6f6f5f4a04"))


def observe(tracker, *checks, whole=False, step=0):
    run = CheckSuite(checks).run()
    return run, run.track(into=tracker, whole=whole, at=CLOCK + timedelta(minutes=step))


def only(tracker):
    (record,) = tracker.records()
    return record


def test_a_situation_check_has_an_identity_across_runs_and_a_plain_check_has_none():
    assert FileCheck("src").identity == FileCheck("src").identity
    assert FileCheck("src").identity != FileCheck("docs").identity
    assert AnonymousCheck().identity is None


# tarav.breadcrumb 34832f9c2a9b17d33c62f47bceca921c8667ff4daebc5b725df4496e203ab2cc
def test_raised_then_absent_from_the_same_completed_check_is_active_then_passed(tmp_path):
    tracker = POITracker(TrackRecordStore(tmp_path))
    run, summary = observe(tracker, FileCheck("src", bad=("a.py",)))
    record = only(tracker)
    assert summary["created"] == 1 and status_vector(record) == {"observation": ACTIVE}
    assert record["poi_id"] == run.pois()[0].identity
    assert record["check"] == {"type": "Tarav.Test.Tracking.FileCheck",
                               "identity": FileCheck("src").identity}
    assert "help" not in record["poi"]

    observe(tracker, FileCheck("src"), step=1)
    observe(tracker, FileCheck("src"), step=2)
    axis = only(tracker)["axes"]["observation"]
    assert axis["value"] == PASSED
    assert [change["value"] for change in axis["history"]] == [ACTIVE, PASSED]
    assert axis["data"]["last_active_at"] == CLOCK.isoformat()
    assert axis["data"]["last_evaluated_at"] == (CLOCK + timedelta(minutes=2)).isoformat()

    observe(tracker, FileCheck("src", bad=("a.py",)), step=3)
    axis = only(tracker)["axes"]["observation"]
    assert [change["value"] for change in axis["history"]] == [ACTIVE, PASSED, ACTIVE]
    assert axis["history"][-1]["by"]["check_identity"] == FileCheck("src").identity
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_a_check_that_did_not_complete_or_did_not_run_is_no_evidence(tmp_path):
    tracker = POITracker(TrackRecordStore(tmp_path))
    observe(tracker, FileCheck("src", bad=("a.py",)))
    observe(tracker, FileCheck("docs"), step=1)  # another check; a partial run
    assert status_vector(only(tracker)) == {"observation": ACTIVE}
    observe(tracker, FileCheck("src", status="failed"), step=2)
    assert status_vector(only(tracker)) == {"observation": NOT_EVALUATED}
    observe(tracker, FileCheck("src", bad=("a.py",)), step=3)
    observe(tracker, FileCheck("docs"), whole=True, step=4)  # the whole suite, without it
    axis = only(tracker)["axes"]["observation"]
    assert axis["value"] == NOT_EVALUATED
    assert axis["data"]["last_evaluated_at"] == (CLOCK + timedelta(minutes=3)).isoformat()


def test_a_poi_of_a_check_without_identity_never_passes(tmp_path):
    tracker = POITracker(TrackRecordStore(tmp_path))
    _, summary = observe(tracker, AnonymousCheck(), whole=True)
    assert summary["points_without_check_identity"] == 1
    assert only(tracker)["check"]["identity"] is None
    observe(tracker, AnonymousCheck(raise_poi=False), whole=True, step=1)
    assert status_vector(only(tracker)) == {"observation": NOT_EVALUATED}


def test_an_instance_can_switch_tracking_off_only_where_its_type_includes_the_setting(tmp_path):
    tracker = POITracker(TrackRecordStore(tmp_path))
    _, summary = observe(tracker, FileCheck("src", bad=("a.py", "b.py"), poi_type=SwitchablePOI,
                                            untracked=("b.py",)))
    assert summary["pois_not_tracked"] == 1 and summary["created"] == 1
    plain = FilePOI(FileCheck("src"), "plain", situation={"folder": "src"})
    assert plain.tracking_enabled()
    with pytest.raises(SettingsError):
        plain.settings.set("tracked", value=False)


def test_another_workflow_contributes_an_axis_that_changes_independently(tmp_path):
    tracker = POITracker(TrackRecordStore(tmp_path), axes=(ReviewAxis(),))
    run, _ = observe(tracker, FileCheck("src", bad=("a.py",)), FileCheck("docs", bad=("b.md",)))
    poi_id = run.pois()[0].identity
    reviewer = {"kind": "agent", "name": "reviewer"}
    tracker.set(poi_id[:12], axis="review", value="closed", by=reviewer, at=CLOCK)
    observe(tracker, FileCheck("src"), FileCheck("docs", bad=("b.md",)), step=1)
    closed = tracker.records(axes={"review": "closed"})
    assert [status_vector(record) for record in closed] == [
        {"observation": PASSED, "review": "closed"}]
    entry = closed[0]["axes"]["review"]
    assert entry["owner_workflow"] == "5c0b7b0e-58f5-4f5e-8a6f-3d6f6f5f4a04"
    assert entry["history"] == [{"at": CLOCK.isoformat(), "value": "closed", "by": reviewer}]
    assert len(tracker.records(axes={"observation": ACTIVE})) == 1
    assert tracker.records(axes={"observation": ACTIVE, "review": "closed"}) == []
    with pytest.raises(TrackingError, match="does not accept"):
        tracker.set(poi_id, axis="review", value="maybe", by=reviewer)
    with pytest.raises(TrackingError, match="only by its owner"):
        tracker.set(poi_id, axis="observation", value=PASSED, by=reviewer)
    with pytest.raises(TrackingError, match="Unknown axis"):
        tracker.records(axes={"mood": "good"})
    with pytest.raises(TrackingError, match="already contributed"):
        POITracker(TrackRecordStore(tmp_path), axes=(ReviewAxis(), ReviewAxis()))


def _project(tmp_path):
    marker = tmp_path / ".tarav" / "project.json"
    marker.parent.mkdir()
    marker.write_text(json.dumps(Project.records.record_example()), encoding="utf-8")
    return Project.from_path(tmp_path)


def test_the_blessing_axis_reads_the_project_blessing_store(tmp_path):
    create_runtime(archive_root=tmp_path / "archive", record_types=(FilePOI,))
    project = _project(tmp_path)
    assert project.poi_tracking().store.root == tmp_path / ".tarav" / "poi-tracking"
    assert not project.poi_tracking().store.root.exists()
    run, _ = observe(project.poi_tracking(), FileCheck("src", bad=("a.py",)))
    assert status_vector(only(project.poi_tracking())) == {
        "observation": ACTIVE, "blessing": "unblessed"}
    project.decisions().blessings().bless(
        run.pois()[0], actor={"type": "Example.Actor", "locator": {"name": "reviewer"}},
        rationale="Accepted for now")
    # Reading shows the blessing at once and writes nothing.
    read = only(project.poi_tracking())
    assert status_vector(read) == {"observation": ACTIVE, "blessing": "blessed"}
    assert len(read["axes"]["blessing"]["history"]) == 1
    # The next observation puts the change in the axis history; observation is untouched.
    observe(project.poi_tracking(), FileCheck("src", bad=("a.py",)), step=1)
    axes = only(project.poi_tracking())["axes"]
    assert [change["value"] for change in axes["blessing"]["history"]] == [
        "unblessed", "blessed"]
    assert axes["blessing"]["type"] == entity(BlessingAxis).name
    assert len(axes["observation"]["history"]) == 1


def test_unreadable_record_files_are_notified_and_skipped(tmp_path):
    tracker = POITracker(TrackRecordStore(tmp_path))
    observe(tracker, FileCheck("src", bad=("a.py",)))
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    with pytest.warns(UserWarning, match="Track record skipped"):
        assert len(tracker.records()) == 1


def test_records_render_through_the_registry_and_open_through_context(tmp_path):
    tracker = POITracker(TrackRecordStore(tmp_path / "store"), axes=(ReviewAxis(),))
    run, _ = observe(tracker, FileCheck("src", bad=("a.py",)))
    poi_id = run.pois()[0].identity
    selection = tracking_selection(tracker.report(axes={"observation": ACTIVE}))
    for name in (TRACKING_POI_RENDERER, "Tarav.POI.Default.Renderer",
                 "Tarav.POI.JsonLines.Renderer"):
        for level in ("line", "record", "context"):
            content = renderer(name).render(selection, level=level)
            assert poi_id[:12] in content
            assert f"tarav context --id {poi_id[:12]} --view {TRACKED_POI_VIEW}" in content
    text = renderer(TRACKING_POI_RENDERER).render(selection)
    assert "observation=active" in text and "observation: active 1" in text

    reported = ReportedPOIStore(tmp_path / "reports")
    reported.retain(run.pois(), project={"id": "p", "name": "p"})
    service = ContextQueryService()
    service.register_resolver("reported-poi", ReportedPOIResolver(reported))
    service.register_resolver("tracked-poi", TrackRecordResolver(lambda: [tmp_path / "store"]))
    service.register_view("reported-poi", ReportedPOIContext)
    service.register_view(TRACKED_POI_VIEW, TrackedPOIContext)
    answer = service.open(IdentityContextQuery(poi_id[:12], view=TRACKED_POI_VIEW))
    assert [entry.name for entry in answer.target.ls()] == [
        "status", "poi", "check", "axes", "reported"]
    status = service.open(IdentityContextQuery(poi_id[:12], view=TRACKED_POI_VIEW,
                                               path=("status",)))
    assert status.target.records.to_record()["value"] == {"observation": ACTIVE}
    # Without the view, and with the reported view, the reported POI is the one subject.
    assert service.open(IdentityContextQuery(poi_id[:12])).subject.identity == poi_id
    pointer = service.open(IdentityContextQuery(poi_id[:12], view="reported-poi",
                                                path=("track-record",)))
    assert TRACKED_POI_VIEW in pointer.target.records.to_record()["value"][0]


def test_the_data_point_can_be_built_by_a_script_without_a_check_run(tmp_path):
    tracker = POITracker(TrackRecordStore(tmp_path))
    poi = FilePOI(FileCheck("src"), "by hand", situation={"folder": "src"})
    tracker.observe([CheckObservation("Some.Check", "identity-1", "completed", (poi,))], at=CLOCK)
    tracker.observe([CheckObservation("Some.Check", "identity-1", "completed")], at=CLOCK)
    assert status_vector(only(tracker)) == {"observation": PASSED}
    with pytest.raises(TypeError):
        tracker.observe([CheckRun()])
