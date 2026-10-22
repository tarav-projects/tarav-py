"""One freshness signal per repository; checks never advance its map."""

from datetime import datetime, timedelta, timezone

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.actions.pois import POIResolutionAction
from tarav.l1.checks import CheckPOI, CheckResult, CheckSuite, SituationCheck
from tarav.l1.checks.chains import SituationChain

from .workflow import PRODUCT_MAPPING_SHIP


class MappingUpdateRequired(CheckPOI):
    """A map is missing, has outdated selection, or has newer commits beyond its freshness window."""

    action = "Tarav.ProductMapping.Update.Action"

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("18d67416-9682-4ad9-97db-3c80bf8116e3"),
                          name="Tarav.ProductMapping.Update.POI", workflow=PRODUCT_MAPPING_SHIP)


class MappingUpdateAction(POIResolutionAction):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("ca66dd7d-5828-4eaa-a3f4-8dd4e15456a5"),
                          name="Tarav.ProductMapping.Update.Action", workflow=PRODUCT_MAPPING_SHIP)


# tarav.breadcrumb 75d4bc18878e
class MappingFreshnessCheck(SituationCheck):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("2bcbbfc5-4d24-4525-862d-0a7ff808a8b6"),
                          name="Tarav.ProductMapping.Check", workflow=PRODUCT_MAPPING_SHIP)

    def __init__(self, *, mapper, max_age_days=5, now=None):
        if max_age_days < 0:
            raise ValueError("Map freshness days must be nonnegative")
        super().__init__(situation={"repository_id": mapper.repository_id})
        self.mapper, self.max_age_days = mapper, max_age_days
        self.now = now or datetime.now(timezone.utc)

    def _run(self):
        try:
            latest = self.mapper.latest()
            head = self.mapper.product.exact("HEAD")
            scope_changed = latest is not None and self.mapper.selection() != (
                latest.typed.include, latest.typed.exclude)
            due = latest is None or scope_changed or (
                latest.typed.commit != head and self.now - datetime.fromisoformat(
                    latest.typed.confirmed_at) >= timedelta(days=self.max_age_days))
        except (OSError, ValueError, RuntimeError) as exc:
            return CheckResult(self, status="incomplete", reason=f"Mapping scan unavailable: {exc}")
        pois = [self.poi(MappingUpdateRequired, message="Product map update required",
                         details={"repository": str(self.mapper.product.root), "head": head,
                                  "mapped_commit": latest.typed.commit if latest else None,
                                  "scope_changed": scope_changed,
                                  "max_age_days": self.max_age_days})] if due else []
        return CheckResult(self, status="completed", pois=pois)


class MappingUpdateChain(SituationChain):
    Check = MappingFreshnessCheck
    POIs = (MappingUpdateRequired,)

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("10cd0fa8-f0cd-4f22-8e7f-d33a8fa74847"),
                          name="Tarav.ProductMapping.Chain", workflow=PRODUCT_MAPPING_SHIP)


class ProductMappingSuite(CheckSuite):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("925f0ea2-10fa-4233-b8e9-e52e0ca37c9e"),
                          name="Tarav.ProductMapping.Suite", workflow=PRODUCT_MAPPING_SHIP)

    def __init__(self, mapper, *, max_age_days=5, now=None):
        super().__init__(key=mapper.repository_id, name="Product Mapping",
                         repositories=[mapper.product.root])
        self.mapper, self.max_age_days, self.now = mapper, max_age_days, now

    def produce(self):
        yield MappingFreshnessCheck(mapper=self.mapper, max_age_days=self.max_age_days, now=self.now)


PRODUCT_MAPPING_CHECK_TYPES = (MappingUpdateRequired, MappingFreshnessCheck,
                               MappingUpdateChain, ProductMappingSuite)
