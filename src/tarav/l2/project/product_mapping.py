"""Project integration policy over the independent Product Mapping workflow."""

from pydantic import BaseModel, ConfigDict, Field

from tarav.l0.kernel import NamespaceBase, TaravClass, TypeShip
from tarav.l1.checks import Check, CheckResult, CheckSuite, SuiteCheckpoint
from tarav.l1.git.hooks import GitConfig
from tarav.l1.product_mapping import ProductMapper
from tarav.l1.product_mapping.checks import MappingFreshnessCheck, ProductMappingSuite
from tarav.l1.project.config import ProjectConfig
from tarav.l1.project.workflow import PROJECT_WORKFLOW_SHIP


# tarav.breadcrumb a885ca2acfd0
class ProductMappingConfig(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    enabled: bool = False
    max_age_days: int = Field(default=5, ge=0)
    include: list[str] = Field(default_factory=lambda: ["*"])
    exclude: list[str] = Field(default_factory=list)


def configured_mapper(repository, repository_id, *, root=None):
    """Apply the selected Project's controls without coupling the core to Projects."""
    config = ProjectConfig(repository).section("product_mapping", ProductMappingConfig)
    return ProductMapper(repository, repository_id, root=root,
                         include=config.include if config else None,
                         exclude=config.exclude if config else None)


class MappingLoadCheck(Check):
    """The selected Project mapping configuration cannot be loaded."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("888e9d85-9fd8-4556-a1fa-bbf041c5941e"),
                          name="Tarav.Project.ProductMapping.Load", workflow=PROJECT_WORKFLOW_SHIP)

    def __init__(self, reason):
        super().__init__()
        self.reason = reason

    def _run(self):
        return CheckResult(self, status="incomplete", reason=self.reason)


# tarav.breadcrumb 44285f334384
class MappingManager(NamespaceBase):
    """Own the Project's mapping selection and maintenance-check integration."""

    def open(self):
        settings = ProjectConfig(self.obj.root)
        binding = settings.section("git", GitConfig)
        if binding is None or binding.repository is None:
            raise ValueError("Product Mapping requires an explicit Git repository identity binding")
        return configured_mapper(self.obj.root, binding.repository)

    def suite(self):
        def produce(_suite):
            try:
                config = ProjectConfig(self.obj.root).section("product_mapping", ProductMappingConfig)
                if config and config.enabled:
                    yield ProductMappingSuite(self.open(), max_age_days=config.max_age_days)
                    yield SuiteCheckpoint("enabled")
            except (OSError, ValueError, RuntimeError) as exc:
                yield MappingLoadCheck(str(exc))
        # An identified suite prevents a disabled integration from closing old actions.
        return MappingProjectSuite(produce, key=str(self.obj.id), name="Project Product Mapping",
                                   checkpoint_types={"enabled": (MappingFreshnessCheck,)})


class MappingProjectSuite(CheckSuite):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("a6d24784-d3e4-43e9-b7a1-e3b37e740242"),
                          name="Tarav.Project.ProductMapping.Suite", workflow=PROJECT_WORKFLOW_SHIP)
