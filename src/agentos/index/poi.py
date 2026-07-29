from __future__ import annotations

from agentos.poi import (
    POICatalog,
    POIClassRegistration,
    POIInstance,
    POILocation,
)
from agentos.wayfinder import poi_class_reference

from ._linter_models import LinterFinding
from ._linter_parser_checks import (
    ANCHOR_LEGACY_SIGIL,
    ANCHOR_UNPREFIXED,
    BLOCK_UNGROUNDED,
    LINE_TYPE_GR_MISSING_ANCHOR,
    LINE_TYPE_SYNTAX,
    LINE_TYPE_UNKNOWN,
    LINE_UNLINKED,
    REVIEWED_CITE_CLOSURE,
    SOURCE_AXIS_PLACEMENT,
    TYPE_STATEMENT_LEGACY_SIGIL,
)
from ._linter_structure import (
    APPENDIX_INVALID_FILENAME,
    APPENDIX_ORPHAN,
    APPENDIX_PAGE_GAP,
    APPENDIX_ROUTE_ANNOTATION_MISSING,
    APPENDIX_ROUTE_ANNOTATION_STALE,
    BLOCK_UNANCHORED_SECTION,
    CONFIG_NO_SURFACES,
    CONCEPT_DUPLICATE,
    CONCEPT_INVALID_HEADING,
    CONCEPT_INVENTORY_EMPTY,
    DEPOT_COLLISION,
    DEPOT_DANGLING_MENTION,
    DEPOT_DEP_UNRESOLVED,
    FILES_NONE,
    INDEX_INVALID_FILENAME,
    MDBLOCKS_CODE_MAP,
    MDBLOCKS_SYNTAX,
    ROUTER_EMPTY,
    ROUTER_ENTRIES_EMPTY,
    ROUTER_INVALID_CONCEPT,
    ROUTER_LEGACY_NAME,
    ROUTER_MISSING,
    ROUTER_MISSING_ENTRY,
    ROUTER_MISSING_FILE,
    ROUTER_UNKNOWN_CONCEPT,
    ROUTER_WRONG_FILE,
    SURFACE_INVALID,
    SURFACE_INVALID_BY_KIND,
    SURFACE_MISSING_BY_KIND,
    SURFACE_NOT_MARKDOWN_BY_KIND,
)


INDEX_POI_CODES = tuple(
    dict.fromkeys(
        (
            CONFIG_NO_SURFACES,
            *SURFACE_MISSING_BY_KIND.values(),
            *SURFACE_NOT_MARKDOWN_BY_KIND.values(),
            *SURFACE_INVALID_BY_KIND.values(),
            SURFACE_INVALID,
            FILES_NONE,
            MDBLOCKS_SYNTAX,
            *MDBLOCKS_CODE_MAP.values(),
            BLOCK_UNANCHORED_SECTION,
            ROUTER_MISSING,
            ROUTER_LEGACY_NAME,
            ROUTER_EMPTY,
            INDEX_INVALID_FILENAME,
            CONCEPT_INVALID_HEADING,
            CONCEPT_INVENTORY_EMPTY,
            CONCEPT_DUPLICATE,
            APPENDIX_INVALID_FILENAME,
            APPENDIX_ORPHAN,
            APPENDIX_ROUTE_ANNOTATION_MISSING,
            APPENDIX_ROUTE_ANNOTATION_STALE,
            APPENDIX_PAGE_GAP,
            ROUTER_INVALID_CONCEPT,
            ROUTER_ENTRIES_EMPTY,
            ROUTER_MISSING_ENTRY,
            ROUTER_MISSING_FILE,
            ROUTER_UNKNOWN_CONCEPT,
            ROUTER_WRONG_FILE,
            DEPOT_DEP_UNRESOLVED,
            DEPOT_COLLISION,
            DEPOT_DANGLING_MENTION,
            LINE_TYPE_SYNTAX,
            LINE_TYPE_UNKNOWN,
            LINE_TYPE_GR_MISSING_ANCHOR,
            SOURCE_AXIS_PLACEMENT,
            ANCHOR_LEGACY_SIGIL,
            ANCHOR_UNPREFIXED,
            TYPE_STATEMENT_LEGACY_SIGIL,
            LINE_UNLINKED,
            BLOCK_UNGROUNDED,
            REVIEWED_CITE_CLOSURE,
        )
    )
)

INDEX_POI_CATALOG = POICatalog(
    POIClassRegistration(
        finding_code=code,
        reference=poi_class_reference("agentos-pkg", code),
    )
    for code in INDEX_POI_CODES
)


def finding_to_poi(
    finding: LinterFinding,
    catalog: POICatalog = INDEX_POI_CATALOG,
) -> POIInstance:
    return POIInstance.create(
        class_reference=catalog.require(finding.code),
        target=POILocation(path=finding.path, line=finding.line),
        severity=finding.severity,
        situation=finding.message,
        evidence=finding.details,
    )


__all__ = [
    "INDEX_POI_CATALOG",
    "INDEX_POI_CODES",
    "finding_to_poi",
]
