from __future__ import annotations

from pathlib import Path


TARAV_DATA_DIRNAME = "tarav"


def default_tarav_data_root() -> Path:
    """Return the default physical depot for durable Tarav data."""
    return Path.home().expanduser().resolve() / "Documents" / TARAV_DATA_DIRNAME


__all__ = ["TARAV_DATA_DIRNAME", "default_tarav_data_root"]
