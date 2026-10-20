"""Mechanical Notebook evidence requirements as ordinary Situation Chains."""

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.actions.pois import POIResolutionAction
from tarav.l1.checks import CheckPOI, CheckResult, CheckSuite, SituationCheck
from tarav.l1.checks.chains import SituationChain
from tarav.l1.lines import Line
from tarav.l1.notebook import Notebook
from tarav.l1.notebook.workflow import NOTEBOOK_WORKFLOW_SHIP
from tarav.l2.notebook_capture import NotebookCapture, requirements
from tarav.l2.project.notebook import ProjectNotebook


def _type(cls, identity, name):
    return TaravClass(target=cls, id=TypeShip(identity), name=name, workflow=NOTEBOOK_WORKFLOW_SHIP)


class SupportMissing(CheckPOI):
    """A required current support set is absent or empty."""
    action = "Tarav.Notebook.Support.Missing.Action"

    @classmethod
    def class_entity(cls):
        return _type(cls, "ce5a32fd-b923-497f-afdc-10c30f90c24c", "Tarav.Notebook.Support.Missing.POI")


class SupportStale(CheckPOI):
    """Retained support concerns a different Line or context state."""
    action = "Tarav.Notebook.Support.Stale.Action"

    @classmethod
    def class_entity(cls):
        return _type(cls, "cce8c092-9f22-4af1-a7a0-0589ed071f14", "Tarav.Notebook.Support.Stale.POI")


class SupportInvalid(CheckPOI):
    """A support relationship fails its mechanical contract."""
    action = "Tarav.Notebook.Support.Invalid.Action"

    @classmethod
    def class_entity(cls):
        return _type(cls, "2c4e2501-186b-415a-bcc3-36fdabef81e5", "Tarav.Notebook.Support.Invalid.POI")


class SupportUnavailable(CheckPOI):
    """Required support evidence cannot currently be resolved."""
    action = "Tarav.Notebook.Support.Unavailable.Action"

    @classmethod
    def class_entity(cls):
        return _type(cls, "9169d159-14e8-4144-8a93-201469307599", "Tarav.Notebook.Support.Unavailable.POI")


class ReviewMissing(CheckPOI):
    """The current Line requires explicit review evidence."""
    action = "Tarav.Notebook.Review.Missing.Action"

    @classmethod
    def class_entity(cls):
        return _type(cls, "d100870e-92a7-4650-8a19-c89bd8725cd7", "Tarav.Notebook.Review.Missing.POI")


class ReviewStale(CheckPOI):
    """Retained review concerns earlier wording or authoring context."""
    action = "Tarav.Notebook.Review.Stale.Action"

    @classmethod
    def class_entity(cls):
        return _type(cls, "4d514301-f8ef-4ff7-a747-b4f23a6b8e36", "Tarav.Notebook.Review.Stale.POI")


class ReviewInvalid(CheckPOI):
    """Explicit review fails its token, role, order or presentation contract."""
    action = "Tarav.Notebook.Review.Invalid.Action"

    @classmethod
    def class_entity(cls):
        return _type(cls, "60ad3ce4-663b-4f0e-8ca4-8d8cd735a3a6", "Tarav.Notebook.Review.Invalid.POI")


class ReviewUnavailable(CheckPOI):
    """Review evidence cannot currently be resolved."""
    action = "Tarav.Notebook.Review.Unavailable.Action"

    @classmethod
    def class_entity(cls):
        return _type(cls, "b9bcfe48-2ef9-4258-b2f2-807a86eeb7c5", "Tarav.Notebook.Review.Unavailable.POI")


class NotebookUnavailable(CheckPOI):
    """An existing Project notebook cannot be loaded for evidence checking."""
    action = "Tarav.Notebook.Access.Unavailable.Action"

    @classmethod
    def class_entity(cls):
        return _type(cls, "fa526959-26bc-4df7-9dd2-1bb58014e9d7", "Tarav.Notebook.Access.Unavailable.POI")


class SupportMissingAction(POIResolutionAction):
    @classmethod
    def class_entity(cls):
        return _type(cls, "d1f42b8e-f31e-469c-9081-3c363500ac11", SupportMissing.action)


class SupportStaleAction(POIResolutionAction):
    @classmethod
    def class_entity(cls):
        return _type(cls, "ff686540-ea85-4ed8-a6a5-9b878c2d8d54", SupportStale.action)


class SupportInvalidAction(POIResolutionAction):
    @classmethod
    def class_entity(cls):
        return _type(cls, "7b89d8a1-d836-4b01-9e82-dea14a147180", SupportInvalid.action)


class SupportUnavailableAction(POIResolutionAction):
    @classmethod
    def class_entity(cls):
        return _type(cls, "505194b6-de07-41b2-95a5-bf7330736e2e", SupportUnavailable.action)


class ReviewMissingAction(POIResolutionAction):
    @classmethod
    def class_entity(cls):
        return _type(cls, "c62377ac-7e2a-457d-93d0-c9206f8c733e", ReviewMissing.action)


class ReviewStaleAction(POIResolutionAction):
    @classmethod
    def class_entity(cls):
        return _type(cls, "21304678-03e0-4419-b0b3-f2e50237aa3e", ReviewStale.action)


class ReviewInvalidAction(POIResolutionAction):
    @classmethod
    def class_entity(cls):
        return _type(cls, "78ac3b02-2e40-4f34-b9ed-342e71f06222", ReviewInvalid.action)


class ReviewUnavailableAction(POIResolutionAction):
    @classmethod
    def class_entity(cls):
        return _type(cls, "44230f78-8c70-4141-8ffc-18d6bb1fa3e8", ReviewUnavailable.action)


