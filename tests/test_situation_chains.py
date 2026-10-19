"""A Situation Chain groups the Types of one situation's links and binds them."""

from __future__ import annotations

import pytest

from tarav.l0.kernel import TaravClass, TypeShip, entity
from tarav.l1.checks import CheckPOI, CheckResult, CHECKS_WORKFLOW_SHIP, SituationCheck
from tarav.l1.checks.chains import SituationChain
from tarav.l1.poi import fingerprint


class LampOn(CheckPOI):
    """A lamp was found on."""

    action = "Tarav.Test.Chains.Lamp.On.Action"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("d138efb2-623c-41d9-9b59-fef203c56235"),
                          name="Tarav.Test.Chains.Lamp.On.POI", workflow=CHECKS_WORKFLOW_SHIP)


class Unrelated(CheckPOI):
    """A POI of no lamp chain."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("03d1130b-da58-496d-bf8e-2bdcca6321ff"),
                          name="Tarav.Test.Chains.Unrelated", workflow=CHECKS_WORKFLOW_SHIP)


class LampCheck(SituationCheck):
    """Is the lamp on? Its caller gives the lamp and the level it read."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("b120cb78-7a96-4174-b7d1-9ff45bb9542e"),
                          name="Tarav.Test.Chains.Lamp.Check", workflow=CHECKS_WORKFLOW_SHIP)

    def __init__(self, *, situation, raises=LampOn) -> None:
        super().__init__(situation=situation)
        self.raises = raises

    def _run(self) -> CheckResult:
        if not self.situation["level"]:
            return CheckResult(self, status="completed")
        poi = self.poi(self.raises, message=f"{self.situation['lamp']} is on")
        return CheckResult(self, status="completed", pois=(poi,))


class LampChain(SituationChain):
    """A lamp, read at one level."""

    Check = LampCheck
    POIs = (LampOn,)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("adb767b3-bd07-4e13-874b-91531497ba4e"),
                          name="Tarav.Test.Chains.Lamp.Chain", workflow=CHECKS_WORKFLOW_SHIP)


HALL = {"lamp": "hall", "level": 3}


def test_defining_a_chain_binds_its_links_to_it():
    assert LampCheck.chain is LampChain and LampOn.chain is LampChain
    assert Unrelated.chain is None


def test_an_instance_is_one_situation_and_takes_its_identity_from_it():
    chain = LampChain(HALL)
    assert chain.identity == fingerprint([str(entity(LampChain).id), HALL])
    assert chain.identity == LampChain(dict(HALL)).identity
    assert chain.identity != LampChain({**HALL, "level": 2}).identity


def test_the_check_of_an_instance_raises_the_chains_poi_about_its_situation():
    chain = LampChain(HALL)
    (poi,) = chain.check().run().pois()
    assert type(poi) is LampOn and poi.situation == HALL
    assert poi.identity == fingerprint([str(entity(LampOn).id), HALL])
    assert chain.check().identity == fingerprint([str(entity(LampCheck).id), HALL])
    assert list(LampChain({**HALL, "level": 0}).check().run().pois()) == []


def test_a_chains_check_raises_only_the_chains_pois():
    with pytest.raises(TypeError, match="Tarav.Test.Chains.Unrelated is not a POI of Tarav.Test.Chains.Lamp.Chain"):
        LampChain.Check(situation=HALL, raises=Unrelated).run()


def test_a_chain_type_name_is_the_chain_which_one_then_what_it_is():
    from tarav.l1.checks.chains import chain_type_name

    assert chain_type_name("Tarav.Test.Chains.Lamp", "Check") == "Tarav.Test.Chains.Lamp.Check"
    assert chain_type_name("Tarav.Test.Chains.Lamp", "POI", "On") == "Tarav.Test.Chains.Lamp.On.POI"
    with pytest.raises(ValueError, match="'Resolution' is not a kind of chain Type"):
        chain_type_name("Tarav.Test.Chains.Lamp", "Resolution", "On")


def test_a_link_belongs_to_one_chain():
    with pytest.raises(TypeError, match="Tarav.Test.Chains.Lamp.Check already belongs to Tarav.Test.Chains.Lamp.Chain"):
        class Another(SituationChain):
            Check = LampCheck
            POIs = (LampOn,)

            @classmethod
            def class_entity(cls) -> TaravClass:
                return TaravClass(target=cls, id=TypeShip("5d7cd32f-3c12-4cad-848e-9b36c50e870f"),
                                  name="Tarav.Test.Chains.Another", workflow=CHECKS_WORKFLOW_SHIP)


def _poi(name, action):
    return type("Found", (CheckPOI,), {"action": action, "class_entity": classmethod(
        lambda cls: TaravClass(target=cls, id=TypeShip("6b1e4f0e-2b8a-4f4e-9a55-0d3b7f2f6c11"),
                               name=name, workflow=CHECKS_WORKFLOW_SHIP))})


def _check(name):
    return type("Looks", (SituationCheck,), {"class_entity": classmethod(
        lambda cls: TaravClass(target=cls, id=TypeShip("2f5b9c1d-7e4a-4b3c-8d2e-1a6f0c9b8e77"),
                               name=name, workflow=CHECKS_WORKFLOW_SHIP))})


def _chain(name, check, *pois):
    return type("Desk", (SituationChain,), {"Check": check, "POIs": pois, "class_entity": classmethod(
        lambda cls: TaravClass(target=cls, id=TypeShip("9c4d2a7b-3e1f-4a6b-b5c8-7d0e2f1a3b44"),
                               name=name, workflow=CHECKS_WORKFLOW_SHIP))})


@pytest.mark.parametrize(("chain", "check", "poi", "action", "message"), [
    ("Tarav.Test.Chains.Desk", "Tarav.Test.Chains.Desk.Check", "Tarav.Test.Chains.Desk.Dusty.POI",
     "Tarav.Test.Chains.Desk.Dusty.Action", "A chain's name ends in .Chain: Tarav.Test.Chains.Desk"),
    ("Tarav.Test.Chains.Desk.Chain", "Tarav.Test.Chains.DeskCheck", "Tarav.Test.Chains.Desk.Dusty.POI",
     "Tarav.Test.Chains.Desk.Dusty.Action",
     ("The Check of Tarav.Test.Chains.Desk.Chain is named Tarav.Test.Chains.Desk.Check, "
     "not Tarav.Test.Chains.DeskCheck")),
    ("Tarav.Test.Chains.Desk.Chain", "Tarav.Test.Chains.Desk.Check", "Tarav.Test.Chains.Desk.POI",
     "Tarav.Test.Chains.Desk.Action",
     ("A POI of Tarav.Test.Chains.Desk.Chain is named Tarav.Test.Chains.Desk.<problem>.POI, "
     "not Tarav.Test.Chains.Desk.POI")),
    ("Tarav.Test.Chains.Desk.Chain", "Tarav.Test.Chains.Desk.Check", "Tarav.Test.Chains.Desk.Dusty.POI",
     "Tarav.Actions.POI.Resolution",
     ("Tarav.Test.Chains.Desk.Dusty.POI names Tarav.Test.Chains.Desk.Dusty.Action as its Action, "
     "not Tarav.Actions.POI.Resolution")),
])
def test_a_chain_refuses_types_not_named_after_it(chain, check, poi, action, message):
    check_type, poi_type = _check(check), _poi(poi, action)
    with pytest.raises(TypeError) as refused:
        _chain(chain, check_type, poi_type)
    assert str(refused.value) == message
    # a refused chain binds nothing
    assert check_type.chain is None and poi_type.chain is None
