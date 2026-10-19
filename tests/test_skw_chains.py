"""The Skillware analysis as Situation Chains: one atomic Check per situation of a package."""

import json

from skw_records import identify_blocks

from tarav.l0.kernel import entity
from tarav.l0.testing import write_project_marker
from tarav.l1.checks import CheckSuite, SituationCheck
from tarav.l1.poi import fingerprint
from tarav.l1.skills import SkillMarker
from tarav.l1.skw.document import Document, DocumentRecord, SkwBlock
from tarav.l1.skw.pois import MissingContent, MissingDependency, MissingLinkTarget, UnbundledLink
from tarav.l2.skw.chains import BlockChain, ConsumerLinkChain, SkwSkillSuite
from tarav.l2.skw.skills import SkwSkill
from tarav.l3.runtime import create_runtime


def _skill(tmp_path, *, body):
    """A Project building one skill from one source with a title and a body block."""
    write_project_marker(tmp_path)
    root = tmp_path / "skills/guide"
    root.mkdir(parents=True)
    SkillMarker.create(root)
    depot = tmp_path / ".tarav/skillware/skills/guide"
    source = depot / "src/guide.skw.json"
    source.parent.mkdir(parents=True)
    data = {"type": entity(DocumentRecord).name, "schema_version": 1, "output": "guide.md",
            "blocks": [{"type": entity(SkwBlock).name, "id": "title", "content": ["# Guide", ""]},
                       {"type": entity(SkwBlock).name, "id": "body", "content": body}]}
    source.write_text(json.dumps(identify_blocks(data, scope="guide")))
    (depot / "main.json").write_text(json.dumps({
        "type": entity(SkwSkill).name, "schema_version": 1,
        "skill_id": str(SkillMarker.of(root).id), "product": "skills/guide",
        "entrypoint": "guide.md", "sources": ["src/guide.skw.json"], "files": ["guide.md"],
        "dependencies": [{"kind": "skill", "path": "../absent", "purposes": ["consumer"]}]}))
    assert Document(source, root=root, depot=depot).compile()["written"]
    return create_runtime().load_object(depot)


def _produced(suite):
    for item in suite.produce():
        if isinstance(item, CheckSuite):
            yield from _produced(item)
        else:
            yield item


def test_the_skill_suite_runs_one_atomic_check_per_situation(tmp_path):
    skill = _skill(tmp_path, body=["Read [one](one.md)."])
    owner = {"skill": str(skill.skill_id)}
    produced = [check for check in _produced(SkwSkillSuite(skill))
                if isinstance(check, SituationCheck)]
    assert [(entity(type(check).chain).name, check.situation["subject"])
            for check in produced] == [
        ("Tarav.SKW.Chain.SkillMarker", owner),
        ("Tarav.SKW.Chain.SkillLoading", owner),
        ("Tarav.SKW.Chain.Product", {**owner, "path": "guide.md"}),
        ("Tarav.SKW.Chain.Source", {**owner, "path": "src/guide.skw.json"}),
        ("Tarav.SKW.Chain.ProductDrift", {**owner, "path": "guide.md"}),
        ("Tarav.SKW.Chain.Block", {**owner, "path": "src/guide.skw.json", "block": "title"}),
        ("Tarav.SKW.Chain.Block", {**owner, "path": "src/guide.skw.json", "block": "body"}),
        ("Tarav.SKW.Chain.ConsumerFile", {**owner, "path": "guide.md"}),
        ("Tarav.SKW.Chain.ConsumerLink", {**owner, "path": "guide.md", "target": "one.md"}),
        ("Tarav.SKW.Chain.Dependency", {**owner, "path": "../absent"}),
    ]
    # every object of a chain is its Type and its situation, hashed
    for check in produced:
        assert check.identity == fingerprint([str(entity(type(check)).id),
                                              check.situation.to_json_value()])


def test_two_bad_links_of_one_file_are_two_situations(tmp_path):
    skill = _skill(tmp_path, body=["Read [one](one.md) and [two](two.md)."])
    pois = [poi for poi in skill.checks.run().pois()
            if isinstance(poi, (UnbundledLink, MissingLinkTarget))]
    assert sorted((type(poi).__name__, poi.situation["subject"]["target"]) for poi in pois) == [
        ("MissingLinkTarget", "one.md"), ("MissingLinkTarget", "two.md"),
        ("UnbundledLink", "one.md"), ("UnbundledLink", "two.md")]
    assert {type(poi).chain for poi in pois} == {ConsumerLinkChain}
    assert pois[0].message == ("A file of the package links to a file that the package "
                               "does not bundle: guide.md to one.md")


def test_situations_name_paths_as_declared_not_as_found_on_this_machine(tmp_path):
    skill = _skill(tmp_path, body=["Plain."])
    (missing,) = [poi for poi in skill.check() if isinstance(poi, MissingDependency)]
    assert missing.situation == {"subject": {"skill": str(skill.skill_id), "path": "../absent"}}
    assert missing.details == {"detail": "consumer"}


def test_a_block_poi_is_raised_by_the_check_of_that_block(tmp_path):
    skill = _skill(tmp_path, body=["Plain."])
    source = skill.depot / "src/guide.skw.json"
    data = json.loads(source.read_text())
    data["blocks"][1]["content"] = None
    source.write_text(json.dumps(data))
    (missing,) = [poi for poi in skill.check() if isinstance(poi, MissingContent)]
    # the same situation the package analysis gave it before it was a chain
    assert missing.situation == {"subject": {"skill": str(skill.skill_id),
                                             "path": "src/guide.skw.json", "block": "body"}}
    assert type(missing).chain is BlockChain
    assert missing.message == "A block has no content: src/guide.skw.json: body"


def test_every_skillware_poi_type_names_its_own_action_type():
    from tarav.l1.actions import action_types
    from tarav.l1.actions.pois import BlessableResolution
    from tarav.l1.skw.pois import SkwPOI, StaleContext, StaleGeneration

    create_runtime()
    registered = action_types()
    poi_types = SkwPOI.__subclasses__()
    actions = [registered[poi_type.action] for poi_type in poi_types]
    assert [entity(action).name for action in actions] == [
        f"{entity(poi_type).name}.Resolution" for poi_type in poi_types]
    assert len(set(actions)) == len(poi_types) == len({entity(a).id for a in actions})
    assert [poi_type for poi_type, action in zip(poi_types, actions)
            if issubclass(action, BlessableResolution)] == [StaleContext, StaleGeneration]
