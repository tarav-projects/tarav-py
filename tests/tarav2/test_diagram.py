from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from tarav.cli.cli import main
from tarav.tarav2.diagram import (
    LINE_ANNOTATION_TYPE,
    MODEL_ANNOTATION_TYPE,
    USER_TOUCHED_CHATLAS_INDEX,
    AnnotationDraft,
    CaptureManifest,
    Diagram,
    DiagramAnnotationSpecializationError,
    DiagramConfiguration,
    DiagramError,
    DiagramLocation,
    DiagramNamespace,
    LineAnnotation,
)


def _line(
    model_ship: str, *, annotation_id: str | None = None, support: bool = True
) -> AnnotationDraft:
    ref = {
        "session_identity": "a" * 64,
        "turn_address": "b" * 64,
        "turn_hash": "c" * 64,
    }
    return AnnotationDraft(
        annotation_id or str(uuid4()),
        {
            "type": LINE_ANNOTATION_TYPE,
            "producer": ref,
            "support": [{"root": ref, "neighborhood": []}] if support else [],
            "location": DiagramLocation(
                model_ship, str(uuid4()), str(uuid4())
            ).to_dict(),
            "data": {"text": "Capture concerns only the present Model."},
        },
    )


def test_namespace_is_an_independent_flat_git_annotation_tape(tmp_path: Path) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")

    assert (namespace.root / ".git").is_dir()
    assert (namespace.root / "namespace.json").is_file()
    assert (namespace.root / "annotations").is_dir()
    assert not (namespace.root / "models").exists()
    assert namespace.name == USER_TOUCHED_CHATLAS_INDEX


def test_only_type_is_universal_and_specialization_is_explicit(tmp_path: Path) -> None:
    namespace = DiagramNamespace.create(tmp_path / "generic", name="Experiments")
    draft = AnnotationDraft(str(uuid4()), {"type": "Example.Free.Annotation"})
    namespace.append((draft,))

    annotation = namespace.annotation(draft.id)
    assert annotation.type == "Example.Free.Annotation"
    assert annotation.to_record()["type"] == "Example.Free.Annotation"
    with pytest.raises(DiagramAnnotationSpecializationError):
        annotation.specialize()


def test_models_are_root_annotations_and_project_to_the_flat_tape(
    tmp_path: Path,
) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model(label="Tarav")
    line = _line(model.ship)
    namespace.apply(CaptureManifest(model.ship, (line,)))

    assert namespace.annotation(model.root_annotation_id).type == MODEL_ANNOTATION_TYPE
    assert [item.id for item in model.annotations()] == [line.id]
    assert isinstance(namespace.annotation(line.id).specialize(), LineAnnotation)


def test_capture_reports_pois_but_remains_writable(tmp_path: Path) -> None:
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    model = namespace.create_model()
    line = _line(model.ship, support=False)

    receipt = namespace.apply(CaptureManifest(model.ship, (line,)))

    assert receipt.created == (line.id,)
    assert {item.code for item in receipt.findings} == {"empty-support-set"}
    assert namespace.annotation(line.id).standing == "UnAsserted"


def test_capture_model_resolves_the_only_writable_namespace(tmp_path: Path) -> None:
    first = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "first")
    second = DiagramNamespace.create(tmp_path / "second", name="Experiments")
    model = first.create_model()
    line = _line(model.ship)
    diagram = Diagram((second, first), default_namespace_id=second.id)

    receipt = diagram.apply(CaptureManifest(model.ship, (line,)))

    assert receipt.namespace_id == first.id
    assert (first.annotations_root / f"{line.id}.json").is_file()
    assert not (second.annotations_root / f"{line.id}.json").exists()


def test_annotation_identity_is_non_rebinding(tmp_path: Path) -> None:
    namespace = DiagramNamespace.create(tmp_path / "generic", name="Experiments")
    annotation_id = str(uuid4())
    namespace.append((AnnotationDraft(annotation_id, {"type": "Example.One"}),))
    with pytest.raises(DiagramError, match="cannot be rebound"):
        namespace.append((AnnotationDraft(annotation_id, {"type": "Example.Two"}),))


def test_project_main_model_bootstraps_in_default_user_namespace(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    (project / ".tarav").mkdir(parents=True)
    marker = {"class": "agentos.project", "project_id": str(uuid4())}
    (project / ".tarav" / "project.json").write_text(
        json.dumps(marker), encoding="utf-8"
    )
    namespace = DiagramNamespace.create_user_touched_chatlas_index(tmp_path / "index")
    diagram = Diagram((namespace,), namespace.id)

    model = diagram.ensure_project_model(project)
    again = diagram.ensure_project_model(project)

    stored = json.loads((project / ".tarav" / "project.json").read_text())
    assert stored["diagram"] == {"main_model": model.ship}
    assert again.ship == model.ship


def test_namespace_cli_and_project_capture_template(tmp_path: Path, capsys) -> None:
    config = tmp_path / "diagram.json"
    namespace = tmp_path / "index"
    project = tmp_path / "project"
    manifest = tmp_path / "capture.json"
    (project / ".tarav").mkdir(parents=True)
    (project / ".tarav" / "project.json").write_text(
        json.dumps({"class": "agentos.project", "project_id": str(uuid4())}),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "tarav2",
                "diagram",
                "namespace",
                "create",
                "--location",
                str(namespace),
                "--name",
                USER_TOUCHED_CHATLAS_INDEX,
                "--default",
                "--diagram-config",
                str(config),
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (
        main(
            [
                "tarav2",
                "diagram",
                "capture",
                "template",
                "--manifest",
                str(manifest),
                "--project",
                str(project),
                "--diagram-config",
                str(config),
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    capture = json.loads(manifest.read_text())
    project_marker = json.loads((project / ".tarav" / "project.json").read_text())
    assert payload["status"] == "ok"
    assert capture["model_ship"] == project_marker["diagram"]["main_model"]
    assert DiagramConfiguration.load(config).default_namespace_id is not None
