"""Append-only attributed blessings and assessments."""

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from tarav.l0.kernel import (
    FileRecord,
    LiteRecord,
    Ship,
    TaravClass,
    TaravEntity,
    TypeShip,
    entity,
)
from tarav.l1.poi import fingerprint
from tarav.l1.decisions import Decision

from .capability import BlessablePOI
from .workflow import BLESSINGS_WORKFLOW_SHIP


_assertion_provider = None
_score_provider = None


def bind_blessing_assertion_services(*, assertions, scores) -> None:
    """Compose higher-layer scoring behavior without reversing l1 imports."""

    global _assertion_provider, _score_provider
    if not callable(assertions) or not callable(scores):
        raise TypeError('Blessing assertion services must be callable')
    _assertion_provider = assertions
    _score_provider = scores


# tarav.breadcrumb 77e3776202a020cf5caa253438fbd0dafbf2796bd6fd03abfc2141d1d6732d9c
class BlessingRecord(Decision):
    # tarav.breadcrumb 1f79ed706a8e477702024e29b419cb676616dfd0c877392cb3dd9d31f8beebb9
    class RecordInterface(Decision.RecordInterface):
        schema_version: int
        created_at: str
        actor: dict
        rationale: str
        support: list[dict]
        poi: dict

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("1c218c7c-4a6b-43dc-9e22-817330824b85"),
            name="Tarav.Blessings.Record",
            workflow=BLESSINGS_WORKFLOW_SHIP,
        )

    @classmethod
    def validate_record(cls, value):
        data = super().validate_record(value)
        _validate(value, blessing=True)
        return data

    @classmethod
    def _from_record(cls, data):
        result = cls.__new__(cls)
        TaravEntity.__init__(result, data.id)
        return result

    def assessment_findings(self, assessments):
        selected = [a for a in assessments if a["assertion"] == "acceptance-justified"]
        if not selected:
            return [{"kind": "blessing-unassessed", "blessing": str(self.id)}]
        return [
            {
                "kind": "blessing-low-score",
                "assessment": assessment["id"],
                "blessing": str(self.id),
            }
            for assessment in selected
            if assessment["score"] < 0.5
        ]

    @property
    def assertions(self):
        """The current typed Assertions for this exact attributed blessing."""

        if _assertion_provider is None:
            raise RuntimeError('Blessing Assertion service has not been composed')
        return _assertion_provider(self)

    def score_vector(self, repository):
        """Read scorer-owned results by Assertion identity without copying scores here."""
        # tarav.breadcrumb b01648a982efd726c6623a6225cbdbb9fc69b7bd9b6f5c60c1b9f98cf68c7d4e

        if _score_provider is None:
            raise RuntimeError('Blessing scoring service has not been composed')
        return _score_provider(self, repository)

    def ships(self):
        poi = self.to_record()["poi"]
        return (*super().ships(), TypeShip(poi["class_id"]))

    @property
    def poi_ids(self) -> tuple[str, ...]:
        return (self.to_record()["poi"]["id"],)

    def obj_context(self, builder):
        from tarav.l1.poi import POIDetails

        builder.add(
            "acceptance",
            opener=lambda: POIDetails.from_record(
                {"type": entity(POIDetails).name, "value": self.to_record()}
            ),
        )

    @classmethod
    def record_example(cls):
        poi = {
            "type": "Example.BlessablePOI",
            "class_id": "7d28d632-2ec5-4c5a-997f-224ad508ce9d",
            "code": "example",
            "message": "Synthetic POI",
            "situation": {"example": "situation"},
            "subject": {},
            "evidence": {},
        }
        poi["id"] = fingerprint([poi["class_id"], poi["situation"]])
        return {
            "type": entity(cls).name,
            "schema_version": 3,
            "id": "b3c3a696-e88c-497f-b87d-cdc9a557d882",
            "created_at": "2026-09-26T00:00:00+00:00",
            "actor": {"type": "Example.Actor", "locator": {"name": "example"}},
            "rationale": "Synthetic Record example",
            "support": [],
            "poi": poi,
        }


