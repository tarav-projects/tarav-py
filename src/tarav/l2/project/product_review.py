"""Project configuration and integration for independent review tracking."""

from pydantic import BaseModel, ConfigDict, Field

from tarav.l0.kernel import NamespaceBase, TaravClass, TypeShip
from tarav.l1.checks import CheckSuite
from tarav.l1.git.hooks import GitConfig
from tarav.l1.product_review import PRODUCT_REVIEW_SHIP
from tarav.l1.project.config import ProjectConfig
from tarav.l2.product_review import ReviewTracker
from tarav.l2.product_review.checks import (
    BatchReviewCheck, CoverageCheck, ProductReviewSuite, ReviewUnavailable,
)

from .product_mapping import configured_mapper


class ProductReviewConfig(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    enabled: bool = False
    horizon_days: int = Field(default=5, ge=0)


def configured_tracker(repository, repository_id, *, root=None, maps_root=None):
    config = ProjectConfig(repository).section("product_review", ProductReviewConfig)
    return ReviewTracker(configured_mapper(repository, repository_id, root=maps_root), root=root,
                         horizon_days=config.horizon_days if config else 5)


class ReviewManager(NamespaceBase):
    def open(self):
        binding = ProjectConfig(self.obj.root).section("git", GitConfig)
        if binding is None or binding.repository is None:
            raise ValueError("Product Review requires an explicit Git repository identity binding")
        return configured_tracker(self.obj.root, binding.repository)

    def suite(self):
        return ProjectReviewSuite(self)


class ProjectReviewSuite(CheckSuite):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("aeff7281-e3b1-435d-93cd-044b9e2b2743"),
                          name="Tarav.Project.ProductReview.Suite", workflow=PRODUCT_REVIEW_SHIP)

    def __init__(self, manager):
        self.manager = manager
        super().__init__(key=str(manager.obj.id), name="Project Product Review",
                         checkpoint_types={"batches": (CoverageCheck, BatchReviewCheck)})

    def produce(self):
        try:
            config = ProjectConfig(self.manager.obj.root).section("product_review", ProductReviewConfig)
            if not config or not config.enabled:
                return
            tracker = self.manager.open()
        except (OSError, ValueError, RuntimeError, LookupError) as exc:
            yield ReviewUnavailable(str(exc))
            return
        yield ProductReviewSuite(tracker)
