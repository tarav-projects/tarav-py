# $kw: ^index-poi-catalog-discovery --from Dependency.Profile.Split --note [DF] Index parser-backed POI catalog discovery lives with Index and returns the lower-level POI catalog model --supp ^c20260811-62u
from __future__ import annotations

from collections.abc import Iterable

from tarav.index.model import BlockHeading, parse_depot
from tarav.poi import POICatalog, POICatalogError, POIClassRegistration
from tarav.wayfinder import (
    PACKAGE_SKILL_ROOT_TYPE,
    WayfinderRegistry,
    poi_class_reference,
)


def discover_poi_catalog(
    *,
    registry: WayfinderRegistry | None = None,
    package_ids: Iterable[str] | None = None,
) -> POICatalog:
    """Discover POI classes from registered Package.Skill `poi` chapters."""
    selected = set(package_ids) if package_ids is not None else None
    registrations: list[POIClassRegistration] = []
    for entry in (registry or WayfinderRegistry()).entries():
        if entry.root.type != PACKAGE_SKILL_ROOT_TYPE:
            continue
        if selected is not None and entry.root.id not in selected:
            continue
        poi_root = entry.path / "poi"
        if not poi_root.is_dir():
            continue
        depot = parse_depot(entry.path)
        for document in depot.documents:
            if (
                document.surface_kind != "chapter"
                or document.path is None
                or document.path.parent != poi_root
            ):
                continue
            diagnostics = document.diagnostics()
            if diagnostics:
                reasons = ", ".join(
                    f"{diagnostic.reason} at line {diagnostic.start_line}"
                    for diagnostic in diagnostics
                )
                raise POICatalogError(
                    f"invalid POI chapter {document.path}: {reasons}"
                )
            for node in document.nodes:
                if not isinstance(node, BlockHeading):
                    continue
                block_path = str(node.parsed.get("path", ""))
                if not node.parsed.get("valid") or not block_path:
                    raise POICatalogError(
                        f"invalid POI class heading in "
                        f"{document.path}:{node.start_line}"
                    )
                registrations.append(
                    POIClassRegistration(
                        finding_code=block_path,
                        reference=poi_class_reference(entry.root.id, block_path),
                    )
                )
    return POICatalog(registrations)


__all__ = ["discover_poi_catalog"]
