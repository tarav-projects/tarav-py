"""A Project's POI tracking: its store under `.tarav/` and the axes it composes."""

import logging
from pathlib import Path
from types import SimpleNamespace

from tarav.l1.poi_tracking import POITracker, TrackRecordStore
from tarav.l1.poi_tracking.views import PROJECT_STORE_PATH

_LOG = logging.getLogger(__name__)


def open_tracker(project) -> POITracker:
    """The tracker of a Project, given the Project or its root folder.

    Opening creates nothing. The blessing axis is composed when the Project's
    Decisions can be read in this process; tracking works without it.
    """
    root = Path(project if isinstance(project, (str, Path)) else project.root).resolve()
    axes = []
    try:
        from tarav.l2.blessings.tracking import BlessingAxis
        from .decisions import ProjectDecisions

        axes.append(BlessingAxis(ProjectDecisions(SimpleNamespace(root=root)).blessings()))
    except Exception:
        _LOG.warning("POI tracking opened without the blessing axis", exc_info=True)
    return POITracker(TrackRecordStore(root / PROJECT_STORE_PATH), axes=axes)


__all__ = ["open_tracker"]
