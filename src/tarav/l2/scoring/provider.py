"""Record navigation for the Scoring repository's own storage layout."""

from pathlib import Path

from tarav.l0.kernel.space import Entry, FilesystemProvider

from .repository import ScoringRepository


class ScoringProvider(FilesystemProvider):
    """Expose typed Scoring Records without moving or rewriting them."""
    # tarav.breadcrumb 470475f6f6f8efb3d7acdc9f8d8bc22ea9b5d68ea2bf6da46fd77d3f972e9c61

    def __init__(self, root: Path, records: object) -> None:
        repository = ScoringRepository(root).open()
        super().__init__(repository.root, records)

    def list(self, address: str = "") -> tuple[Entry, ...]:
        entries = super().list(address)
        if not address:
            return tuple(entry for entry in entries if entry.name != "repository.json")
        return entries


__all__ = ["ScoringProvider"]
