"""Tarav batches attach to existing class identities; the core accepts any Ship."""

from typing import Literal

from tarav.l0.kernel import TaravClass, TypeShip, current_records, entity
from tarav.l1.product_review import Batch, PRODUCT_REVIEW_SHIP

from .tracker import ReviewTracker


def _class_entity(subject, registry):
    """Follow the existing Type graph from trusted registry roots, without a copy."""
    pending = list(registry.types())
    seen = set()
    while pending:
        cls = pending.pop()
        if cls in seen:
            continue
        seen.add(cls)
        target = entity(cls)
        if target.id == subject:
            return target
        pending.extend(base.target for base in target.bases())
        owner = target.workflow
        if owner is not None:
            pending.append(type(owner))
    raise ValueError(f"Subject is not a known class identity: {subject}")


# tarav.breadcrumb 03e02735012a
class ClassBatch(Batch):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("45891a7f-aeb8-4d93-8ee6-186f8c2687e3"),
                          name="Tarav.ProductReview.ClassBatch", workflow=PRODUCT_REVIEW_SHIP)

    class RecordInterface(Batch.RecordInterface):
        type: Literal["Tarav.ProductReview.ClassBatch"]
        subject: TypeShip

    class Records(Batch.Records):
        def record_example(self):
            return {**super().record_example(), "subject": str(entity(Batch).id)}

    def subject_entity(self, *, records=None):
        """Open the live class, including its existing bases, Workflow and Context."""
        registry = records if records is not None else current_records()
        return _class_entity(self.typed.subject, registry)


class ClassReviewTracker(ReviewTracker):
    """Select class-bound batches without copying the product's Type graph."""

    Batch = ClassBatch

    def _subject(self, value):
        subject = TypeShip(str(super()._subject(value)))
        _class_entity(subject, self.store.records)
        return subject
