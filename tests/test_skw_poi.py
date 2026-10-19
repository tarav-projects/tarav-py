import json
import os

import pytest

from skw_records import identify_blocks

from tarav.l0.kernel import entity
from tarav.l1.checks import CheckSuite, run_checks
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
from tarav.l2.skw.chains import (
    ContextFreshnessCheck,
    GenerationContextResolutionCheck,
    GenerationFreshnessCheck,
)
from tarav.l2.skw.chains import SkwSkillSuite
from tarav.l2.skw.skills import SkwSkill
from tarav.l0.testing import write_project_marker
from tarav.l1.skills import SkillMarker
from tarav.l3.runtime import create_runtime


def _produced(suite):
    """What a suite would run, nested suites opened, without running it."""
    for item in suite.produce():
        if isinstance(item, CheckSuite):
            yield from _produced(item)
        else:
            yield item


def _layout(tmp_path):
    """A Project holding one skill: the skill folder, built by a depot of the Project."""
    write_project_marker(tmp_path)
    root = tmp_path / "skills/explain"
    root.mkdir(parents=True)
    SkillMarker.create(root)
    return root


def _depot(root):
    return root.parent.parent / ".tarav/skillware/skills" / root.name


def _document(source):
    depot = source.parent.parent
    return Document(source, root=depot.parents[3] / "skills" / depot.name, depot=depot)


