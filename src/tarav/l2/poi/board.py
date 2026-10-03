"""A pageable view over explicitly tracked POIs and optional Decisions."""

from tarav.l1.blessings import BlessingStore
from tarav.l1.decisions import DecisionStore
from tarav.l1.poi import TrackedPOIStore


# tarav.breadcrumb 11e779ea8d3adbe7f335b96fa331d324f983ea00254c8add9c09104ec6c2f29a
class TrackedPOIBoard:
    def __init__(self, store: TrackedPOIStore, *, blessings: BlessingStore | None = None,
                 decisions: DecisionStore | None = None):
        if not isinstance(store, TrackedPOIStore):
            raise TypeError("Expected a TrackedPOIStore")
        self.store = store
        self.blessings = blessings
        self.decisions = decisions

    def report(self, *, workflow=None, poi_type=None, detected=None,
               disposition=None, subject=None, offset=0, limit=20):
        if type(offset) is not int or type(limit) is not int or offset < 0 or limit < 1:
            raise ValueError("Expected nonnegative offset and positive limit")
        if detected is not None and type(detected) is not bool:
            raise TypeError("Detected filter must be boolean")
        if disposition not in (None, "blessed", "unreviewed"):
            raise ValueError("Unknown disposition filter")
        tracked = self.store.snapshot()
        blessings = self.blessings.snapshot() if self.blessings else {"records": [], "findings": []}
        decisions = self.decisions.snapshot() if self.decisions else {"records": [], "findings": []}
        by_poi = {}
        for record in blessings["records"]:
            if record.get("poi", {}).get("id"):
                by_poi.setdefault(record["poi"]["id"], []).append(record["id"])
        other = {}
        for record in decisions["records"]:
            for poi_id in record.get("poi_ids", ()):
                other.setdefault(poi_id, []).append(record["id"])
        rows = []
        for record in tracked["records"]:
            poi_id = record["poi_id"]
            row = {**record,
                   "disposition": "blessed" if by_poi.get(poi_id) else "unreviewed",
                   "decisions": [*by_poi.get(poi_id, ()), *other.get(poi_id, ())]}
            rows.append(row)
        rows.sort(key=lambda row: (row["poi_id"], row["id"]))
        selected = [row for row in rows
                    if (workflow is None or row["owner_workflow"] == str(workflow))
                    and (poi_type is None or row["poi"]["type"] == poi_type)
                    and (detected is None or row["detected"] is detected)
                    and (disposition is None or row["disposition"] == disposition)
                    and (subject is None or row["poi"].get("subject") == subject)]
        page = selected[offset:offset + limit]
        return {
            "total": len(rows), "matching": len(selected), "offset": offset,
            "shown": len(page),
            "next_offset": offset + limit if offset + limit < len(selected) else None,
            "store_findings": [*tracked["findings"], *blessings["findings"],
                               *decisions["findings"]],
            "items": page,
        }