class NotebookUnavailableAction(POIResolutionAction):
    @classmethod
    def class_entity(cls):
        return _type(cls, "ed7c7620-9f7b-46af-8c9b-9b62127257c6", NotebookUnavailable.action)


class EvidenceCheck(SituationCheck):
    @classmethod
    def class_entity(cls):
        return _type(cls, "1ca4e85c-dc75-45c3-80af-85f1bd1d7162", "Tarav.Notebook.Evidence.Check")

    def __init__(self, *, situation, problems):
        super().__init__(situation=situation)
        self.problems = problems

    def _run(self):
        pois = [self.poi(self.problem_types[p.kind], message=p.message) for p in self.problems]
        return CheckResult(self, status="incomplete" if any(p.kind == "Unavailable" for p in self.problems)
                           else "completed", pois=pois)


# tarav.breadcrumb ee675dd8c679
class SupportCheck(EvidenceCheck):
    problem_types = {"Missing": SupportMissing, "Stale": SupportStale,
                     "Invalid": SupportInvalid, "Unavailable": SupportUnavailable}

    @classmethod
    def class_entity(cls):
        return _type(cls, "6b7eed8e-90fa-4677-ab28-782e5dfd6673", "Tarav.Notebook.Support.Check")


class ReviewCheck(EvidenceCheck):
    problem_types = {"Missing": ReviewMissing, "Stale": ReviewStale,
                     "Invalid": ReviewInvalid, "Unavailable": ReviewUnavailable}

    @classmethod
    def class_entity(cls):
        return _type(cls, "d798b3bf-7947-4c8f-915d-3cc3d312cf8c", "Tarav.Notebook.Review.Check")


class SupportChain(SituationChain):
    Check = SupportCheck
    POIs = (SupportMissing, SupportStale, SupportInvalid, SupportUnavailable)

    @classmethod
    def class_entity(cls):
        return _type(cls, "9e96d67b-b594-4c92-8232-acf13b8b2547", "Tarav.Notebook.Support.Chain")


class ReviewChain(SituationChain):
    Check = ReviewCheck
    POIs = (ReviewMissing, ReviewStale, ReviewInvalid, ReviewUnavailable)

    @classmethod
    def class_entity(cls):
        return _type(cls, "263f48cb-6ce1-46bf-8a21-3609bb044359", "Tarav.Notebook.Review.Chain")


class NotebookAccessCheck(SituationCheck):
    @classmethod
    def class_entity(cls):
        return _type(cls, "1024362c-ec69-459f-bb89-7b15220c3fb2", "Tarav.Notebook.Access.Check")

    def __init__(self, *, situation, binding):
        super().__init__(situation=situation)
        self.binding, self.root, self.error = binding, None, None

    def _run(self):
        try:
            if self.binding.notebook.store.path(str(self.binding.root_ship)).exists():
                self.root = self.binding.root
        except (OSError, ValueError, TypeError, LookupError, RuntimeError) as exc:
            self.error = str(exc)
            return CheckResult(self, status="incomplete", pois=(self.poi(
                NotebookUnavailable, message=f"Cannot load Project notebook: {exc}"),))
        return CheckResult(self, status="completed")


class NotebookAccessChain(SituationChain):
    Check = NotebookAccessCheck
    POIs = (NotebookUnavailable,)

    @classmethod
    def class_entity(cls):
        return _type(cls, "d07e6b54-f172-4dcb-8eac-6f6ed04477ab", "Tarav.Notebook.Access.Chain")


# tarav.breadcrumb bf66d81da834
class NotebookEvidenceSuite(CheckSuite):
    """Inspect existing evidence-bearing content; never provision or retrofit data."""

    @classmethod
    def class_entity(cls):
        return _type(cls, "513f3edc-fb20-4c15-84a0-cef7e12f37c6", "Tarav.Notebook.Evidence.Suite")

    def __init__(self, project, *, capture=None):
        self.project = project
        self.capture = capture if capture is not None else NotebookCapture(Notebook())
        super().__init__(name="Notebook evidence", key=str(project.id))

    def produce(self):
        binding = ProjectNotebook(self.project, notebook=self.capture.notebook)
        access = NotebookAccessChain({"project": str(self.project.id),
                                      "root": str(binding.root_ship)}).check(binding=binding)
        yield access
        if access.error is not None:
            self._refused += 1
            return
        if access.root is None:
            return
        for line in access.root.walk():
            if not isinstance(line, Line):
                continue
            support, review = requirements(line)
            support_ids = list(map(str, getattr(line, "support_ships", ())))
            review_ids = list(map(str, getattr(line, "review_ships", ())))
            if not (support or review or support_ids or review_ids):
                continue
            inspected = self.capture.inspect(line)
            situation = {"project": str(self.project.id), "line": str(line.id),
                         "state": inspected["state"]["digest"],
                         "support_required": support, "review_required": review,
                         "support": support_ids, "review": review_ids}
            if support or support_ids:
                yield SupportChain(situation).check(problems=inspected["support"])
            if review or review_ids:
                yield ReviewChain(situation).check(problems=inspected["review"])


NOTEBOOK_EVIDENCE_POIS = (*SupportChain.POIs, *ReviewChain.POIs, NotebookUnavailable)
NOTEBOOK_EVIDENCE_ACTIONS = (
    SupportMissingAction, SupportStaleAction, SupportInvalidAction, SupportUnavailableAction,
    ReviewMissingAction, ReviewStaleAction, ReviewInvalidAction, ReviewUnavailableAction,
    NotebookUnavailableAction,
)
