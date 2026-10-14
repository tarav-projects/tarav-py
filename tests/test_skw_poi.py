import json

import pytest

from skw_records import identify_blocks

from tarav.l0.kernel import entity
from tarav.l1.checks import run_checks
from tarav.l1.skw.document import Document, DocumentRecord
from tarav.l1.skw.annotations import GenerationAnnotation, ObjectIndexReference
from tarav.l1.skw.document import SkwBlock
from tarav.l1.references.structured import StructuredFileReference
from tarav.l1.skw.pois import (
    ContextUnresolvable,
    InvalidLoadingModel,
    StaleContext,
    StaleGeneration,
)
from tarav.l2.skw.pois import (
    ContextFreshnessCheck,
    GenerationContextResolutionCheck,
    GenerationFreshnessCheck,
)
from tarav.l2.skw.skills import SkwSkill
from tarav.l3.runtime import create_runtime


def _document_source(root):
    path = root / ".skw/src/explanation.skw.json"
    path.parent.mkdir(parents=True)
    (root / "input.py").write_text("print(1)")
    data = {
        "type": entity(DocumentRecord).name,
        "schema_version": 1,
        "output": "explanation.md",
        "blocks": [
            {
                "type": entity(SkwBlock).name,
                "id": "title",
                "content": ["# Explanation", ""],
            },
            {
                "type": entity(SkwBlock).name,
                "id": "explain",
                "objects_index": {
                    "policy": {
                        "type": entity(StructuredFileReference).name,
                        "locator": {"path": "../../context.txt"},
                    }
                },
                "annotations": [{
                    "type": entity(GenerationAnnotation).name,
                    "instructions": ["Explain the current program."],
                    "context": [
                        {
                            "type": entity(StructuredFileReference).name,
                            "locator": {"path": "../../input.py"},
                        },
                        {
                            "type": entity(ObjectIndexReference).name,
                            "index": "policy",
                        },
                    ],
                }],
                "content": None,
            },
        ],
    }
    identify_blocks(data, scope="explanation")
    path.write_text(json.dumps(data))
    return path, data


def _skill(root):
    (root / ".skw/main.json").write_text(json.dumps({
        "type": entity(SkwSkill).name,
        "schema_version": 1,
        "entrypoint": "explanation.md",
        "sources": [".skw/src/explanation.skw.json"],
        "files": ["explanation.md"],
        "dependencies": [],
    }))
    if not (root / "explanation.md").exists():
        (root / "explanation.md").write_text("# Explanation\n")
    return create_runtime().load_object(root / ".skw")


def test_generation_context_resolution_is_independent_and_repairable(tmp_path):
    source, data = _document_source(tmp_path)
    data["blocks"][1]["content"] = ["The program prints one."]
    source.write_text(json.dumps(data))
    assert Document(source).compile()["written"]
    skill = _skill(tmp_path)

    checks = tuple(
        check for check in skill._checks()
        if isinstance(check, GenerationContextResolutionCheck)
    )
    assert len(checks) == 2
    pois = tuple(poi for result in run_checks(checks) for poi in result.pois())
    assert len(pois) == 1
    assert isinstance(pois[0], ContextUnresolvable)
    assert pois[0].situation["subject"]["context_index"] == 1
    assert not any(isinstance(poi, InvalidLoadingModel) for poi in skill.evaluate().pois)

    (tmp_path / "context.txt").write_text("available")
    assert not any(
        isinstance(poi, ContextUnresolvable) for poi in skill.evaluate().pois
    )

    data["blocks"][1]["annotations"][0]["context"][1]["index"] = "absent"
    source.write_text(json.dumps(data))
    emitted = skill.evaluate().pois
    assert any(isinstance(poi, ContextUnresolvable) for poi in emitted)
    assert not any(isinstance(poi, InvalidLoadingModel) for poi in emitted)