def _document_source(root):
    path = _depot(root) / "src/explanation.skw.json"
    path.parent.mkdir(parents=True)
    (root / "input.py").write_text("print(1)")

    def beside(name):
        # a context path is relative to the source that declares it
        return os.path.relpath(root / name, path.parent)
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
                        "locator": {"path": beside("context.txt")},
                    }
                },
                "annotations": [{
                    "type": entity(GenerationAnnotation).name,
                    "instructions": ["Explain the current program."],
                    "context": [
                        {
                            "type": entity(StructuredFileReference).name,
                            "locator": {"path": beside("input.py")},
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
    (_depot(root) / "main.json").write_text(json.dumps({
        "type": entity(SkwSkill).name,
        "schema_version": 1,
        "skill_id": str(SkillMarker.of(root).id),
        "product": "skills/explain",
        "entrypoint": "explanation.md",
        "sources": ["src/explanation.skw.json"],
        "files": ["explanation.md"],
        "dependencies": [],
    }))
    if not (root / "explanation.md").exists():
        (root / "explanation.md").write_text("# Explanation\n")
    return create_runtime().load_object(_depot(root))


def test_generation_context_resolution_is_independent_and_repairable(tmp_path):
    root = _layout(tmp_path)
    source, data = _document_source(root)
    data["blocks"][1]["content"] = ["The program prints one."]
    source.write_text(json.dumps(data))
    assert _document(source).compile()["written"]
    skill = _skill(root)

    checks = tuple(
        check for check in _produced(SkwSkillSuite(skill))
        if isinstance(check, GenerationContextResolutionCheck)
    )
    assert len(checks) == 2
    pois = tuple(poi for result in run_checks(checks) for poi in result.pois())
    assert len(pois) == 1
    assert isinstance(pois[0], ContextUnresolvable)
    assert pois[0].situation["subject"]["context_index"] == 1
    assert not any(isinstance(poi, InvalidLoadingModel) for poi in skill.evaluate().pois)

    (root / "context.txt").write_text("available")
    assert not any(
        isinstance(poi, ContextUnresolvable) for poi in skill.evaluate().pois
    )

    data["blocks"][1]["annotations"][0]["context"][1]["index"] = "absent"
    source.write_text(json.dumps(data))
    emitted = skill.evaluate().pois
    assert any(isinstance(poi, ContextUnresolvable) for poi in emitted)
    assert not any(isinstance(poi, InvalidLoadingModel) for poi in emitted)


# tarav.breadcrumb 6b9be7810af0
def test_skw_freshness_checks_snapshot_independent_acceptance_scopes(
    tmp_path, monkeypatch
):
    root = _layout(tmp_path)
    source, data = _document_source(root)
    context_path = root / "context.txt"
    context_path.write_text("context one")
    source.write_text(json.dumps(data))

    prepared = _document(source).prepare("explain")
    data["blocks"][1]["content"] = ["Prints one."]
    source.write_text(json.dumps(data))
    document = _document(source)
    document.record(prepared["id"])
    assert document.compile()["findings"] == []

    skill = _skill(root)
    data["blocks"][1]["annotations"][0]["instructions"] = [
        "Explain the revised program."
    ]
    source.write_text(json.dumps(data))

    checks = tuple(check for check in _produced(SkwSkillSuite(skill)) if isinstance(
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

    bench = Bench(tmp_path / "bench-records", create_runtime().records)
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


# tarav.breadcrumb 7f528a5c259b
def test_the_package_suite_detects_what_the_skill_command_shows(tmp_path):
    from tarav.l1.skw.pois import ProductDrift, UnbundledLink

    root = _layout(tmp_path)
    source, data = _document_source(root)
    data["blocks"][1]["content"] = ["The program prints one."]
    source.write_text(json.dumps(data))
    (root / "context.txt").write_text("available")
    assert _document(source).compile()["written"]
    skill = _skill(root)

    def kinds(pois):
        return sorted(type(poi).__name__ for poi in pois)

    before = skill.checks.run().pois()
    assert not any(isinstance(poi, (ProductDrift, UnbundledLink)) for poi in before)

    # a hand edit of the compiled file: a line the source does not have, and a
    # link to a file the package does not bundle
    product = root / "explanation.md"
    (root / "extra.md").write_text("# Extra\n")
    product.write_text(product.read_text() + "\nSee [extra](extra.md).\n")

    found = skill.checks.run().pois()
    assert any(isinstance(poi, ProductDrift) for poi in found)
    assert any(isinstance(poi, UnbundledLink) for poi in found)
    # the suite a Project runs and the skill command agree on what they find
    assert kinds(found) == kinds(skill.evaluate().pois)
    assert skill.checks.suite().identity == {"type": "Tarav.SKW.Suite.Skill",
                                             "key": str(SkillMarker.of(root).id)}


# tarav.breadcrumb 82935932a297
def test_a_product_drift_declares_what_was_compared(tmp_path):
    from tarav.l1.skw.pois import ProductDrift

    root = _layout(tmp_path)
    source, data = _document_source(root)
    data["blocks"][1]["content"] = ["The program prints one."]
    source.write_text(json.dumps(data))
    (root / "context.txt").write_text("available")
    assert _document(source).compile()["written"]
    skill = _skill(root)
    product = root / "explanation.md"
    compiled = product.read_text()

    def drift():
        return [poi for poi in skill.checks.run().pois() if isinstance(poi, ProductDrift)]

    product.write_text(compiled + "\nA line written by hand.\n")
    (first,) = drift()
    assert set(first.situation) == {"subject", "actual", "expected"}
    assert first.situation["subject"] == {"skill": str(SkillMarker.of(root).id),
                                          "path": "explanation.md"}
    assert first.situation["actual"] != first.situation["expected"]
    assert first.message == (f"{root.name}: explanation.md differs from what its "
                             "source produces (1 places, 2 lines)")
    assert set(first.details) == {"source", "difference"}
    assert first.details["source"] == str(source.resolve())
    assert first.details["difference"][-1] == "-A line written by hand."
    assert not set(first.details) & set(first.situation)

    # another file of the package changes: the same drift, the same POI
    main = _depot(root) / "main.json"
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


# tarav.breadcrumb f38c67b3208d
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
        "type": "Tarav.SKW.ReadingNode.UnreachableBlock.POI", "block": "x", "path": "a.skw.json"}

    # what a package reports is said by Types, and so is what a command prints
    root = _layout(tmp_path)
    source, data = _document_source(root)
    data["blocks"][1]["content"] = ["The program prints one."]
    source.write_text(json.dumps(data))
    (root / "context.txt").write_text("available")
    assert _document(source).compile()["written"]
    product = root / "explanation.md"
    product.write_text(product.read_text() + "\nA line written by hand.\n")
    findings = _document(source).lint()
    assert [found.poi for found in findings].count(skw.ProductDrift) == 1
    assert all("kind" not in found.to_json() for found in findings)
    for poi in _skill(root).checks.run().pois():
        if isinstance(poi, skw.SkwPOI):
            # the details repeat nothing of the situation, and name no kind;
            # the state of the rest of the package is no part of the problem
            assert "finding" not in poi.details and "surface_state" not in poi.situation
            assert "surface_state" not in poi.details
            assert "kind" not in poi.records.to_record()["details"]
            assert isinstance(poi, skw.ProductDrift) or poi.message.startswith(
                type(poi).statement)


# tarav.breadcrumb f05d8da396a5
def test_a_declared_link_is_checked_only_by_its_prose_part(tmp_path):

    from tarav.l1.skw.pois import MissingMarkdownLink
    from tarav.l2.skw.chains import LinkProseChain

    root = _layout(tmp_path)
    source = _depot(root) / "src/explanation.skw.json"
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
        _document(source).compile()
        return [poi for poi in _skill(root).checks.run().pois()
                if type(poi).chain is LinkProseChain]

    # the text lacks the declared link; the authored link nobody declared is not a POI
    (missing,) = reading_pois()
    assert isinstance(missing, MissingMarkdownLink)
    # the skill is named by the UUID in its marker, not by where it lies
    assert missing.situation == {"subject": {"skill": str(SkillMarker.of(root).id),
                                             "block": body["id"], "target": href}}
    assert missing.message.startswith(MissingMarkdownLink.statement)
    assert not missing.details

    # the text holds it: nothing to say
    body["content"] = [f"Read [the end]({href}), or see [elsewhere](https://example.com).", ""]
    assert reading_pois() == []

    # a link without a prose part checks nothing, whatever the text says
    body["content"] = ["Read on.", ""]
    del link["prose"]
    assert reading_pois() == []


def test_a_problem_keeps_its_identity_when_another_package_file_changes(tmp_path):
    from tarav.l1.skw import pois as skw

    root = _layout(tmp_path)
    source, data = _document_source(root)
    data["blocks"][1]["content"] = ["The program prints one."]
    source.write_text(json.dumps(data))
    (root / "context.txt").write_text("available")
    (root / "notes.md").write_text("notes\n")
    skill = _skill(root)
    main = _depot(root) / "main.json"
    main.write_text(json.dumps({**json.loads(main.read_text()), "files": ["explanation.md", "notes.md"]}))
    assert _document(source).compile()["written"]
    data["blocks"][0]["content"] = ["# Explanation, edited", ""]  # the source changed after compiling
    source.write_text(json.dumps(data))

    def drift():
        package = create_runtime().load_object(_depot(root))
        (poi,) = [poi for poi in package.checks.run().pois() if isinstance(poi, skw.SourceUncompiled)]
        return poi

    before = drift()
    (root / "notes.md").write_text("notes, edited\n")  # unrelated to the drifted block
    after = drift()

    assert skill is not None
    assert after.identity == before.identity
    assert after.situation == before.situation == {"subject": before.situation["subject"]}
    assert "surface_state" not in after.details
