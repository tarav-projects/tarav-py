from tarav.l0.kernel import entity

import json

import pytest
from tarav.unsorted.primitives import DiagramError

from tarav.l1.skw.publication import ModelPublication, ModelPublicationRecord
from tarav.runtime import create_runtime
from tarav.l1.skw.skills import SkwSkill
from test_rendering import _diagram_with_line


def publication(tmp_path):
    _, model, block, _, _ = _diagram_with_line(tmp_path)
    root = tmp_path / "skill"
    source = root / ".skw/src/model.json"
    source.parent.mkdir(parents=True)
    source.write_text(
        json.dumps(
            {
                "type": entity(ModelPublicationRecord).name,
                "schema_version": 1,
                "namespace": "../../../index",
                "model": model.ship,
                "blocks": [block],
                "output": "references/model.md",
            }
        )
    )
    return ModelPublication(source, root=root), model


def test_publish_tracks_source_and_product_without_repair(tmp_path):
    p, model = publication(tmp_path)
    assert any(f.get("kind") == "publication-stale" for f in p.check())
    p.compile()
    first = p.target.read_bytes()
    assert b"Renderers are named read-only projections." in first
    assert b"Diagram.Rendering" in first
    assert not any(
        f.get("kind") in {"publication-stale", "publication-drift"} for f in p.check()
    )
    p.compile()
    assert p.target.read_bytes() == first
    p.target.write_text("Manual edit")
    assert any(f.get("kind") == "publication-drift" for f in p.check())
    assert p.target.read_text() == "Manual edit"
    # A retained model change invalidates even if selected wording is equal.
    path = model.namespace.ships_root / f"{model.ship}.json"
    data = json.loads(path.read_text())
    data["hints"] = {"test_revision": 2}
    path.write_text(json.dumps(data))
    assert any(f.get("kind") == "publication-stale" for f in p.check())


def test_package_compiles_and_deploys_publication(tmp_path):
    p, _ = publication(tmp_path)
    (p.root / "SKILL.md").write_text("[Model](references/model.md)\n")
    (p.root / ".skw/main.json").write_text(
        json.dumps(
            {
                "type": entity(SkwSkill).name,
                "schema_version": 1,
                "entrypoint": "SKILL.md",
                "sources": [],
                "publications": [".skw/src/model.json"],
                "files": ["SKILL.md", "references/model.md"],
            }
        )
    )
    package = create_runtime().load_object(p.root / ".skw")
    package.build()
    target = tmp_path / "deployed"
    package.deploy(target)
    assert (target / "references/model.md").read_bytes() == p.target.read_bytes()
    assert not (target / ".skw").exists()


def test_missing_selection_does_not_overwrite_product(tmp_path):
    p, _ = publication(tmp_path)
    p.compile()
    first = p.target.read_bytes()
    p.data["blocks"] = ["00000000-0000-0000-0000-000000000000"]
    assert p.check()[0]["kind"] == "publication-unresolvable"
    with pytest.raises(DiagramError):
        p.compile()
    assert p.target.read_bytes() == first