# tarav.breadcrumb 6b9be7810af01872f85ffccc2c271b21ce3fab37b6ebd82f0fada50386a36f7f
def test_skw_freshness_checks_snapshot_independent_acceptance_scopes(
    tmp_path, monkeypatch
):
    source, data = _document_source(tmp_path)
    context_path = tmp_path / "context.txt"
    context_path.write_text("context one")
    source.write_text(json.dumps(data))

    prepared = Document(source).prepare("explain")
    data["blocks"][1]["content"] = ["Prints one."]
    source.write_text(json.dumps(data))
    document = Document(source)
    document.record(prepared["id"])
    assert document.compile()["findings"] == []

    (tmp_path / ".skw/main.json").write_text(json.dumps({
        "type": entity(SkwSkill).name,
        "schema_version": 1,
        "entrypoint": "explanation.md",
        "sources": [".skw/src/explanation.skw.json"],
        "files": ["explanation.md"],
        "dependencies": [],
    }))
    skill = create_runtime().load_object(tmp_path / ".skw")
    data["blocks"][1]["annotations"][0]["instructions"] = [
        "Explain the revised program."
    ]
    source.write_text(json.dumps(data))

    checks = tuple(check for check in skill._checks() if isinstance(
        check, (GenerationFreshnessCheck, ContextFreshnessCheck)
    ))
    assert {type(check) for check in checks} == {
        GenerationFreshnessCheck,
        ContextFreshnessCheck,
    }

    def unexpected_read(*args, **kwargs):
        raise AssertionError("SituationCheck evaluation read external state")

    with monkeypatch.context() as isolated:
        isolated.setattr(Document, "generation_fingerprint", unexpected_read)
        isolated.setattr(Document, "_resolved_context", unexpected_read)
        pois = tuple(poi for result in run_checks(checks) for poi in result.pois())
    generation = next(poi for poi in pois if isinstance(poi, StaleGeneration))
    assert not any(isinstance(poi, StaleContext) for poi in pois)

    from blessing_bench import Bench

    bench = Bench(tmp_path / "records", create_runtime().records)
    bench.bless(generation, reason="The output remains valid for input revision two.")
    assert bench.pois.standing(generation) == "blessed"
    data["blocks"][1]["annotations"][0]["instructions"] = [
        "Explain the final program."
    ]
    source.write_text(json.dumps(data))
    context_path.write_text("context two")
    changed = skill.evaluate().pois
    changed_generation = next(
        poi for poi in changed if isinstance(poi, StaleGeneration)
    )
    assert changed_generation.identity != generation.identity
    assert bench.pois.standing(changed_generation) == "open"
    assert any(isinstance(poi, StaleContext) for poi in changed)


# tarav.breadcrumb 7f528a5c259b365f5e59cb23ce3be218a54766baf7d0e473f2d2379ef58c5d8f
def test_the_package_suite_detects_what_the_skill_command_shows(tmp_path):
    from tarav.l1.skw.pois import ProductDrift, UnbundledLink

    source, data = _document_source(tmp_path)
    data["blocks"][1]["content"] = ["The program prints one."]
    source.write_text(json.dumps(data))
    (tmp_path / "context.txt").write_text("available")
    assert Document(source).compile()["written"]
    skill = _skill(tmp_path)

    def kinds(pois):
        return sorted(type(poi).__name__ for poi in pois)

    before = skill.checks.run().pois()
    assert not any(isinstance(poi, (ProductDrift, UnbundledLink)) for poi in before)

    # a hand edit of the compiled file: a line the source does not have, and a
    # link to a file the package does not bundle
    product = tmp_path / "explanation.md"
    (tmp_path / "extra.md").write_text("# Extra\n")
    product.write_text(product.read_text() + "\nSee [extra](extra.md).\n")

    found = skill.checks.run().pois()
    assert any(isinstance(poi, ProductDrift) for poi in found)
    assert any(isinstance(poi, UnbundledLink) for poi in found)
    # the suite a Project runs and the skill command agree on what they find
    assert kinds(found) == kinds(skill.evaluate().pois)
    assert skill.checks.suite().identity == {"type": "Tarav.Checks.Suite", "key": tmp_path.name}


# tarav.breadcrumb 82935932a297a50ab9c5849ee8aa5a7723673f80895d916211bab92cff53fbcf
def test_a_product_drift_declares_what_was_compared(tmp_path):
    from tarav.l1.skw.pois import ProductDrift

    source, data = _document_source(tmp_path)
    data["blocks"][1]["content"] = ["The program prints one."]
    source.write_text(json.dumps(data))
    (tmp_path / "context.txt").write_text("available")
    assert Document(source).compile()["written"]
    skill = _skill(tmp_path)
    product = tmp_path / "explanation.md"
    compiled = product.read_text()

    def drift():
        return [poi for poi in skill.checks.run().pois() if isinstance(poi, ProductDrift)]

    product.write_text(compiled + "\nA line written by hand.\n")
    (first,) = drift()
    assert set(first.situation) == {"product", "actual", "expected"}
    assert first.situation["product"] == str(product.resolve())
    assert first.situation["actual"] != first.situation["expected"]
    assert first.message == (f"{tmp_path.name}: explanation.md differs from what its "
                             "source produces (1 places, 2 lines)")
    assert set(first.details) == {"source", "difference"}
    assert first.details["source"] == str(source.resolve())
    assert first.details["difference"][-1] == "-A line written by hand."
    assert not set(first.details) & set(first.situation)

    # another file of the package changes: the same drift, the same POI
    main = tmp_path / ".skw/main.json"
    main.write_text(main.read_text() + "\n")
    (same,) = drift()
    assert same.identity == first.identity

    # the compiled file changes again: another drift
    product.write_text(compiled + "\nAnother line written by hand.\n")
    (other,) = drift()
    assert other.identity != first.identity
    assert other.situation["expected"] == first.situation["expected"]

    product.write_text(compiled)
    assert drift() == []


