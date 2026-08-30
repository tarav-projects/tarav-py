# $kw: ^skw-build --from POI.System --from POI.Linter --supp dependency roles and whole-file context-assembly bypass supervision authorized ^c20260725-27u --supp common POI migration execution ^c20260729-49u
"""Stable public facade for Skillware expansion, build, check, and blessing."""

from __future__ import annotations

from tarav.skw.network import extract_mentions

from ._build_core import (
    BUILD_DIR,
    PROJECT_MARKER,
    SETTINGS_NAME,
    SRC_SUFFIX,
    CodeSurfaceConfig,
    EditionHistoryConfig,
    Expansion,
    Skillware,
    SkillwareError,
    SkwConfig,
    UnlockRequirement,
    _resolve_locator,
    content_hash,
    expand_edition_history_targets,
    expand_file,
    find_project_root,
    load_project_skw_config,
    load_skillware,
    parse_skw_config,
    resolve_build_root,
    unlock_requirements,
)
from ._code_model import (
    CodeBackendRegistry,
    CodeBlessRecord,
    CodeCheckReport,
    CodeLanguageBackend,
    CodeSurfaceModel,
    CodeSurfaceTarget,
)
from ._code_surfaces import bless_code_poi, check_code_surfaces, expand_code_surfaces
from ._build_operations import (
    AGENTS_MD_TEXT,
    AGENTS_NAME,
    BLESSABLE_KINDS,
    LOCK_NAME,
    SUPPRESSIBLE_KINDS,
    BlessRecord,
    BuildEntry,
    BuildRefusal,
    BuildReport,
    CheckEntry,
    CheckReport,
    ProjectCheckReport,
    bless_pois_by_kind,
    bless_skill,
    build_skill,
    check_project,
    check_skill,
    discover_packages,
)
from .poi import SkillwarePOIInstance


__all__ = [
    "SETTINGS_NAME",
    "SRC_SUFFIX",
    "Expansion",
    "Skillware",
    "SkillwareError",
    "content_hash",
    "expand_file",
    "load_skillware",
    "BLESSABLE_KINDS",
    "BlessRecord",
    "BuildEntry",
    "BuildRefusal",
    "BuildReport",
    "CheckEntry",
    "CheckReport",
    "CodeCheckReport",
    "CodeBlessRecord",
    "CodeBackendRegistry",
    "CodeLanguageBackend",
    "CodeSurfaceConfig",
    "CodeSurfaceModel",
    "CodeSurfaceTarget",
    "SkillwarePOIInstance",
    "SUPPRESSIBLE_KINDS",
    "UnlockRequirement",
    "bless_pois_by_kind",
    "bless_code_poi",
    "bless_skill",
    "build_skill",
    "check_skill",
    "check_code_surfaces",
    "extract_mentions",
    "expand_code_surfaces",
    "unlock_requirements",
]


_DIRECT_EXPORTS = (
    AGENTS_MD_TEXT,
    AGENTS_NAME,
    BUILD_DIR,
    LOCK_NAME,
    PROJECT_MARKER,
    EditionHistoryConfig,
    ProjectCheckReport,
    SkwConfig,
    _resolve_locator,
    check_project,
    discover_packages,
    expand_edition_history_targets,
    find_project_root,
    load_project_skw_config,
    parse_skw_config,
    resolve_build_root,
)
