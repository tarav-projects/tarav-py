"""A bench for tests: raise POIs in the run of an owned suite and bless them through Actions."""

from __future__ import annotations

from datetime import datetime, timezone

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.actions import ACTIONS_WORKFLOW_SHIP, ActionRunStore, StepRunner
from tarav.l1.actions import register_action
from tarav.l1.actions.pois import BlessableResolution, action_id
from tarav.l1.actions.project import ProjectActions
from tarav.l1.actions.blessing import BLESSED, Blessing, BlessingInput
from tarav.l1.checks import Check, CheckResult, CheckSuite
from tarav.l1.operator_context import OperatorContextStore
from tarav.l1.records import RecordRegistry

TARGET = {"id": "bench", "name": "bench", "root": "/bench"}


class BenchCheck(Check):
    """Stands for whatever check raised the POIs handed to the bench."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("e4a90c1b-6f27-4d58-9b03-2c8d7e5f1a46"),
                          name="Tarav.Test.Bench.Check", workflow=ACTIONS_WORKFLOW_SHIP)


@register_action
class BenchResolution(BlessableResolution):
    """The action of the example POIs these tests bless; they name it as `BLESSABLE`."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("e1d807a2-a5d4-4d20-9cf3-13370d83c1fa"),
                          name="Tarav.Test.Bench.Resolution", workflow=ACTIONS_WORKFLOW_SHIP)


BLESSABLE = "Tarav.Test.Bench.Resolution"


# tarav.breadcrumb 37944529d175
class Bench:
    def __init__(self, root, records) -> None:
        registry = RecordRegistry(root, records)
        self.runs = ActionRunStore(registry)
        self.contexts = OperatorContextStore(registry)
        self.actor: dict | None = {"provider": "example", "session_id": "reviewer"}
        self.at = datetime.now(timezone.utc)
        self.runner = StepRunner(runs=self.runs, contexts=self.contexts,
                                 session=lambda: self.actor, now=lambda: self.at.isoformat())
        self.actions = ProjectActions(TARGET, self.runs, now=lambda: self.at.isoformat())
        self.pois = self.actions  # how the bench Project's actions stand for a POI
        self.raised: list = []

    def produce(self, *pois) -> dict:
        """One run of the bench checks that produces every POI raised so far, and these."""
        self.raised.extend(pois)
        run = CheckSuite()
        for poi in self.raised:
            check = getattr(poi, "check", None) or BenchCheck()
            run.add(CheckResult(check, status="completed", pois=[poi]))
        return self.actions.update(run)

    def bless(self, poi, *, reason: str = "Reviewed.", support=(), at=None,
              actor: str | None = None) -> Blessing:
        """Produce the POI in a run of the bench checks and close its action with a blessing."""
        if at is not None:
            self.at = at
        if actor is not None:
            self.actor = {"provider": "example", "session_id": actor}
        self.produce(poi)
        key = self.contexts.put(BlessingInput.new(reason=reason, support=list(support)))
        run = self.runner.close(str(action_id(poi)), key, exit=BLESSED)
        assert run.exit == BLESSED, run.data["tape"][-1]
        return self.pois.blessing(poi)