# tarav.breadcrumb f38c67b3208d0992bd9f3fdb72418be0d592ab312e0f8c8a328aa47db2bb4cf4
def test_a_finding_names_its_poi_type_and_no_type_has_a_second_name(tmp_path):
    from tarav.l1.skw import pois as skw

    atomic = skw.SkwPOI.__subclasses__()
    assert len(atomic) == len({cls.statement for cls in atomic}) and all(
        cls.statement and not cls.statement.endswith(".") for cls in atomic)
    assert not hasattr(skw, "CLASSES")
    with pytest.raises(TypeError):
        skw.Finding("unreachable-block", block="x")
    with pytest.raises(TypeError):
        skw.Finding(skw.SkwPOI, block="x")  # the family states nothing

    finding = skw.Finding(skw.UnreachableBlock, block="x")
    assert finding.poi is skw.UnreachableBlock
    assert finding.at(path="a.skw.json").to_json() == {
        "type": "Tarav.SKW.POI.UnreachableBlock", "block": "x", "path": "a.skw.json"}

    # what a package reports is said by Types, and so is what a command prints
    source, data = _document_source(tmp_path)
    data["blocks"][1]["content"] = ["The program prints one."]
    source.write_text(json.dumps(data))
    (tmp_path / "context.txt").write_text("available")
    assert Document(source).compile()["written"]
    product = tmp_path / "explanation.md"
    product.write_text(product.read_text() + "\nA line written by hand.\n")
    findings = Document(source).lint()
    assert [found.poi for found in findings].count(skw.ProductDrift) == 1
    assert all("kind" not in found.to_json() for found in findings)
    for poi in _skill(tmp_path).checks.run().pois():
        if isinstance(poi, skw.SkwPOI):
            # the details repeat nothing of the situation, and name no kind
            assert "finding" not in poi.details and "surface_state" not in poi.details
            assert "kind" not in poi.records.to_record()["details"]
            assert isinstance(poi, skw.ProductDrift) or poi.message.startswith(
                type(poi).statement)


# tarav.breadcrumb f05d8da396a57b6a29eaa13c03eaf6566a43a142b26b04753cadea456fdd02cd
def test_a_declared_link_is_checked_only_by_its_prose_part(tmp_path):
    from pathlib import Path

    from tarav.l1.skw.pois import MissingMarkdownLink
    from tarav.l2.skw.reading_checks import READING_CHECK_TYPES

    source = tmp_path / ".skw/src/explanation.skw.json"
    source.parent.mkdir(parents=True)
    data = identify_blocks({
        "type": entity(DocumentRecord).name, "schema_version": 1, "output": "explanation.md",
        "blocks": [
            {"type": entity(SkwBlock).name, "id": "title", "content": ["# Explanation", ""]},
            {"type": entity(SkwBlock).name, "id": "body", "content": [
                "Read on, or see [elsewhere](https://example.com).", ""]},
            {"type": entity(SkwBlock).name, "id": "end", "content": ["The end."]},
        ],
    }, scope="links")
    body, end = data["blocks"][1], data["blocks"][2]["id"]
    link = {"type": "Tarav.SKW.Reading.ExpectedLink", "target": end,
            "entry": {"type": "Tarav.SKW.Reading.BlockEntry", "node": end},
            "prose": {"type": "Tarav.SKW.Reading.MarkdownProse"}}
    body["annotations"] = [link]
    href = f"explanation.md#skw-{end}"

    def reading_pois():
        source.write_text(json.dumps(data))
        Document(source).compile()
        return [poi for poi in _skill(tmp_path).checks.run().pois()
                if isinstance(poi.check, READING_CHECK_TYPES)]

    # the text lacks the declared link; the authored link nobody declared is not a POI
    (missing,) = reading_pois()
    assert isinstance(missing, MissingMarkdownLink)
    assert set(missing.situation) == {"project", "block", "href"}
    assert Path(missing.situation["project"]).resolve() == tmp_path.resolve()
    assert (missing.situation["block"], missing.situation["href"]) == (body["id"], href)
    assert missing.message.startswith(MissingMarkdownLink.statement)
    assert not missing.details

    # the text holds it: nothing to say
    body["content"] = [f"Read [the end]({href}), or see [elsewhere](https://example.com).", ""]
    assert reading_pois() == []

    # a link without a prose part checks nothing, whatever the text says
    body["content"] = ["Read on.", ""]
    del link["prose"]
    assert reading_pois() == []