class BlessingAssessmentRecord(TaravEntity, FileRecord):
    class RecordInterface(TaravEntity.RecordInterface):
        schema_version: int
        created_at: str
        actor: dict
        rationale: str
        support: list[dict]
        blessing: str
        assertion: str
        score: float | int

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("341a797a-82c7-4fb3-b97b-c60c6f19139b"),
            name="Tarav.Blessings.Assessment",
            workflow=BLESSINGS_WORKFLOW_SHIP,
        )

    @classmethod
    def validate_record(cls, value):
        data = super().validate_record(value)
        _validate(value, blessing=False)
        return data

    @classmethod
    def _from_record(cls, data):
        result = cls.__new__(cls)
        TaravEntity.__init__(result, data.id)
        return result

    def obj_context(self, builder):
        from tarav.l1.poi import POIDetails

        builder.add(
            "assessment",
            opener=lambda: POIDetails.from_record(
                {"type": entity(POIDetails).name, "value": self.to_record()}
            ),
        )

    def ships(self):
        return (*super().ships(), Ship(self.to_record()["blessing"]))

    @classmethod
    def record_example(cls):
        record = BlessingRecord.record_example()
        record.pop("poi")
        record.update(
            type=entity(cls).name,
            blessing="b3c3a696-e88c-497f-b87d-cdc9a557d882",
            assertion="acceptance-justified",
            score=1.0,
        )
        return record


def reference(value):
    if (
        not isinstance(value, dict)
        or not value.get("type")
        or not isinstance(value.get("locator"), dict)
        or not value["locator"]
    ):
        raise ValueError("Expected an explicit typed actor/evidence reference")
    json.dumps(value, sort_keys=True, allow_nan=False)


def _validate(record, *, blessing):
    if not isinstance(record, dict):
        raise ValueError("Expected a blessing Record object")
    if record.get("schema_version") != 3:
        raise ValueError("Unsupported blessing record schema")
    UUID(record["id"])
    datetime.fromisoformat(record["created_at"])
    reference(record["actor"])
    if not isinstance(record["rationale"], str) or not record["rationale"].strip():
        raise ValueError("An attributed rationale is required")
    if not isinstance(record["support"], list):
        raise ValueError("support must be a list of typed references")
    for item in record["support"]:
        reference(item)
    if blessing:
        poi = record["poi"]
        required = {"type", "class_id", "id", "situation", "subject", "evidence"}
        if not isinstance(poi, dict) or not required <= poi.keys():
            raise ValueError("Blessing must retain a BlessablePOI snapshot")
        situation = LiteRecord.from_json_value(poi["situation"])
        if poi["id"] != fingerprint([poi["class_id"], situation.to_json_value()]):
            raise ValueError("POI identity disagrees with retained situation")
        TypeShip(poi["class_id"])
    else:
        UUID(record["blessing"])
        if (
            type(record["score"]) not in (int, float)
            or not math.isfinite(record["score"])
            or not 0 <= record["score"] <= 1
        ):
            raise ValueError("score must be a finite value between zero and one")
        if not isinstance(record["assertion"], str) or not record["assertion"].strip():
            raise ValueError("Assessment must name its assertion")


