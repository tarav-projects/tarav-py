"""Independent coverage and per-batch review signals; checking never writes."""

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.actions.pois import POIResolutionAction
from tarav.l1.checks import Check, CheckPOI, CheckResult, CheckSuite, SituationCheck, SuiteCheckpoint
from tarav.l1.checks.chains import SituationChain
from tarav.l1.product_review import PRODUCT_REVIEW_SHIP


class CoverageRequired(CheckPOI):
    """Some mapped chunks do not belong to any live review batch."""

    action = "Tarav.ProductReview.Coverage.Required.Action"

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("28cbfcde-2b94-4fc8-9166-762c2f338b10"),
                          name="Tarav.ProductReview.Coverage.Required.POI", workflow=PRODUCT_REVIEW_SHIP)


class CoverageAction(POIResolutionAction):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("3937d2a6-e8ca-42f7-96f9-a96dff5f919e"),
                          name="Tarav.ProductReview.Coverage.Required.Action", workflow=PRODUCT_REVIEW_SHIP)


class BatchReviewRequired(CheckPOI):
    """A live batch has changed or its current revision has no completed review."""

    action = "Tarav.ProductReview.Batch.Required.Action"

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("819c54fb-7a80-4d93-af32-7cd088ff611d"),
                          name="Tarav.ProductReview.Batch.Required.POI", workflow=PRODUCT_REVIEW_SHIP)


class BatchReviewAction(POIResolutionAction):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("642ab467-8254-4c74-a115-ab378ba8643f"),
                          name="Tarav.ProductReview.Batch.Required.Action", workflow=PRODUCT_REVIEW_SHIP)


# tarav.breadcrumb 0e494f16ef08
class CoverageCheck(SituationCheck):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("12dc2f33-de92-44c3-9a99-4b85453b8867"),
                          name="Tarav.ProductReview.Coverage.Check", workflow=PRODUCT_REVIEW_SHIP)

    def __init__(self, report):
        super().__init__(situation={"repository_id": report["repository_id"]})
        self.report = report

    def _run(self):
        return CheckResult(self, status="completed", pois=[self.poi(
            CoverageRequired, message=f"{len(self.report['uncovered'])} mapped chunks need review batches",
            details={k: self.report[k] for k in ("map_id", "commit", "uncovered")})]
            if self.report["uncovered"] else [])


class BatchReviewCheck(SituationCheck):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("ff00cfca-0a6d-4f02-8bda-454e1ae5dc97"),
                          name="Tarav.ProductReview.Batch.Check", workflow=PRODUCT_REVIEW_SHIP)

    def __init__(self, repository_id, batch, *, map_id):
        super().__init__(situation={"repository_id": repository_id, "batch_id": batch["batch_id"]})
        self.batch, self.map_id = batch, map_id

    def _run(self):
        return CheckResult(self, status="completed", pois=[self.poi(
            BatchReviewRequired, message=f"Review batch {self.batch['title']}: {self.batch['state']}",
            details={**self.batch, "selected_map": self.map_id})]
            if self.batch["state"] != "reviewed" else [])


class CoverageChain(SituationChain):
    Check = CoverageCheck
    POIs = (CoverageRequired,)

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("823038b2-22b4-49dd-af14-e0c0cfdb0c49"),
                          name="Tarav.ProductReview.Coverage.Chain", workflow=PRODUCT_REVIEW_SHIP)


class BatchReviewChain(SituationChain):
    Check = BatchReviewCheck
    POIs = (BatchReviewRequired,)

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("c3421dfa-9090-466c-a0d8-ad35ac614977"),
                          name="Tarav.ProductReview.Batch.Chain", workflow=PRODUCT_REVIEW_SHIP)


class ReviewUnavailable(Check):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("9aee7d09-a177-4f7a-84ab-bc8e2688a935"),
                          name="Tarav.ProductReview.Unavailable.Check", workflow=PRODUCT_REVIEW_SHIP)

    def __init__(self, reason):
        super().__init__()
        self.reason = reason

    def _run(self):
        return CheckResult(self, status="incomplete", reason=self.reason)


class ProductReviewSuite(CheckSuite):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("198cbb25-e1dc-407e-8ccf-253a527e2ad6"),
                          name="Tarav.ProductReview.Suite", workflow=PRODUCT_REVIEW_SHIP)

    def __init__(self, tracker, *, map_id=None, horizon_days=None, now=None):
        self.tracker, self.map_id, self.horizon_days, self.now = tracker, map_id, horizon_days, now
        super().__init__(key=tracker.repository_id, name="Product Review Tracker",
                         repositories=[tracker.mapper.repository],
                         checkpoint_types={"batches": (CoverageCheck, BatchReviewCheck)})

    def produce(self):
        try:
            report = self.tracker.inspect(map_id=self.map_id, horizon_days=self.horizon_days, now=self.now)
        except (OSError, ValueError, RuntimeError, LookupError) as exc:
            yield ReviewUnavailable(str(exc))
            return
        yield CoverageCheck(report)
        for batch in report["batches"]:
            yield BatchReviewCheck(self.tracker.repository_id, batch, map_id=report["map_id"])
        yield SuiteCheckpoint("batches")


PRODUCT_REVIEW_CHECK_TYPES = (CoverageRequired, BatchReviewRequired, CoverageCheck, BatchReviewCheck,
                              CoverageChain, BatchReviewChain, ReviewUnavailable, ProductReviewSuite)
PRODUCT_REVIEW_ACTION_TYPES = (CoverageAction, BatchReviewAction)
