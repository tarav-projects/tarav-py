# $kw: ^chatlas-commit-poi --from POI.System --from POI.Linter --note [DF] Chatlas commit refusals carry package-owned POI instances while retaining the CliError boundary ^c20260729-49u
from __future__ import annotations

from pathlib import Path

from tarav._core.errors import CliError
from tarav.poi import POIInstance, POILocation, reference_sugar
from tarav.wayfinder import poi_class_reference


CHATLAS_COMMIT_POI_CODES = (
    "Session.Mismatch",
    "Turn.CountMismatch",
    "Turn.InvalidObject",
    "Turn.RoleMismatch",
    "Turn.TextNotString",
    "Turn.UserTextNotVerbatim",
    "Turn.AssistantTextBlank",
    "Compression.Insufficient",
    "Compression.RegionUntouched",
    "Compression.TurnCollapsed",
    "Compression.RegionCrushed",
)


class ChatlasCommitLintError(CliError):
    def __init__(self, poi: POIInstance) -> None:
        self.poi = poi
        super().__init__(
            "Chatlas zip-transcript-summary Product.Commit.Linter failed: "
            f"{poi.situation} "
            f"[POI {poi.instance_id} {reference_sugar(poi.class_reference)}]"
        )


def raise_chatlas_commit_poi(
    code: str,
    *,
    artifact_path: Path,
    situation: str,
    evidence: dict[str, object],
) -> None:
    if code not in CHATLAS_COMMIT_POI_CODES:
        raise ValueError(f"unknown Chatlas commit POI code: {code}")
    raise ChatlasCommitLintError(
        POIInstance.create(
            class_reference=poi_class_reference(
                "tarav-chatlas-pkg", f"Chatlas.Commit.Linter/{code}"
            ),
            target=POILocation(path=str(artifact_path)),
            severity="error",
            situation=situation,
            evidence=evidence,
        )
    )


__all__ = [
    "CHATLAS_COMMIT_POI_CODES",
    "ChatlasCommitLintError",
    "raise_chatlas_commit_poi",
]
