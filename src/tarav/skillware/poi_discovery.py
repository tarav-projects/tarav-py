# $kw: ^index-poi-catalog-discovery --from Dependency.Profile.Split --from Index.Primary.Surface --note [DF] record-backed POI catalog discovery returns the lower-level POI catalog model --supp ^c20260811-62u --note [DC] a POI class is discovered by its Index address rather than by the file it happens to be written on, so a class exists exactly when the records say it does
from __future__ import annotations

from collections.abc import Iterable

from tarav.indexlab import IndexResolutionError, IndexResolver
from tarav.poi import POICatalog, POICatalogError, POIClassRegistration
from tarav.wayfinder import (
    PACKAGE_SKILL_ROOT_TYPE,
    WayfinderRegistry,
    poi_class_reference,
)

#: The Index chapter that hosts `POI.Class` blocks.
POI_CHAPTER = "poi"


def discover_poi_catalog(
    *,
    registry: WayfinderRegistry | None = None,
    package_ids: Iterable[str] | None = None,
) -> POICatalog:
    """Discover POI classes from the `poi` chapter blocks in the Index records."""
    selected = set(package_ids) if package_ids is not None else None
    registrations: list[POIClassRegistration] = []
    for entry in (registry or WayfinderRegistry()).entries():
        if entry.root.type != PACKAGE_SKILL_ROOT_TYPE:
            continue
        if selected is not None and entry.root.id not in selected:
            continue
        try:
            resolver = IndexResolver.for_path(entry.path)
        except IndexResolutionError:
            continue
        prefix = f"{entry.path.name}/{POI_CHAPTER}#"
        for name in resolver.block_names():
            if not name.startswith(prefix):
                continue
            block_path = name[len(prefix) :]
            if not block_path:
                raise POICatalogError(f"POI class block has an empty address: {name}")
            registrations.append(
                POIClassRegistration(
                    finding_code=block_path,
                    reference=poi_class_reference(entry.root.id, block_path),
                )
            )
    return POICatalog(registrations)


__all__ = ["discover_poi_catalog"]