class BlessingStore:
    def __init__(self, root, *, record_types=()):
        self.root = Path(root).resolve()
        self.record_types = {}
        for cls in (BlessingRecord, BlessingAssessmentRecord, *record_types):
            if not issubclass(cls, (BlessingRecord, BlessingAssessmentRecord)):
                raise TypeError("Expected a blessing or assessment type")
            name = entity(cls).name
            if name in self.record_types and self.record_types[name] is not cls:
                raise ValueError(f"Duplicate blessing type: {name}")
            self.record_types[name] = cls

    @classmethod
    def from_archive(cls, archive, **kwargs):
        """Keep the established physical partition independent of semantic ownership."""

        from tarav.l1.poi.workflow import POIWorkflow

        return cls(archive.for_workflow(POIWorkflow).directory / "blessings", **kwargs)

    def accepts(self, poi) -> bool:
        return isinstance(poi, BlessablePOI)

    def _type(self, record):
        if not isinstance(record, dict) or record.get("type") not in self.record_types:
            raise ValueError("Unknown blessing record type")
        return self.record_types[record["type"]]

    def _is(self, record, base):
        return issubclass(self._type(record), base)

    def load(self, identity):
        for record in self.snapshot()["records"]:
            if record["id"] == str(identity):
                return self._type(record).from_record(record)
        raise KeyError(identity)

    def add(self, blessing):
        if not isinstance(blessing, (BlessingRecord, BlessingAssessmentRecord)):
            raise TypeError("Expected a blessing or assessment object")
        record = blessing.to_record()
        if self._type(record) is not type(blessing):
            raise TypeError("Object does not match registered blessing type")
        self._append(record)
        return blessing

    def snapshot(self):
        records = []
        findings = []
        if not self.root.exists():
            return {"records": records, "findings": findings}
        for path in sorted(self.root.glob("*.json")):
            try:
                record = json.loads(path.read_text())
                self._type(record).validate_record(record)
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                findings.append(
                    {"kind": "invalid-blessing-record", "path": str(path), "detail": str(exc)}
                )
                continue
            records.append(record)
        ids = {record["id"] for record in records if self._is(record, BlessingRecord)}
        for record in records:
            if (
                self._is(record, BlessingAssessmentRecord)
                and record["blessing"] not in ids
            ):
                findings.append(
                    {"kind": "orphan-blessing-assessment", "id": record["id"]}
                )
        return {"records": records, "findings": findings}

    def _append(self, record):
        self._type(record).validate_record(record)
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / (record["id"] + ".json")
        with path.open("x", encoding="utf-8") as handle:
            handle.write(
                json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
            )
        return record

    def bless(
        self,
        poi,
        *,
        actor,
        rationale,
        support=(),
        record_type=BlessingRecord,
    ):
        if not issubclass(record_type, BlessingRecord):
            raise TypeError("Expected BlessingRecord subtype")
        if not self.accepts(poi):
            raise ValueError("This POI type does not permit blessing")
        record = {
            "type": entity(record_type).name,
            "schema_version": 3,
            "id": str(uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "actor": actor,
            "rationale": rationale,
            "support": list(support),
            "poi": poi.blessing_snapshot(),
        }
        return self._append(record)

    def assess(
        self,
        blessing,
        *,
        actor,
        assertion,
        score,
        rationale,
        support=(),
        record_type=BlessingAssessmentRecord,
    ):
        if not issubclass(record_type, BlessingAssessmentRecord):
            raise TypeError("Expected BlessingAssessmentRecord subtype")
        records = self.snapshot()["records"]
        if not any(
            self._is(record, BlessingRecord) and record["id"] == blessing
            for record in records
        ):
            raise ValueError("Unknown blessing")
        return self._append(
            {
                "type": entity(record_type).name,
                "schema_version": 3,
                "id": str(uuid4()),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "blessing": blessing,
                "actor": actor,
                "assertion": assertion,
                "score": score,
                "rationale": rationale,
                "support": list(support),
            }
        )

    # tarav.breadcrumb 1be8737940ef28408a7723ab4a82c57058f2dd976c2b7ff644ec7cf108c6a741
    def standing(self, poi, *, snapshot=None):
        if not self.accepts(poi):
            raise TypeError("Expected BlessablePOI")
        records = (snapshot if snapshot is not None else self.snapshot())["records"]
        accepted = [
            record
            for record in records
            if self._is(record, BlessingRecord)
            and record["poi"]["id"] == poi.identity
        ]
        status = "blessed" if accepted else "unblessed"
        scores = [
            record
            for record in records
            if self._is(record, BlessingAssessmentRecord)
            and record["blessing"] in {blessing["id"] for blessing in accepted}
        ]
        assessment_findings = []
        for record in accepted:
            assessments = [
                score for score in scores if score["blessing"] == record["id"]
            ]
            obj = self._type(record).from_record(record)
            assessment_findings.extend(obj.assessment_findings(assessments))
        return {
            "status": status,
            "records": [record["id"] for record in accepted],
            "assessment_findings": assessment_findings,
            "assessment": (
                "unassessed"
                if any(
                    finding["kind"] == "blessing-unassessed"
                    for finding in assessment_findings
                )
                else "scored"
                if scores
                else "not-applicable"
            ),
            "scores": [
                {
                    "id": record["id"],
                    "blessing": record["blessing"],
                    "assertion": record["assertion"],
                    "score": record["score"],
                }
                for record in scores
            ],
        }
